---
title: "A Quick Look at RoaringBitmap"
layout: post

date: 2017-03-01
redirect_from:
  - /a-quick-look-at-roaringbitmap/
---

This article is an introduction to the data structures found in the [RoaringBitmap](https://github.com/RoaringBitmap/RoaringBitmap) library, which I have been making extensive use of recently. I wrote some time ago about the basic idea of [bitmap indices](https://richardstartin.github.io/posts/how-a-bitmap-index-works), which are used in various databases and search engines, with the caveat that no traditional implementation is optimal across all data scenarios (in terms of size of the data set, sparsity, cardinalities of attributes and global sort orders of data sets with respect to specific attributes). RoaringBitmap is a dynamic data structure which aims to be that _one-size-fits-all_ solution across all scenarios.

#### Containers

A RoaringBitmap should be thought of as a set of unsigned integers, consisting of containers which cover disjoint subsets. Each subset can contain values from a range of size 2^16, and the subset is indexed by a 16 bit key. This means that in the worst case it only takes 16 bits to represent a single 32 bit value, so unsigned 32 bit integers can be stored as Java shorts. The choice of container size also means that in the worst case, the container will still fit in L1 cache on a modern processor.

The implementation of the container covering a disjoint subset is free to vary between _[RunContainer](https://github.com/RoaringBitmap/RoaringBitmap/blob/master/RoaringBitmap/src/main/java/org/roaringbitmap/RunContainer.java)_, _[BitmapContainer](https://github.com/RoaringBitmap/RoaringBitmap/blob/master/RoaringBitmap/src/main/java/org/roaringbitmap/BitmapContainer.java)_ and _[ArrayContainer](https://github.com/RoaringBitmap/RoaringBitmap/blob/master/RoaringBitmap/src/main/java/org/roaringbitmap/ArrayContainer.java)_, depending entirely on properties of the subset. When inserting data into a RoaringBitmap, it is decided whether to create a new container, or to mutate an existing container, depending on whether the values fit in the range covered by the container's key. When performing a set operation, for instance by intersecting two bitmaps or computing their symmetric difference, a new RoaringBitmap is created by performing operations container by container, and it is decided dynamically which container implementation is best suited for the result. For cases where it is too difficult to determine the best implementation automatically, the method `runOptimize` is available to the programmer to make sure.

When querying a RoaringBitmap, the query can be executed container by container (which incidentally makes the query naturally parallelisable, [but it hasn't been done yet](https://github.com/RoaringBitmap/RoaringBitmap/issues/42)), and each pair from the cartesian product of combinations of container implementations must be implemented separately. This is manageable because there are only three implementations, and there won't be any more. There is less work to do for symmetric operations, such as union and intersection, than with asymmetric operations such as contains.

#### RunContainer

When there are lots of clean words in a section of a bitmap, the best choice of container is run length encoding. The implementation of RunContainer is simple and very compact. It consists of an array of shorts (not ints, the most significant 16 bits are in the key) where the values at the even indices are the starts of runs, and the values at the odd indices are the lengths of the respective runs. Membership queries can be implemented simply using a binary search, and quantile queries can be implemented in constant time. Computing container cardinality requires a pass over the entire run array.

#### ArrayContainer

When data is sparse within a section of the bitmap, the best implementation is an array (`short[]`). For very sparse data, this isn't theoretically optimal, but for most cases it is very good and the array for the container will fit in L1 cache for _mechanical sympathy_. Cardinality is very fast because it is precomputed, and operations would be fast in spite of their precise implementation by virtue of the small size of the set (that being said, the actual implementations <em>are</em> fast). Often when creating a new container, it is necessary to convert to a bitmap for better compression as the container fills up.

#### BitmapContainer

BitmapContainer is the classic implementation of a bitset. There is a fixed length `long[]` which should be interpreted bitwise, and a precomputed cardinality. Operations on `BitmapContainer`s tend to be very fast, despite typically touching each element in the array, because they fit in L1 cache and make extensive use of Java intrinsics. If you find a method name in [here](http://hg.openjdk.java.net/jdk8/jdk8/hotspot/file/87ee5ee27509/src/share/vm/classfile/vmSymbols.hpp) and run your JVM on a reasonably modern processor, your code will quickly get optimised by the JVM, sometimes even to a single instruction. A much hackneyed example, explained better by [Michael Barker](http://bad-concurrency.blogspot.co.uk/2012/08/arithmetic-overflow-and-intrinsics.html) _quite some time ago_, would be [`Long.bitCount`](https://docs.oracle.com/javase/7/docs/api/java/lang/Long.html#bitCount(long)), which translates to the single instruction <em>popcnt</em> and has various uses when operating on `BitmapContainer`s. When intersecting with another container, the cardinality can only decrease or remain the same, so there is a chance a smaller `ArrayContainer` will be produced.

#### Examples
There is a nice [Scala project](https://github.com/adform/bitmap-dsl) on github which functions as a DSL for creating RoaringBitmaps - it allows you to create an _equality encoded_ ([see my previous bitmap index post](https://richardstartin.github.io/posts/how-a-bitmap-index-works)) RoaringBitmap in a very fluid way. 

I have implemented bit slice indices, both equality and range encoded, in a data quality tool I am building. Below is an implementation of a range encoded bit slice index as an example of how to work with RoaringBitmaps.

```java
public class RangeEncodedOptBitSliceIndex implements RoaringIndex {

  private final int[] basis;
  private final int[] cumulativeBasis;
  private final RoaringBitmap[][] bitslice;

  public RangeEncodedOptBitSliceIndex(ProjectionIndex projectionIndex, int[] basis) {
    this.basis = basis;
    this.cumulativeBasis = accumulateBasis(basis);
    this.bitslice = BitSlices.createRangeEncodedBitSlice(projectionIndex, basis);
  }

  @Override
  public RoaringBitmap whereEqual(int code, RoaringBitmap existence) {
    RoaringBitmap result = existence.clone();
    int[] expansion = expand(code, cumulativeBasis);
    for(int i = 0; i < cumulativeBasis.length; ++i) {
      int component = expansion[i];
      if(component == 0) {
        result.and(bitslice[i][0]);
      }
      else if(component == basis[i] - 1) {
        result.andNot(bitslice[i][basis[i] - 2]);
      }
      else {
        result.and(FastAggregation.xor(bitslice[i][component], bitslice[i][component - 1]));
      }
    }
    return result;
  }

  @Override
  public RoaringBitmap whereNotEqual(int code, RoaringBitmap existence) {
    RoaringBitmap inequality = existence.clone();
    inequality.andNot(whereEqual(code, existence));
    return inequality;
  }

  @Override
  public RoaringBitmap whereLessThan(int code, RoaringBitmap existence) {
    return whereLessThanOrEqual(code - 1, existence);
  }

  @Override
  public RoaringBitmap whereLessThanOrEqual(int code, RoaringBitmap existence) {
    final int[] expansion = expand(code, cumulativeBasis);
    final int firstIndex = cumulativeBasis.length - 1;
    int component = expansion[firstIndex];
    int threshold = basis[firstIndex] - 1;
    RoaringBitmap result = component < threshold ? bitslice[firstIndex][component].clone() : existence.clone();     for(int i = firstIndex - 1; i >= 0; --i) {
      component = expansion[i];
      threshold = basis[i] - 1;
      if(component != threshold) {
        result.and(bitslice[i][component]);
      }
      if(component != 0) {
        result.or(bitslice[i][component - 1]);
      }
    }
    return result;
  }

  @Override
  public RoaringBitmap whereGreaterThan(int code, RoaringBitmap existence) {
    RoaringBitmap result = existence.clone();
    result.andNot(whereLessThanOrEqual(code, existence));
    return result;
  }

  @Override
  public RoaringBitmap whereGreaterThanOrEqual(int code, RoaringBitmap existence) {
    RoaringBitmap result = existence.clone();
    result.andNot(whereLessThan(code, existence));
    return result;
  }
}
```

#### Further Reading

The library has been implemented under an Apache License by several contributors, the most significant contributions coming from computer science researcher Daniel Lemire, [who presented RoaringBitmap at Spark Summit 2017](https://www.youtube.com/watch?v=1QMgGxiCFWE). Visit [the project site](http://roaringbitmap.org/) and the [research paper](https://arxiv.org/pdf/1402.6407.pdf) behind the library.
