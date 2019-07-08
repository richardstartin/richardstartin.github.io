---
ID: 11244
title: Vectorised Polynomial Hash Codes
author: Richard Startin
post_excerpt: ""
layout: post
theme: minima
published: true
date: 2018-08-25 12:49:56
---
To provide support for the idea of pluggable hashing strategies, Peter Lawrey <a href="https://vanilla-java.github.io/2018/08/15/Looking-at-randomness-and-performance-for-hash-codes.html" rel="noopener" target="_blank">demonstrates</a> that there are better and faster hash codes than the JDK implementation of `String.hashCode` or `Arrays.hashCode`. I really like the analysis of output distribution so recommend reading the post. However, I'm not absolutely sure if pluggable hashing strategies would be a good idea. They can induce coupling between the strategy implementation and the contents of the hashed data structure, which have different life cycles and code ownership. If performance is what matters, why not just make the existing algorithm much faster?

Peter's hash code uses `Unsafe` to reinterpret each four bytes as an integer, but is otherwise just another polynomial hash code with a different coefficient. It produces a slightly different result, but with potentially better properties. Here's that hash code.

```java
private static final int M2 = 0x7A646E4D;

// read 4 bytes at a time from a byte[] assuming Java 9+ Compact Strings
private static int getIntFromArray(byte[] value, int i) {
    return UnsafeMemory.INSTANCE.UNSAFE.getInt(value, BYTE_ARRAY_OFFSET + i); 
}

public static int nativeHashCode(byte[] value) {
    long h = getIntFromArray(value, 0);
    for (int i = 4; i < value.length; i += 4)
        h = h * M2 + getIntFromArray(value, i);
    h *= M2;
    return (int) h ^ (int) (h >>> 25);
}
```

Leaving the output distribution to one side, Peter reports that this hash code performs better than `Arrays.hashCode(byte[])` and this is accurate. Where does the performance come from? The reintepretation reduces the number of multiplications by a factor of four, but you need `Unsafe` to achieve this. This also obviates the need to convert each byte to an integer to avoid overflow. Another problem is solved just by changing the multiplier. `Arrays.hashCode` is generally slow because the multiplication by 31 gets strength reduced to a left shift by five and a subtraction, which inadvertently creates a data dependency which can't be unrolled. When the multiplier is 31, just unrolling the multiplication to disable the strength reduction can <a href="http://mail.openjdk.java.net/pipermail/core-libs-dev/2014-September/028898.html" rel="noopener" target="_blank">increase throughput by 2x</a>, and the rather obscure choice of `0x7A646E4D` means that no such transformation takes place: this results in independent chains of multiplications and additions in the main loop:

```asm
  0.18%    0.46%     ││  0x00007f3b21c05285: movslq 0x18(%rdx,%r8,1),%rsi
  5.93%    6.28%     ││  0x00007f3b21c0528a: movslq 0x1c(%rdx,%r8,1),%rax
  0.12%    0.42%     ││  0x00007f3b21c0528f: imul   $0x7a646e4d,%rcx,%rcx
 11.87%   37.31%     ││  0x00007f3b21c05296: movslq 0x14(%rdx,%r8,1),%rdi
  0.10%    0.18%     ││  0x00007f3b21c0529b: movslq 0x10(%rdx,%r8,1),%r8
  0.06%    0.58%     ││  0x00007f3b21c052a0: add    %rcx,%r8
  5.29%    1.30%     ││  0x00007f3b21c052a3: imul   $0x7a646e4d,%r8,%r8
 18.34%   21.94%     ││  0x00007f3b21c052aa: add    %r8,%rdi
  6.33%    1.96%     ││  0x00007f3b21c052ad: imul   $0x7a646e4d,%rdi,%r8
 17.60%   10.88%     ││  0x00007f3b21c052b4: add    %r8,%rsi
  5.39%    0.72%     ││  0x00007f3b21c052b7: imul   $0x7a646e4d,%rsi,%rcx
 17.80%   11.58%     ││  0x00007f3b21c052be: add    %rax,%rcx 
```

Is this as good as it can get and is there something fundamentally wrong with the JDK algorithm? The algorithm can be vectorised, but this is beyond C2's autovectoriser. The same algorithm is used for `Arrays.hashCode(int[])`, which doesn't have the complication of type promotion from `byte` to `int`. I have noted before that this can be transformed to a loop which C2 can autovectorise by precomputing the coefficients of the polynomial (i.e. the powers of 31 until they repeat modulo 32, but `x -> x * 31` has a very long period modulo 32) but this requires either an enormous array or a maximum length.

```java
    private int[] coefficients;
    private int seed;

    void init(int size) {
        coefficients = new int[size]; 
        coefficients[size - 1] = 1;
        for (int i = size - 2; i >= 0; --i) {
            coefficients[i] = 31 * coefficients[i + 1];
        }
        seed = 31 * coefficients[0];
    }

    public int hashCodeAutoVectorised() {
        int result = seed;
        for (int i = 0; i < data.length && i < coefficients.length; ++i) {
            result += coefficients[i] * data[i];
        }
        return result;
    }
```


This idea isn't practical but demonstrates that this kind of polynomial can be computed efficiently, if only the coefficients could be generated without disabling autovectorisation. Generating the coefficients on the fly is possible with the Vector API. It requires a multiplier containing eight consecutive powers of 31, and the exponent of each element needs to be increased by eight in each iteration. This can be achieved with a broadcast variable.

```java
  public int polynomialHashCode() {
    var next = YMM_INT.broadcast(POWERS_OF_31_BACKWARDS[33 - 9]);
    var coefficients = YMM_INT.fromArray(POWERS_OF_31_BACKWARDS, 33 - 8);
    var acc = YMM_INT.zero();
    for (int i = data.length; i - YMM_INT.length() >= 0; i -= YMM_INT.length()) {
      acc = acc.add(coefficients.mul(YMM_INT.fromArray(data, i - YMM_INT.length())));
      coefficients = coefficients.mul(next);
    }
    return acc.addAll() + coefficients.get(7);
  }
```

There's a problem here - it sandwiches a low latency addition between two high latency multiplications, so there is a data dependency and unrolling without breaking the dependency isn't necessarily helpful. The dependency can be broken manually by using four accumulators, four coefficient vectors consisting of 32 consecutive powers of 31, and each coefficient must have its logarithm increased by 32 in each iteration. It may look dirty but the dependencies are eradicated.

```java
  public int polynomialHashCodeUnrolled() {
    var next = YMM_INT.broadcast(POWERS_OF_31_BACKWARDS[0]);
    var coefficients1 = YMM_INT.fromArray(POWERS_OF_31_BACKWARDS, 33 - 8);
    var coefficients2 = YMM_INT.fromArray(POWERS_OF_31_BACKWARDS, 33 - 16);
    var coefficients3 = YMM_INT.fromArray(POWERS_OF_31_BACKWARDS, 33 - 24);
    var coefficients4 = YMM_INT.fromArray(POWERS_OF_31_BACKWARDS, 33 - 32);
    var acc1 = YMM_INT.zero();
    var acc2 = YMM_INT.zero();
    var acc3 = YMM_INT.zero();
    var acc4 = YMM_INT.zero();
    for (int i = data.length; i - 4 * YMM_INT.length() >= 0; i -= YMM_INT.length() * 4) {
      acc1 = acc1.add(coefficients1.mul(YMM_INT.fromArray(data, i - YMM_INT.length())));
      acc2 = acc2.add(coefficients2.mul(YMM_INT.fromArray(data, i - 2 * YMM_INT.length())));
      acc3 = acc3.add(coefficients3.mul(YMM_INT.fromArray(data, i - 3 * YMM_INT.length())));
      acc4 = acc4.add(coefficients4.mul(YMM_INT.fromArray(data, i - 4 * YMM_INT.length())));
      coefficients1 = coefficients1.mul(next);
      coefficients2 = coefficients2.mul(next);
      coefficients3 = coefficients3.mul(next);
      coefficients4 = coefficients4.mul(next);
    }
    return acc1.add(acc2).add(acc3).add(acc4).addAll() + coefficients1.get(7);
  }
```

The implementation above does not handle arbitrary length input, but the input could either be padded with zeroes (see this <a href="https://www.cl.cam.ac.uk/~vp331/papers/pslp_cgo2015.pdf" rel="noopener" target="_blank">paper</a> on padded SLP autovectorisation) or followed by a post loop. It produces the same output as `Arrays.hashCode`, so how much faster is it?

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<tbody><tr>
<th>Benchmark</th>
<th>(size)</th>
<th>Mode</th>
<th>Cnt</th>
<th>Score</th>
<th>Error</th>
<th>Units</th>
</tr>
<tr>
<td>arraysHashCode</td>
<td>1024</td>
<td>thrpt</td>
<td>20</td>
<td>1095.089</td>
<td>3.980</td>
<td>ops/ms</td>
</tr>
<tr>
<td>arraysHashCode</td>
<td>65536</td>
<td>thrpt</td>
<td>20</td>
<td>16.963</td>
<td>0.130</td>
<td>ops/ms</td>
</tr>
<tr>
<td>hashCodeAutoVectorised</td>
<td>1024</td>
<td>thrpt</td>
<td>20</td>
<td>3716.853</td>
<td>18.025</td>
<td>ops/ms</td>
</tr>
<tr>
<td>hashCodeAutoVectorised</td>
<td>65536</td>
<td>thrpt</td>
<td>20</td>
<td>57.265</td>
<td>0.907</td>
<td>ops/ms</td>
</tr>
<tr>
<td>polynomialHashCode</td>
<td>1024</td>
<td>thrpt</td>
<td>20</td>
<td>2623.090</td>
<td>7.920</td>
<td>ops/ms</td>
</tr>
<tr>
<td>polynomialHashCode</td>
<td>65536</td>
<td>thrpt</td>
<td>20</td>
<td>39.344</td>
<td>0.238</td>
<td>ops/ms</td>
</tr>
<tr>
<td>polynomialHashCodeUnrolled</td>
<td>1024</td>
<td>thrpt</td>
<td>20</td>
<td>8266.119</td>
<td>34.480</td>
<td>ops/ms</td>
</tr>
<tr>
<td>polynomialHashCodeUnrolled</td>
<td>65536</td>
<td>thrpt</td>
<td>20</td>
<td>131.196</td>
<td>6.234</td>
<td>ops/ms</td>
</tr>
</tbody></table>
</div>

So there really is absolutely nothing wrong with the algorithm from a performance perspective, but the implementation can be improved vastly (~8x). It seems that the tools required for JDK engineers and users alike to make optimisations like these are in the pipeline!

What about byte arrays? One obstacle to vectorisation is that to implement the JDK algorithm strictly, the bytes must accumulate into 32 bit values, which means that the lanes need to widen, so the contents of a single vector register of bytes would need to fan out to four vector registers of integers. This would be achievable by loading vectors at eight byte offsets and permuting the first eight bytes of each vector into every fourth position, but this is quite convoluted.

Peter demonstrates that reinterpreting four bytes as an integer doesn't necessarily degrade the hash distribution, and may even improve it, so I used the same trick: rebracketing a `ByteVector` to an `IntVector` to produce the "wrong" result, but a reasonable hash code nonetheless. A nice feature of the Vector API is allowing this kind of reinterpretation without resorting to `Unsafe`, via `Vector.rebracket`.

```java
  public int hashCodeVectorAPINoDependencies() {
    var next = YMM_INT.broadcast(POWERS_OF_31[8]);
    var coefficients1 = YMM_INT.fromArray(POWERS_OF_31, 0);
    var coefficients2 = coefficients1.mul(next);
    var coefficients3 = coefficients2.mul(next);
    var coefficients4 = coefficients3.mul(next);
    next = next.mul(next);
    next = next.mul(next);
    var acc1 = YMM_INT.zero();
    var acc2 = YMM_INT.zero();
    var acc3 = YMM_INT.zero();
    var acc4 = YMM_INT.zero();
    for (int i = 0; i < data.length; i += YMM_BYTE.length() * 4) {
      acc1 = acc1.add(coefficients1.mul(YMM_BYTE.fromArray(data, i).rebracket(YMM_INT)));
      acc2 = acc2.add(coefficients2.mul(YMM_BYTE.fromArray(data, i + YMM_BYTE.length()).rebracket(YMM_INT)));
      acc3 = acc3.add(coefficients3.mul(YMM_BYTE.fromArray(data, i + 2 * YMM_BYTE.length()).rebracket(YMM_INT)));
      acc4 = acc4.add(coefficients4.mul(YMM_BYTE.fromArray(data, i + 3 * YMM_BYTE.length()).rebracket(YMM_INT)));
      coefficients1 = coefficients1.mul(next);
      coefficients2 = coefficients2.mul(next);
      coefficients3 = coefficients3.mul(next);
      coefficients4 = coefficients4.mul(next);
    }
    return acc1.add(acc2).add(acc3).add(acc4).addAll();
  }
```

Owing to its use of better tools yet to be released, this version is many times faster than either the JDK implementation or Peter's. 

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<tbody><tr>
<th>Benchmark</th>
<th>(size)</th>
<th>Mode</th>
<th>Cnt</th>
<th>Score</th>
<th>Error</th>
<th>Units</th>
</tr>
<tr>
<td>arraysHashCode</td>
<td>128</td>
<td>thrpt</td>
<td>20</td>
<td>8897.392</td>
<td>220.582</td>
<td>ops/ms</td>
</tr>
<tr>
<td>arraysHashCode</td>
<td>256</td>
<td>thrpt</td>
<td>20</td>
<td>4286.621</td>
<td>156.794</td>
<td>ops/ms</td>
</tr>
<tr>
<td>arraysHashCode</td>
<td>512</td>
<td>thrpt</td>
<td>20</td>
<td>2024.858</td>
<td>72.030</td>
<td>ops/ms</td>
</tr>
<tr>
<td>arraysHashCode</td>
<td>1024</td>
<td>thrpt</td>
<td>20</td>
<td>1002.173</td>
<td>39.917</td>
<td>ops/ms</td>
</tr>
<tr>
<td>hashCodeVectorAPINoDependencies</td>
<td>128</td>
<td>thrpt</td>
<td>20</td>
<td>88395.374</td>
<td>3369.397</td>
<td>ops/ms</td>
</tr>
<tr>
<td>hashCodeVectorAPINoDependencies</td>
<td>256</td>
<td>thrpt</td>
<td>20</td>
<td>64799.697</td>
<td>1035.175</td>
<td>ops/ms</td>
</tr>
<tr>
<td>hashCodeVectorAPINoDependencies</td>
<td>512</td>
<td>thrpt</td>
<td>20</td>
<td>48248.967</td>
<td>864.728</td>
<td>ops/ms</td>
</tr>
<tr>
<td>hashCodeVectorAPINoDependencies</td>
<td>1024</td>
<td>thrpt</td>
<td>20</td>
<td>27429.025</td>
<td>916.850</td>
<td>ops/ms</td>
</tr>
<tr>
<td>hashCodeVectorAPIDependencies</td>
<td>128</td>
<td>thrpt</td>
<td>20</td>
<td>96679.811</td>
<td>316.470</td>
<td>ops/ms</td>
</tr>
<tr>
<td>hashCodeVectorAPIDependencies</td>
<td>256</td>
<td>thrpt</td>
<td>20</td>
<td>52140.582</td>
<td>1825.173</td>
<td>ops/ms</td>
</tr>
<tr>
<td>hashCodeVectorAPIDependencies</td>
<td>512</td>
<td>thrpt</td>
<td>20</td>
<td>26327.195</td>
<td>492.730</td>
<td>ops/ms</td>
</tr>
<tr>
<td>hashCodeVectorAPIDependencies</td>
<td>1024</td>
<td>thrpt</td>
<td>20</td>
<td>10929.500</td>
<td>351.732</td>
<td>ops/ms</td>
</tr>
<tr>
<td>nativeHashCode</td>
<td>128</td>
<td>thrpt</td>
<td>20</td>
<td>38799.185</td>
<td>188.636</td>
<td>ops/ms</td>
</tr>
<tr>
<td>nativeHashCode</td>
<td>256</td>
<td>thrpt</td>
<td>20</td>
<td>17438.536</td>
<td>257.168</td>
<td>ops/ms</td>
</tr>
<tr>
<td>nativeHashCode</td>
<td>512</td>
<td>thrpt</td>
<td>20</td>
<td>7041.815</td>
<td>209.817</td>
<td>ops/ms</td>
</tr>
<tr>
<td>nativeHashCode</td>
<td>1024</td>
<td>thrpt</td>
<td>20</td>
<td>3217.187</td>
<td>96.379</td>
<td>ops/ms</td>
</tr>
</tbody></table>
</div>


<blockquote><a href="https://github.com/richardstartin/vectorbenchmarks/tree/master/src/main/java/com/openkappa/panama/vectorbenchmarks" rel="noopener" target="_blank">Benchmark source code</a>
</blockquote>


<blockquote>Paul Sandoz discussed this topic at Oracle Code One 2018 (<a href="https://static.rainfocus.com/oracle/oow18/sess/1525822677955001tLqU/PF/codeone18-vector-API-DEV5081_1540354883936001Q3Sv.pdf" rel="noopener" target="_blank">Slides</a>)
<iframe width="560" height="315" src="https://www.youtube.com/embed/PnVw1uFxSyw" frameborder="0" allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
</blockquote>
