---
ID: 8559
title: "Tricking Java into Adding Up Arrays Faster"
author: Richard Startin
layout: post

date: 2017-08-18
---
Imagine you have an `int[]` and want to compute the sum of its elements. You could do exactly that, or, supposing your values are small enough not to overflow, you can make your loop much faster by multiplying each element by 2 inside the loop, and dividing the result by 2 at the end. This is because autovectorisation, with strength reductions to shifts and additions to boot, kicks in for loops that look like a dot product, whereas summations of arrays don't seem to be optimised at all - see this <a href="https://richardstartin.github.io/posts/how-much-algebra-does-c2-know-part-2-distributivity/" target="_blank">post</a> for an analysis. Don't believe me? Run the code at <a href="https://github.com/richardstartin/simdbenchmarks" target="_blank">github</a>.

```java
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
```

|Benchmark|Mode|Threads|Samples|Score|Score Error (99.9%)|Unit|Param: size|
|--- |--- |--- |--- |--- |--- |--- |--- |
|CropCircle|thrpt|1|10|29.922687|0.383028|ops/ms|100000|
|CropCircle|thrpt|1|10|2.065812|0.120089|ops/ms|1000000|
|NaiveSum|thrpt|1|10|26.241689|0.660850|ops/ms|100000|
|NaiveSum|thrpt|1|10|1.868644|0.244081|ops/ms|1000000|
