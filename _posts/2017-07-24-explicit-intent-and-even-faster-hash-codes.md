---
ID: 6964
post_title: >
  Explicit Intent and Even Faster Hash
  Codes
author: Richard Startin
post_excerpt: ""
layout: post
permalink: >
  http://richardstartin.uk/explicit-intent-and-even-faster-hash-codes/
published: true
post_date: 2017-07-24 20:39:28
---
I wrote a <a href="http://richardstartin.uk/still-true-in-java-9-handwritten-hash-codes-are-faster/" target="_blank">post </a>recently about how disappointed I was that the optimiser couldn't outsmart some <a href="http://lemire.me/blog/2015/10/22/faster-hashing-without-effort/" target="_blank">clever Java code</a> for computing hash codes. Well, here's a faster hash code along the same lines.

The hash code implemented in <code>Arrays.hashCode</code> is a polynomial hash, it applies to any data type with a positional interpretation. It takes the general form $latex \sum_{i=0}^{n}x_{i}31^{n - i}$ where $latex x_0 = 1$. In other words, it's a dot product of the elements of the array and some powers of 31. Daniel Lemire's implementation makes it explicit to the optimiser, in a way it won't otherwise infer, that this operation is data parallel. If it's really just a dot product it can be made even more obvious at the cost of a loss of flexibility.

Imagine you are processing fixed or limited length strings (VARCHAR(255) or an URL) or coordinates of a space of fixed dimension. Then you could pre-compute the coefficients in an array and write the hash code explicitly as a dot product. Java 9 uses AVX instructions for dot products, so it should be very fast.

<code class="language-java">
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
</code>

This is really explicit, unambiguously parallelisable, and the results are remarkable.

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><th>Benchmark</th>
<th>Mode</th>
<th>Threads</th>
<th>Samples</th>
<th>Score</th>
<th>Score Error (99.9%)</th>
<th>Unit</th>
<th>Param: size</th>
</thead>
<tbody><tr>
<td>HashCode.BuiltIn</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">10.323026</td>
<td align="right">0.223614</td>
<td>ops/us</td>
<td align="right">100</td>
</tr>
<tr>
<td>HashCode.BuiltIn</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.959246</td>
<td align="right">0.038900</td>
<td>ops/us</td>
<td align="right">1000</td>
</tr>
<tr>
<td>HashCode.BuiltIn</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.096005</td>
<td align="right">0.001836</td>
<td>ops/us</td>
<td align="right">10000</td>
</tr>
<tr>
<td>HashCode.FixedLength</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">20.186800</td>
<td align="right">0.297590</td>
<td>ops/us</td>
<td align="right">100</td>
</tr>
<tr>
<td>HashCode.FixedLength</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">2.314187</td>
<td align="right">0.082867</td>
<td>ops/us</td>
<td align="right">1000</td>
</tr>
<tr>
<td>HashCode.FixedLength</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.227090</td>
<td align="right">0.005377</td>
<td>ops/us</td>
<td align="right">10000</td>
</tr>
<tr>
<td>HashCode.Unrolled</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">13.250821</td>
<td align="right">0.752609</td>
<td>ops/us</td>
<td align="right">100</td>
</tr>
<tr>
<td>HashCode.Unrolled</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.503368</td>
<td align="right">0.058200</td>
<td>ops/us</td>
<td align="right">1000</td>
</tr>
<tr>
<td>HashCode.Unrolled</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.152179</td>
<td align="right">0.003541</td>
<td>ops/us</td>
<td align="right">10000</td>
</tr>
</tbody></table>
</div>

Modifying the algorithm slightly to support limited variable length arrays degrades performance slightly, but there are seemingly equivalent implementations which do much worse.

<code class="language-java">
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
</code>

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><th>Benchmark</th>
<th>Mode</th>
<th>Threads</th>
<th>Samples</th>
<th>Score</th>
<th>Score Error (99.9%)</th>
<th>Unit</th>
<th>Param: size</th>
</thead>
<tbody><tr>
<td>FixedLength</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">19.172574</td>
<td align="right">0.742637</td>
<td>ops/us</td>
<td align="right">100</td>
</tr>
<tr>
<td>FixedLength</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">2.233006</td>
<td align="right">0.115285</td>
<td>ops/us</td>
<td align="right">1000</td>
</tr>
<tr>
<td>FixedLength</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.227451</td>
<td align="right">0.012231</td>
<td>ops/us</td>
<td align="right">10000</td>
</tr>
</tbody></table>
</div>

The benchmark code is at <a href="https://github.com/richardstartin/simdbenchmarks" target="_blank">github</a>.