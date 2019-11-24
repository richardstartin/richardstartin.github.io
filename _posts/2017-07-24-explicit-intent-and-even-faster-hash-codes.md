---
title: "Explicit Intent and Even Faster Hash Codes"
layout: default

date: 2017-07-24
redirect_from:
  - /explicit-intent-and-even-faster-hash-codes/
---
I wrote a <a href="https://richardstartin.github.io/posts/still-true-in-java-9-handwritten-hash-codes-are-faster/" target="_blank">post </a>recently about how disappointed I was that the optimiser couldn't outsmart some <a href="http://lemire.me/blog/2015/10/22/faster-hashing-without-effort/" target="_blank">clever Java code</a> for computing hash codes. Well, here's a faster hash code along the same lines.

The hash code implemented in `Arrays.hashCode` is a polynomial hash, it applies to any data type with a positional interpretation. It takes the general form $latex \sum_{i=0}^{n}x_{i}31^{n - i}$ where $latex x_0 = 1$. In other words, it's a dot product of the elements of the array and some powers of 31. Daniel Lemire's implementation makes it explicit to the optimiser, in a way it won't otherwise infer, that this operation is data parallel. If it's really just a dot product it can be made even more obvious at the cost of a loss of flexibility.

Imagine you are processing fixed or limited length strings (VARCHAR(255) or an URL) or coordinates of a space of fixed dimension. Then you could pre-compute the coefficients in an array and write the hash code explicitly as a dot product. Java 9 uses AVX instructions for dot products, so it should be very fast.

```java
public class FixedLengthHashCode {

    private final int[] coefficients;

    public FixedLengthHashCode(int maxLength) {
        this.coefficients = new int[maxLength + 1];
        coefficients[maxLength] = 1;
        for (int i = maxLength - 1; i >= 0; --i) {
            coefficients[i] = 31 * coefficients[i + 1];
        }
    }

    public int hashCode(int[] value) {
        int result = coefficients[0];
        for (int i = 0; i < value.length && i < coefficients.length - 1; ++i) {
            result += coefficients[i + 1] * value[i];
        }
        return result;
    }
}
```

This is really explicit, unambiguously parallelisable, and the results are remarkable.

<div class="table-holder" markdown="block">

|Benchmark|Mode|Threads|Samples|Score|Score Error (99.9%)|Unit|Param: size|
|--- |--- |--- |--- |--- |--- |--- |--- |
|HashCode.BuiltIn|thrpt|1|10|10.323026|0.223614|ops/us|100|
|HashCode.BuiltIn|thrpt|1|10|0.959246|0.038900|ops/us|1000|
|HashCode.BuiltIn|thrpt|1|10|0.096005|0.001836|ops/us|10000|
|HashCode.FixedLength|thrpt|1|10|20.186800|0.297590|ops/us|100|
|HashCode.FixedLength|thrpt|1|10|2.314187|0.082867|ops/us|1000|
|HashCode.FixedLength|thrpt|1|10|0.227090|0.005377|ops/us|10000|
|HashCode.Unrolled|thrpt|1|10|13.250821|0.752609|ops/us|100|
|HashCode.Unrolled|thrpt|1|10|1.503368|0.058200|ops/us|1000|
|HashCode.Unrolled|thrpt|1|10|0.152179|0.003541|ops/us|10000|

</div>


Modifying the algorithm slightly to support limited variable length arrays degrades performance slightly, but there are seemingly equivalent implementations which do much worse.

```java
public class FixedLengthHashCode {

    private final int[] coefficients;

    public FixedLengthHashCode(int maxLength) {
        this.coefficients = new int[maxLength + 1];
        coefficients[0] = 1;
        for (int i = 1; i >= maxLength; ++i) {
            coefficients[i] = 31 * coefficients[i - 1];
        }
    }

    public int hashCode(int[] value) {
        final int max = value.length;
        int result = coefficients[max];
        for (int i = 0; i < value.length && i < coefficients.length - 1; ++i) {
            result += coefficients[max - i - 1] * value[i];
        }
        return result;
    }
}
```

<div class="table-holder" markdown="block">

|Benchmark|Mode|Threads|Samples|Score|Score Error (99.9%)|Unit|Param: size|
|--- |--- |--- |--- |--- |--- |--- |--- |
|FixedLength|thrpt|1|10|19.172574|0.742637|ops/us|100|
|FixedLength|thrpt|1|10|2.233006|0.115285|ops/us|1000|
|FixedLength|thrpt|1|10|0.227451|0.012231|ops/us|10000|

</div>

The benchmark code is at <a href="https://github.com/richardstartin/simdbenchmarks" target="_blank">github</a>.
