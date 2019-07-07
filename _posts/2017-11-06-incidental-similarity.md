---
ID: 9874
post_title: Incidental Similarity
author: Richard Startin
post_excerpt: ""
layout: post
permalink: >
  http://richardstartin.uk/incidental-similarity/
published: true
post_date: 2017-11-06 12:19:49
---
I recently saw an interesting class, <a href="https://github.com/apache/arrow/blob/master/java/vector/src/main/java/org/apache/arrow/vector/BitVector.java" rel="noopener" target="_blank">BitVector</a>, in Apache Arrow, which represents a column of bits, providing minimal or zero copy distribution. The implementation is similar to a bitset but backed by a `byte[]` rather than a `long[]`. Given the coincidental similarity in <em>implementation</em>, it's tempting to look at this, extend its interface and try to use it as a general purpose, distributed bitset. Could this work? Why not just implement some extra methods? Fork it on Github!

This post details the caveats of trying to adapt an abstraction beyond its intended purpose; in a scenario where generic bitset capabilities are added to BitVector without due consideration, examined through the lens of performance. This runs into the observable effect of word widening on throughput, given the constraints imposed by <a href="https://docs.oracle.com/javase/specs/jls/se8/html/jls-15.html#jls-15.22" rel="noopener" target="_blank">JLS 15.22</a>. In the end, the only remedy is to use a `long[]`, sacrificing the original zero copy design goal. I hope this is a fairly self-contained example of how uncontrolled adaptation can be hostile to the original design goals: having the source code isn't enough reason to modify it.

<h3>Checking bits</h3>

How fast is it to check if the bit at index `i` is set or not? BitVector implements this functionality, and was designed for it. This can be measured by JMH by generating a random `long[]` and creating a `byte[]` 8x longer with identical bits. The throughput of checking the value of the bit at random indices can be measured. It turns out that if all you want to do is access bits, `byte[]` isn't such a bad choice, and if those bytes are coming directly from the network, it could even be a great choice. I ran the benchmark below and saw that the two operations are similar (within measurement error).

```java
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@State(Scope.Thread)
public class BitSet {

    @Param({"1024", "2048", "4096", "8192"})
    int size;

    private long[] leftLongs;
    private long[] rightLongs;
    private long[] differenceLongs;
    private byte[] leftBytes;
    private byte[] rightBytes;
    private byte[] differenceBytes;

    @Setup(Level.Trial)
    public void init() {
        this.leftLongs = createLongArray(size);
        this.rightLongs = createLongArray(size);
        this.differenceLongs = new long[size];
        this.leftBytes = makeBytesFromLongs(leftLongs);
        this.rightBytes = makeBytesFromLongs(rightLongs);
        this.differenceBytes = new byte[size * 8];
    }

    @Benchmark
    public boolean CheckBit_LongArray() {
        int index = index();
        return (leftLongs[index >>> 6] & (1L << index)) != 0;
    }

    @Benchmark
    public boolean CheckBit_ByteArray() {
        int index = index();
        return ((leftBytes[index >>> 3] & 0xFF) & (1 << (index & 7))) != 0;
    }

    private int index() {
        return ThreadLocalRandom.current().nextInt(size * 64);
    }

    private static byte[] makeBytesFromLongs(long[] array) {
        byte[] bytes = new byte[8 * array.length];
        for (int i = 0; i < array.length; ++i) {
            long word = array[i];
            bytes[8 * i + 7] = (byte) word;
            bytes[8 * i + 6] = (byte) (word >>> 8);
            bytes[8 * i + 5] = (byte) (word >>> 16);
            bytes[8 * i + 4] = (byte) (word >>> 24);
            bytes[8 * i + 3] = (byte) (word >>> 32);
            bytes[8 * i + 2] = (byte) (word >>> 40);
            bytes[8 * i + 1] = (byte) (word >>> 48);
            bytes[8 * i]     = (byte) (word >>> 56);
        }
        return bytes;
    }
}
```

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th>Benchmark</th>
<th>Mode</th>
<th>Threads</th>
<th>Samples</th>
<th>Score</th>
<th>Score Error (99.9%)</th>
<th>Unit</th>
<th>Param: size</th>
</tr></thead>
<tbody><tr>
<td>CheckBit_ByteArray</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">174.421170</td>
<td align="right">1.583275</td>
<td>ops/us</td>
<td align="right">1024</td>
</tr>
<tr>
<td>CheckBit_ByteArray</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">173.938408</td>
<td align="right">1.445796</td>
<td>ops/us</td>
<td align="right">2048</td>
</tr>
<tr>
<td>CheckBit_ByteArray</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">172.522190</td>
<td align="right">0.815596</td>
<td>ops/us</td>
<td align="right">4096</td>
</tr>
<tr>
<td>CheckBit_ByteArray</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">167.550530</td>
<td align="right">1.677091</td>
<td>ops/us</td>
<td align="right">8192</td>
</tr>
<tr>
<td>CheckBit_LongArray</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">171.639695</td>
<td align="right">0.934494</td>
<td>ops/us</td>
<td align="right">1024</td>
</tr>
<tr>
<td>CheckBit_LongArray</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">169.703960</td>
<td align="right">2.427244</td>
<td>ops/us</td>
<td align="right">2048</td>
</tr>
<tr>
<td>CheckBit_LongArray</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">169.333360</td>
<td align="right">1.649654</td>
<td>ops/us</td>
<td align="right">4096</td>
</tr>
<tr>
<td>CheckBit_LongArray</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">166.518375</td>
<td align="right">0.815433</td>
<td>ops/us</td>
<td align="right">8192</td>
</tr>
</tbody></table>
</div>

To support this functionality, there's no reason to choose either way, and it must be very appealing to use bytes as they are delivered from the network, avoiding copying costs. Given that for a database column, this is the only operation needed, and Apache Arrow has a stated aim to copy data as little as possible, this seems like quite a good decision.

<h3>Logical Conjugations</h3>

But what happens if you try to add a logical operation to BitVector, such as an XOR? We need to handle the fact that `byte`s are <em>signed</em> and their sign bit must be preserved in promotion, according to the <a href="https://docs.oracle.com/javase/specs/jls/se8/html/jls-5.html#jls-5.1.2" rel="noopener" target="_blank">JLS</a>. This would break the bitset, so extra operations are required to keep the 8th bit in its right place. With the widening and its associated workarounds, suddenly the `byte[]` is a much poorer choice than a `long[]`, and it shows in benchmarks.

```java
    @Benchmark
    public void Difference_ByteArray(Blackhole bh) {
        for (int i = 0; i < leftBytes.length && i < rightBytes.length; ++i) {
            differenceBytes[i] = (byte)((leftBytes[i] & 0xFF) ^ (rightBytes[i] & 0xFF));
        }
        bh.consume(differenceBytes);
    }

    @Benchmark
    public void Difference_LongArray(Blackhole bh) {
        for (int i = 0; i < leftLongs.length && i < rightLongs.length; ++i) {
            differenceLongs[i] = leftLongs[i] ^ rightLongs[i];
        }
        bh.consume(differenceLongs);
    }
```

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th>Benchmark</th>
<th>Mode</th>
<th>Threads</th>
<th>Samples</th>
<th>Score</th>
<th>Score Error (99.9%)</th>
<th>Unit</th>
<th>Param: size</th>
</tr></thead>
<tbody><tr>
<td>Difference_ByteArray</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.805872</td>
<td align="right">0.038644</td>
<td>ops/us</td>
<td align="right">1024</td>
</tr>
<tr>
<td>Difference_ByteArray</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.391705</td>
<td align="right">0.017453</td>
<td>ops/us</td>
<td align="right">2048</td>
</tr>
<tr>
<td>Difference_ByteArray</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.190102</td>
<td align="right">0.008580</td>
<td>ops/us</td>
<td align="right">4096</td>
</tr>
<tr>
<td>Difference_ByteArray</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.169104</td>
<td align="right">0.015086</td>
<td>ops/us</td>
<td align="right">8192</td>
</tr>
<tr>
<td>Difference_LongArray</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">2.450659</td>
<td align="right">0.094590</td>
<td>ops/us</td>
<td align="right">1024</td>
</tr>
<tr>
<td>Difference_LongArray</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.047330</td>
<td align="right">0.016898</td>
<td>ops/us</td>
<td align="right">2048</td>
</tr>
<tr>
<td>Difference_LongArray</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.546286</td>
<td align="right">0.014211</td>
<td>ops/us</td>
<td align="right">4096</td>
</tr>
<tr>
<td>Difference_LongArray</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.277378</td>
<td align="right">0.015663</td>
<td>ops/us</td>
<td align="right">8192</td>
</tr>
</tbody></table>
</div>

This is a fairly crazy slow down. Why? You need to look at the assembly generated in each case. For `long[]` it's demonstrable that <a href="http://richardstartin.uk/vectorised-logical-operations-in-java-9/" rel="noopener" target="_blank">logical operations do vectorise</a>. The JLS, specifically section <a href="https://docs.oracle.com/javase/specs/jls/se8/html/jls-15.html#jls-15.22" rel="noopener" target="_blank">15.22</a>, doesn't really give the `byte[]` implementation a chance. It states that for logical operations, sub `dword` primitive types must be promoted or widened before the operation. This means that if one were to try to implement this operation with, say AVX2, using 256 bit `ymmword`s each consisting of 16 `byte`s, then each `ymmword` would have to be inflated by a factor of four: it gets complicated quickly, given this constraint.  Despite that complexity, I was surprised to see that C2 does use 128 bit `xmmword`s, but it's not as fast as using the full 256 bit registers available. This can be seen by printing out the emitted assembly like normal.

<pre>
movsxd  r10,ebx     

vmovq   xmm2,mmword ptr [rsi+r10+10h]

vpxor   xmm2,xmm2,xmmword ptr [r8+r10+10h]

vmovq   mmword ptr [rax+r10+10h],xmm2
</pre>