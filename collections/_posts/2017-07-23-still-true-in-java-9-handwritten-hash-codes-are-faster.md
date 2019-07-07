---
ID: 6788
post_title: 'Still True in Java 9: Handwritten Hash Codes are Faster'
author: Richard Startin
post_excerpt: ""
layout: post
permalink: >
  http://richardstartin.uk/still-true-in-java-9-handwritten-hash-codes-are-faster/
published: true
post_date: 2017-07-23 12:37:12
---
One of the things to keep in mind with Java is that the best performance advice for one version may not apply to the next. The JVM has an optimiser which works by detecting intent in byte-code; it does a better job when the programmer is skilled enough to make that intent clear. There have been times when the optimiser has done a bad job, either through bugs or feature gaps, and compensatory idioms emerge. The value of these idioms degrades over time as the optimiser improves; a stroke of ingenuity in one version can become ritualistic nonsense in the next. It's important not to be <em>that guy</em> who fears adding strings together because it was costly a decade ago, but does it always get better, even with low hanging fruit?

I reproduced the results of an <a href="http://lemire.me/blog/2015/10/22/faster-hashing-without-effort/" target="_blank">extremely astute optimisation</a> presented in 2015 by Daniel Lemire. I was hoping to see that an improved optimiser in Java 9, having observed several cases of automatic vectorisation, would render this optimisation null. 

<h3>Hash Codes for Arrays</h3>

I encourage you to read the <a href="http://lemire.me/blog/2015/10/22/faster-hashing-without-effort/" target="_blank">original blog post</a> because it is informative, but for the sake of coherence I will summarise the key point here. <code>Arrays.hashCode</code> implements the following hash code:

<code class="language-java">
    public static int hashCode(int[] a) {
        if (a == null)
            return 0;

        int result = 1;
        for (int element : a)
            result = 31 * result + element;

        return result;
    }
</code>

This results in a good hash code, but a scalar internal representation of this code has a problem: a data dependency on the multiplication, which is slower than moving data into registers. A significant and reproducible speed up can be observed when unrolling the loop, which allows prefetching 128 bits of the array into registers before doing the slower multiplications:

<code class="language-java">
    public static int hashCode(int[] a) {
        if (a == null)
            return 0;

        int result = 1;
        int i = 0;
        for (; i + 3 < a.length; i += 4) {
            result = 31 * 31 * 31 * 31 * result
                   + 31 * 31 * 31 * a[i]
                   + 31 * 31 * a[i + 1]
                   + 31 * a[i + 2]
                   + a[i + 3];
        }
        for (; i < a.length; i++) {
            result = 31 * result + a[i];
        }
        return result;
    }
</code>

The improvement in performance from this simple change can be confirmed with Java 8 by running a simple benchmark. 

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
<td>BuiltIn</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">9.537736</td>
<td align="right">0.382617</td>
<td>ops/us</td>
<td align="right">100</td>
</tr>
<tr>
<td>BuiltIn</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.804620</td>
<td align="right">0.103037</td>
<td>ops/us</td>
<td align="right">1000</td>
</tr>
<tr>
<td>BuiltIn</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.092297</td>
<td align="right">0.003947</td>
<td>ops/us</td>
<td align="right">10000</td>
</tr>
<tr>
<td>Unrolled</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">14.974398</td>
<td align="right">0.628522</td>
<td>ops/us</td>
<td align="right">100</td>
</tr>
<tr>
<td>Unrolled</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.514986</td>
<td align="right">0.035759</td>
<td>ops/us</td>
<td align="right">1000</td>
</tr>
<tr>
<td>Unrolled</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.137408</td>
<td align="right">0.010200</td>
<td>ops/us</td>
<td align="right">10000</td>
</tr>
</tbody></table>
</div>

The performance improvement is so obvious, and the change so easy to make, that one wonders why JVM vendors didn't make the change themselves.

<h3>Java 9: Universally Better Automatic Optimisations?</h3>

As the comments on the blog post suggest, this is a prime candidate for vectorisation. Auto-vectorisation is a <em>thing</em> in Java 9. Using intrinsics or code clean enough to express intent clearly, you can really expect to see good usage of SIMD in Java 9. I was really expecting the situation to reverse in Java 9; but it doesn't.

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
<td>BuiltIn</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">9.822568</td>
<td align="right">0.381087</td>
<td>ops/us</td>
<td align="right">100</td>
</tr>
<tr>
<td>BuiltIn</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.949273</td>
<td align="right">0.024021</td>
<td>ops/us</td>
<td align="right">1000</td>
</tr>
<tr>
<td>BuiltIn</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.093171</td>
<td align="right">0.004502</td>
<td>ops/us</td>
<td align="right">10000</td>
</tr>
<tr>
<td>Unrolled</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">13.762617</td>
<td align="right">0.440135</td>
<td>ops/us</td>
<td align="right">100</td>
</tr>
<tr>
<td>Unrolled</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.501106</td>
<td align="right">0.094897</td>
<td>ops/us</td>
<td align="right">1000</td>
</tr>
<tr>
<td>Unrolled</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.139963</td>
<td align="right">0.011487</td>
<td>ops/us</td>
<td align="right">10000</td>
</tr>
</tbody></table>
</div>

This is a still a smart optimisation two years later, but it offends my sensibilities in the same way hints do in SQL - a layer of abstraction has been punctured. I will have to try again in Java 10.

<blockquote>Better gains are available when <a href="http://richardstartin.uk/explicit-intent-and-even-faster-hash-codes/">precomputing the coefficients is possible</a>.</blockquote>