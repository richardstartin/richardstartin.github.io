---
ID: 8559
post_title: >
  Tricking Java into Adding Up Arrays
  Faster
author: Richard Startin
post_excerpt: ""
layout: post
permalink: >
  http://richardstartin.uk/tricking-java-into-adding-up-arrays-faster/
published: true
post_date: 2017-08-18 21:46:25
---
Imagine you have an <code>int[]</code> and want to compute the sum of its elements. You could do exactly that, or, supposing your values are small enough not to overflow, you can make your loop much faster by multiplying each element by 2 inside the loop, and dividing the result by 2 at the end. This is because autovectorisation, with strength reductions to shifts and additions to boot, kicks in for loops that look like a dot product, whereas summations of arrays don't seem to be optimised at all - see this <a href="http://richardstartin.uk/how-much-algebra-does-c2-know-part-2-distributivity/" target="_blank">post</a> for an analysis. Don't believe me? Run the code at <a href="https://github.com/richardstartin/simdbenchmarks" target="_blank">github</a>. 

<code class="language-java>
    @CompilerControl(CompilerControl.Mode.DONT_INLINE)
    @Benchmark
    public int NaiveSum(IntData state) {
        int value = 0;
        int[] data = state.data1;
        for (int i = 0; i < data.length; ++i) {
            value += data[i];
        }
        return value;
    }

    @CompilerControl(CompilerControl.Mode.DONT_INLINE)
    @Benchmark
    public int CropCircle(IntData state) {
        int value = 0;
        int[] data = state.data1;
        for (int i = 0; i < data.length; ++i) {
            value += 2 * data[i];
        }
        return value / 2;
    }
</code>

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><th title="Field #1">Benchmark</th>
<th>Mode</th>
<th>Threads</th>
<th>Samples</th>
<th>Score</th>
<th>Score Error (99.9%)</th>
<th>Unit</th>
<th>Param: size</th>
</thead>
<tbody><tr>
<td>CropCircle</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">29.922687</td>
<td align="right">0.383028</td>
<td>ops/ms</td>
<td align="right">100000</td>
</tr>
<tr>
<td>CropCircle</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">2.065812</td>
<td align="right">0.120089</td>
<td>ops/ms</td>
<td align="right">1000000</td>
</tr>
<tr>
<td>NaiveSum</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">26.241689</td>
<td align="right">0.660850</td>
<td>ops/ms</td>
<td align="right">100000</td>
</tr>
<tr>
<td>NaiveSum</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.868644</td>
<td align="right">0.244081</td>
<td>ops/ms</td>
<td align="right">1000000</td>
</tr>
</tbody></table>
</div>