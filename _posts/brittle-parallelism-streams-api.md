---
title: Brittle Parallelism in the Streams API
layout: post
tags: java
date: 2021-04-05
---

I wrote [a post](/posts/spliterator-characteristics-and-performance) over 
three years ago about how the internal treatment of `Spliterator` characteristics can lead to very surprising performance anomalies.
For instance, if you start with an already `DISTINCT` `IntStream`, and then call `.distinct()`, the `DISTINCT` characteristic was ignored, leading to the boxing and deduplication of the elements of the `IntStream`.
What's worse is that if the `IntStream` started off with the `SIZED` characteristic, this would be forgotten so downstream operations might be a lot slower than if the `SIZED` characteristic had propagated downstream.
This observation was captured in [JDK-8193641](https://bugs.openjdk.java.net/browse/JDK-8193641), but it was deprioritised as the test case was deemed to be contrived by Stuart Marks.
In the spirit of the resurrection of things which came to be in December, I thought it was worth looking at this again briefly to highlight another odd consequence of not carefully propagating characteristics down the pipeline.

1. TOC
{:toc}

## `SUBSIZED`
The `SUBSIZED` characteristic promises that the operation `Spliterator::trySplit` is constant time, so can be [sliced](https://github.com/openjdk/jdk/blob/05a764f4ffb8030d6b768f2d362c388e5aabd92d/src/java.base/share/classes/java/util/stream/SliceOps.java#L76).
This property is useful for evaluating parallel tasks, because it means a faster evaluation strategy can be used, as outlined in the source code below.

```java
            @Override
            <P_IN> Node<T> opEvaluateParallel(PipelineHelper<T> helper,
                                              Spliterator<P_IN> spliterator,
                                              IntFunction<T[]> generator) {
                long size = helper.exactOutputSizeIfKnown(spliterator);
                if (size > 0 && spliterator.hasCharacteristics(Spliterator.SUBSIZED)) {
                    // Because the pipeline is SIZED the slice spliterator
                    // can be created from the source, this requires matching
                    // to shape of the source, and is potentially more efficient
                    // than creating the slice spliterator from the pipeline
                    // wrapping spliterator
                    Spliterator<P_IN> s = sliceSpliterator(helper.getSourceShape(), spliterator, skip, limit);
                    return Nodes.collect(helper, s, true, generator);
                } else if (!StreamOpFlag.ORDERED.isKnown(helper.getStreamAndOpFlags())) {
                    Spliterator<T> s =  unorderedSkipLimitSpliterator(
                            helper.wrapSpliterator(spliterator),
                            skip, limit, size);
                    // Collect using this pipeline, which is empty and therefore
                    // can be used with the pipeline wrapping spliterator
                    // Note that we cannot create a slice spliterator from
                    // the source spliterator if the pipeline is not SIZED
                    return Nodes.collect(this, s, true, generator);
                }
                else {
                    return new SliceTask<>(this, helper, spliterator, generator, skip, limit).
                            invoke();
                }
            }
```
[Source](https://github.com/openjdk/jdk/blob/05a764f4ffb8030d6b768f2d362c388e5aabd92d/src/java.base/share/classes/java/util/stream/SliceOps.java#L155)

When you create a stream from most `Collection`s, you get an `IteratorSpliterator`. If the collection is non-concurrent, the stream is automatically `SUBSIZED`.

```java
        public IteratorSpliterator(Collection<? extends T> collection, int characteristics) {
            this.collection = collection;
            this.it = null;
            this.characteristics = (characteristics & Spliterator.CONCURRENT) == 0
                                   ? characteristics | Spliterator.SIZED | Spliterator.SUBSIZED
                                   : characteristics;
        }
```
[Source](https://github.com/openjdk/jdk/blob/05a764f4ffb8030d6b768f2d362c388e5aabd92d/src/java.base/share/classes/java/util/Spliterators.java#L1710)

## `SUBSIZED` gets lost in translation

The problem is that there are various innocuous ways to lose the `SUBSIZED` characterstic.
For instance, if you call `.distinct()` or `.sorted()`, the call is delegated to `DistinctOps::makeRef` ([source](https://github.com/openjdk/jdk/blob/05a764f4ffb8030d6b768f2d362c388e5aabd92d/src/java.base/share/classes/java/util/stream/DistinctOps.java#L54)) and `SortedOps::makeRef` ([source](https://github.com/openjdk/jdk/blob/05a764f4ffb8030d6b768f2d362c388e5aabd92d/src/java.base/share/classes/java/util/stream/SortedOps.java#L110)) respectively.
Neither of these calls preserves `SUBSIZED`, but in a lot of cases, they could.

Sizes and subsizes can't generally be propagated through an operation which removes duplicates, but there are important special cases where propagation can occur. 
The special measures taken by `DistinctOps` to preserve the `DISTINCT` characteristic gives away that its authors felt that requesting the distinct elements of an already distinct stream was important enough to optimise for, albeit choosing an implementation which discards characteristics.

On the other hand, I'm not at all sure why _sorting_, or any other cardinality-preserving operation, need incur the loss of `SIZED` or `SUBSIZED` and this looks like a glaring oversight to me. 

## Contrived benchmarks

The performance impact can be quite large, and can be seen with some simple (contrived?) benchmarks.
I ran these benchmarks on a 4 core machine using JDK 11.0.10 on Ubuntu 18.0.4.
My source code is [here](https://github.com/richardstartin/runtime-benchmarks/tree/master/src/main/java/com/openkappa/runtime/stream).

### Sorted `ArrayList`

Here is a contrived comparison, with an `ArrayList`. 
Both implementations perform a redundant sort before a reducing terminal operation, but the sort need not be redundant at all; a naive calculation of the total size of each quantile would require the sort.
One implementation sorts the input manually rather than relying on the streams API for a fair comparison.

```java
  @Benchmark
  public long sortThenParallelMapReduce() {
    Collections.sort(list); // sort first to do the same amount of work
    return list.stream()
        .parallel()
        .mapToInt(String::length)
        .sum();
  }

  @Benchmark
  public long sortedParallelMapReduce() {
    return list.stream()
        .sorted() // use the streams API
        .parallel()
        .mapToInt(String::length)
        .sum();
  }
```

The difference avoiding `SortedOps` makes is huge:

```
Benchmark                                  (size)  Mode  Cnt      Score     Error  Units
ArrayListStream.sortThenParallelMapReduce     100  avgt    5     16.832 ±   0.356  us/op
ArrayListStream.sortThenParallelMapReduce   10000  avgt    5    131.494 ±   2.637  us/op
ArrayListStream.sortThenParallelMapReduce  100000  avgt    5   4521.761 ±  70.150  us/op
ArrayListStream.sortedParallelMapReduce       100  avgt    5     39.216 ±   0.463  us/op
ArrayListStream.sortedParallelMapReduce     10000  avgt    5   1298.756 ±  70.390  us/op
ArrayListStream.sortedParallelMapReduce    100000  avgt    5  18160.854 ± 552.422  us/op
```

### Redundant Distinct `TreeSet`

On the other hand, the impact of a redundant `.distinct()` can be seen not to affect streams over `TreeSet`s by computing length of the elements of a `TreeSet` in parallel.
This is because `TreeSet` has a special [spliterator implementation](https://github.com/openjdk/jdk/blob/2c8e337dff4c84fb435cafac8b571f94e161f074/src/java.base/share/classes/java/util/TreeMap.java#L3033) which is not `SUBSIZED` (it is a linked data structure).
One version has a redundant distinct operation, the other relies on the fact that the elements of a `TreeSet` are already distinct.
The `distinct()` call might be added because the type of the collection is unknown, or the construction of the `Stream` is unknown, or because the programmer hasn't realised that the elements of sets are distinct.

```java
  @Benchmark
  public long parallelMapReduce() {
    return set.stream()
        .parallel()
        .mapToInt(String::length)
        .sum();
  }

  @Benchmark
  public long distinctParallelMapReduce() {
    return set.stream()
        .distinct() // redundant operation will be a no-op, but changes the characteristics
        .parallel()
        .mapToInt(String::length)
        .sum();
  }
```

```
Benchmark                                (size)  Mode  Cnt     Score     Error  Units
TreeSetStream.distinctParallelMapReduce     100  avgt    5    16.423 ±   0.247  us/op
TreeSetStream.distinctParallelMapReduce   10000  avgt    5    49.920 ±   2.855  us/op
TreeSetStream.distinctParallelMapReduce  100000  avgt    5  1522.599 ± 299.516  us/op
TreeSetStream.parallelMapReduce             100  avgt    5    16.223 ±   2.335  us/op
TreeSetStream.parallelMapReduce           10000  avgt    5    73.168 ±   0.985  us/op
TreeSetStream.parallelMapReduce          100000  avgt    5  1300.833 ±  78.865  us/op
```

Even so, the size of a `TreeSet` is known at pipeline construction time.
Three years later, the `SIZED` characteristic is still discarded by a redundant call to `distinct()`, which makes the difference between a constant time count and a linear time count:

```java
  @Benchmark
  public long count() {
    return set.stream().count();
  }

  @Benchmark
  public long distinctCount() {
    return set.stream().distinct().count();
  }
```

```
Benchmark                                (size)  Mode  Cnt     Score     Error  Units
TreeSetStream.count                         100  avgt    5     0.025 ±   0.001  us/op
TreeSetStream.count                       10000  avgt    5     0.035 ±   0.001  us/op
TreeSetStream.count                      100000  avgt    5     0.044 ±   0.005  us/op
TreeSetStream.distinctCount                 100  avgt    5     0.507 ±   0.024  us/op
TreeSetStream.distinctCount               10000  avgt    5   129.226 ± 107.403  us/op
TreeSetStream.distinctCount              100000  avgt    5  4327.173 ± 159.340  us/op
```

So watch out for redundant stream operations.
If you're implementing your own `Spliterator`s, try to make them `SUBSIZED` for profit, so long as the rest of the API doesn't get in your way.





