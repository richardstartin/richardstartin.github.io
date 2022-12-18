---
title: Evaluating Equality Predicates
layout: post
tags: java roaring
date: 2022-12-18
---

I have just [implemented support](https://github.com/RoaringBitmap/RoaringBitmap/pull/606) for (in)equality queries against a `RangeBitmap`, a succinct data structure in the `RoaringBitmap` library which supports range queries.
`RangeBitmap` was designed to support range queries in Apache Pinot (more details [here](https://richardstartin.github.io/posts/range-bitmap-index)) but this enhancement would allow a range index to be used as a fallback for (in)equality queries in case nothing better is available.
Supporting (in)equality queries allows a `RangeBitmap` to be used as a kind of compact inverted index, trading space for time, capable of supporting high cardinality gracefully.  

Since `RangeBitmap` supports memory mapping from files, I think that it could be used for data engineering beyond Apache Pinot. 
This post extends the example set up in [Evaluating Range Predicates](https://richardstartin.github.io/posts/range-predicates) and [Counting over Range Predicates](https://richardstartin.github.io/posts/range-counts), which centre around a large collection of `Transaction` objects:

```java
  public static final class Transaction {
    private final int quantity;
    private final long price;
    private final long timestamp;

    public Transaction(int quantity, long price, long timestamp) {
      this.quantity = quantity;
      this.price = price;
      this.timestamp = timestamp;
    }

    public int getQuantity() {
      return quantity;
    }

    public long getPrice() {
      return price;
    }

    public long getTimestamp() {
      return timestamp;
    }
  }
```

Let's find all the transactions with a certain quantity in the most obvious way possible, using the stream API.

```java
    transactions.stream()
         .filter(transaction -> transaction.quantity == qty)
         .forEach(this::processTransaction);
```

On my laptop, it takes about 3ms to select about 100 transactions from 1M.

<div class="table-holder" markdown="block">

| Benchmark |Mode|Threads|Samples| Score       | Score Error (99.9%) |Unit |Param: minPrice|Param: minQuantity|Param: size|
|-----------|----|-------|-------|-------------|---------------------|-----|---------------|------------------|-----------|
| stream    |avgt|1      |5      | 2849.444527 |  	30.581160         |us/op|100            |1                 |1000000    |

</div>

With a `RangeBitmap`, these same transactions can be found with the already existing `between` method:

```java
    RoaringBitmap matchesQuantity = qtyIndex.between(qty - minQty, qty - minQty);
    matchesQuantity.forEach((IntConsumer) i -> processTransaction(transactions.get(i)));
```

> as explained in [Evaluating Range Predicates](https://richardstartin.github.io/posts/range-predicates), the quantities in the index have been anchored to the smallest value in the population, as a size optimisation. 

This performs quite a lot better, selecting the same transactions in under 300us, which is a 10x improvement.

<div class="table-holder" markdown="block">

| Benchmark |Mode|Threads|Samples| Score       | Score Error (99.9%) |Unit |Param: minPrice|Param: minQuantity|Param: size|
|-----------|----|-------|-------|-------------|---------------------|-----|---------------|------------------|-----------|
| stream    |avgt|1      |5      | 2849.444527 | 	30.581160          |us/op|100            |1                 |1000000    |
| between   |avgt|1      |5      | 296.488277 | 	0.703309           |us/op|100            |1                 |1000000    |

</div>

This can be rewritten using `eq`:

```java
    RoaringBitmap matchesQuantity = qtyIndex.eq(qty - minQty);
    matchesQuantity.forEach((IntConsumer) i -> processTransaction(transactions.get(i)));
```

The new `eq` method doesn't need to do as much work as `between`, which needs to maintain and combine two bitsets during the scan over the `RangeBitmap`, whereas `eq` only needs one.
This means we can get a good speedup from `eq` to select the same transactions:

<div class="table-holder" markdown="block">

| Benchmark |Mode|Threads|Samples| Score       | Score Error (99.9%) |Unit |Param: minPrice|Param: minQuantity|Param: size|
|-----------|----|-------|-------|-------------|---------------------|-----|---------------|------------------|-----------|
| stream    |avgt|1      |5      | 2849.444527 | 	30.581160          |us/op|100            |1                 |1000000    |
| between   |avgt|1      |5      | 296.488277 | 	0.703309           |us/op|100            |1                 |1000000    |
| eq        |avgt|1      |5      | 183.913329 | 	1.994362          |us/op|100            |1                 |1000000    |

</div>

It's worth making a comparison with an inverted index over `quantity` (so a bitmap of transaction positions per quantity) now.
The inverted index would always win for speed on this query, but can take up a lot more space, and the inverted index would almost always lose for range queries.
A range encoded inverted index (a mapping from quantity to bitmap of the positions of all transactions with a smaller quantity) will generally beat `RangeBitmap` for speed at the cost of space.
This makes a `RangeBitmap` suitable for equality queries eiter on a high cardinality attribute or as a fallback better than scanning when range queries are more common.

Inequality filters tend not to be very selective, so benchmarking the evaluation would be dominated by the time to scan the results, but the `neq` method is present for API symmetry.

In the same set of changes there are also methods to push a `RoaringBitmap` context down into `eq` and `neq` queries, which behaves like an intersection. 
Rather than producing a large bitmap and then intersecting it with a small context bitmap, the context bitmap is used to potentially skip over large sections of the `RangeBitmap`.
There are also `eqCardinality` and `neqCardinality` methods, which produce counts rather than bitmaps, as described for [range counts](https://richardstartin.github.io/posts/range-counts).
