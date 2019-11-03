---
ID: 10056
title: >
  Spliterator Characteristics and
  Performance
author: Richard Startin
post_excerpt: ""
layout: default

published: true
date: 2017-12-14 18:00:23
---
The streams API has been around for a while now, and I'm a big fan of it. It allows for a clean declarative programming style, which permits various optimisations to occur, and keeps the pastafarians at bay. I also think the `Stream` is the perfect abstraction for data interchange across API boundaries. This is partly because a `Stream` is lazy, meaning you don't need to pay for consumption until you actually need to, and partly because a `Stream` can only be used once and there can be no ambiguity about ownership. If you supply a `Stream` to an API, you must expect that it has been used and so must discard it. This almost entirely eradicates defensive copies and can mean that no intermediate data structures need ever exist. Despite my enthusiasm for this abstraction, there's some weirdness in this API when you scratch beneath surface.

I wanted to find a way to quickly run length encode an `IntStream` and found it difficult to make this code as fast as I'd like it to be. The code is too slow because it's necessary to inspect each `int`, even when there is enough context available to potentially apply optimisations such as skipping over ranges. It's likely that I am experiencing the friction of treating `Stream` as a data interchange format, which wasn't one of its design goals, but this led me to investigate spliterator characteristics (there is no contiguous characteristic, which could speed up RLE greatly) and their relationship with performance.

<h3>Spliterator Characteristics</h3>

Streams have <em>spliterators</em>, which control iteration and splitting behaviour. If you want to process a stream in parallel, it is the spliterator which dictates how to split the stream, if possible. There's more to a spliterator than parallel execution though, and each single threaded execution can be optimised based on the characteristics bit mask. The different characteristics are as follows:
<ul>
	<li>`ORDERED` promises that there is an order. For instance, `trySplit` is guaranteed to give a prefix of elements.</li>
        <li>`DISTINCT` a promise that each element in the stream is unique.</li>
        <li>`SORTED` a promise that the stream is already sorted.</li>
        <li>`SIZED` promises the size of the stream is known. This is not true when a call to `iterate` generates the stream.</li>
        <li>`NONNULL` promises that no elements in the stream are null.</li>
        <li>`IMMUTABLE` promises the underlying data will not change.</li>
        <li>`CONCURRENT` promises that the underlying data can be modified concurrently. Must not also be `IMMUTABLE`.</li>
        <li>`SUBSIZED` promises that the sizes of splits are known, must also be `SIZED`.</li>
</ul>

There's <a href="https://docs.oracle.com/javase/9/docs/api/java/util/Spliterator.html" rel="noopener" target="_blank">javadoc</a> for all of these flags, which should be your point of reference, and you need to read it because you wouldn't guess based on relative performance. For instance, `IntStream.range(inclusive, exclusive)` creates an `RangeIntSpliterator` with the characteristics `ORDERED | SIZED | SUBSIZED | IMMUTABLE | NONNULL | DISTINCT | SORTED`. This means that this stream has no duplicates, no nulls, is already sorted in natural order, the size is known, and it will be chunked deterministically. The data and the iteration order never change, and if we split it, we will always get the same  first chunk. So these code snippets should have virtually the same performance:

```java
    @Benchmark
    public long countRange() {
        return IntStream.range(0, size).count();
    }

    @Benchmark
    public long countRangeDistinct() {
        return IntStream.range(0, size).distinct().count();
    }
```

This is completely at odds with observations. Even though the elements are already distinct, and metadata exists to support this, requesting the distinct elements decimates performance.

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
<td>countRange</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">49.465729</td>
<td align="right">1.804123</td>
<td>ops/us</td>
<td align="right">262144</td>
</tr>
<tr>
<td>countRangeDistinct</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.000395</td>
<td align="right">0.000002</td>
<td>ops/us</td>
<td align="right">262144</td>
</tr>
</tbody></table>
</div>

It turns out this is because `IntStream.distinct` has a one-size-fits-all implementation which completely ignores the `DISTINCT` characteristic, and goes ahead and boxes the entire range.

```java
    // from java.util.stream.IntPipeline
    @Override
    public final IntStream distinct() {
        // While functional and quick to implement, this approach is not very efficient.
        // An efficient version requires an int-specific map/set implementation.
        return boxed().distinct().mapToInt(i -> i);
    }
```

There is even more observable weirdness. If we wanted to calculate the sum of the first 1000 natural numbers, these two snippets should have the same performance. Requesting what should be a redundant sort doubles the throughput.

```java
    @Benchmark 
    public long headSum() {
        return IntStream.range(0, size).limit(1000).sum();
    }

    @Benchmark
    public long sortedHeadSum() {
        return IntStream.range(0, size).sorted().limit(1000).sum();
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
<td>headSum</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.209763</td>
<td align="right">0.002478</td>
<td>ops/us</td>
<td align="right">262144</td>
</tr>
<tr>
<td>sortedHeadSum</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.584227</td>
<td align="right">0.006004</td>
<td>ops/us</td>
<td align="right">262144</td>
</tr>
</tbody></table>
</div>

In fact, you would have a hard time finding a relationship between Spliterator characteristics and performance, but you can see cases of characteristics driving optimisations if you look hard enough, such as in `IntStream.count`, where the `SIZED` characteristic is used.

```java
    // see java.util.stream.ReduceOps.makeIntCounting
    @Override
    public <P_IN> Long evaluateSequential(PipelineHelper<Integer> helper, Spliterator<P_IN> spliterator) {
        if (StreamOpFlag.SIZED.isKnown(helper.getStreamAndOpFlags()))
            return spliterator.getExactSizeIfKnown();
        return super.evaluateSequential(helper, spliterator);
    }
```

This is a measurably worthwhile optimisation, when benchmarked against the unsized spliterator created by `IntStream.iterate`:

```java
    @Benchmark
    public long countIterator() {
        return IntStream.iterate(0, i -> i < size, i -> i + 1).count();
    }

    @Benchmark
    public long countRange() {
        return IntStream.range(0, size).count();
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
<td>countIterator</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.001198</td>
<td align="right">0.001629</td>
<td>ops/us</td>
<td align="right">262144</td>
</tr>
<tr>
<td>countRange</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">43.166065</td>
<td align="right">4.628715</td>
<td>ops/us</td>
<td align="right">262144</td>
</tr>
</tbody></table>
</div>

What about `limit`, that's supposed to be useful for speeding up streams by limiting the amount of work done? Unfortunately not. It actually makes things potentially much worse. In `SliceOps.flags`, we see it will actually disable `SIZED` operations:

```java
    //see java.util.stream.SliceOps
    private static int flags(long limit) {
        return StreamOpFlag.NOT_SIZED | ((limit != -1) ? StreamOpFlag.IS_SHORT_CIRCUIT : 0);
    }
```

This has a significant effect on performance, as can be seen in the following benchmark:

```java
    @Benchmark
    public long countRange() {
        return IntStream.range(0, size).count();
    }

    @Benchmark
    public long countHalfRange() {
        return IntStream.range(0, size).limit(size / 2).count();
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
<td>countHalfRange</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.003632</td>
<td align="right">0.003363</td>
<td>ops/us</td>
<td align="right">262144</td>
</tr>
<tr>
<td>countRange</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">44.859998</td>
<td align="right">6.191411</td>
<td>ops/us</td>
<td align="right">262144</td>
</tr>
</tbody></table>
</div>

It's almost as if there were grand plans involving characteristic based optimisation, and perhaps time ran out (`IntStream.distinct` has a very apologetic comment) or others were better on paper than in reality. In any case, it looks like they aren't as influential as you might expect. Given that the relationship between the characteristics which exist and performance is flaky at best, it's unlikely that a new one would get implemented, but I think the characteristic `CONTIGUOUS` is missing.