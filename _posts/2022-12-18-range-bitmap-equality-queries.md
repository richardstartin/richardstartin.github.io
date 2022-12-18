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

1. TOC
{:toc}

### How to use it?

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

### How does it work?

`RangeBitmap` has a simple two-dimensional structure.
The first dimension is the rows in the order the values were added in.
The second dimension is the binary representation of each value added, after range encoding, and there are only as many of these columns as there are significant bits in the largest value added.

The layout is essentially the bit-transposition of the values added, striped in bands of $2^{16}$ rows, with a little bit of metadata to help traversals. 
Each $2^{16}$ rows are bucketed into a _horizontal slice_ which consists of $64 - clz(max)$ `RoaringBitmap` containers, one for each bit of the inputs, and a mask of size $64 - clz(max)$ bits, indicating the presence of a container. 
If the $n$th value added to the `RangeBitmap` does not have bit $i$ set, the $i$th container in the $n/2^{16}$th slice will have no bit set.
If all $2^{16}$ values in the slice have bit $i$ unset, the mask will have bit $i$ unset and no container, which is an optimisation to avoid storing empty containers.

If the following values (with their binary representation in brackets) are added in sequence
```
42 (101010)
24 (011000)
9  (001001)
27 (011011)
```

The values are first negated to range encode them (see [here](https://richardstartin.github.io/posts/range-bitmap-index) for explanation).

```
010101
100111
110110
100100
```
There will be one horizontal slice with four rows in it, a 6 bit mask, and 5 containers per slice because the 4th bit is present in all the values in the slice.
This looks something like this, if stored as plain bitsets:

```
110111 1100 0110 1111 1010 0110 
```

There are three kinds of `RoaringBitmap` containers for different densities - sparse, dense, and run length encoded.
Containers with only four values would always be sparse, for the sake of explanation, assume these are just the first four values in a much larger slice.
Encoded as containers, this looks like:

```
110111 [4,2] {2,4} [0,4] 1010 {2,4}
```

Where the containers in braces have been represented as arrays of 16 bit values, the ones in square brackets are run length encoded, and the binary numbers are just bitsets.

To evaluate queries against `RangeBitmap`, the slices need to be iterated over in ascending order.
For each slice, the containers need to be extracted and combined, using a different combination algorithm for each relation.
The equality combination algorithm is very simple:
* start with a bitset `b` with a set bit for each row in the slice
* for each `i` from 0 to the size of the slice's mask, 
  * if `i` is set in the query value, remove the container `i`'s bits (or none, if container `i` is missing for the current slice) from `b`
  * If `i` is absent in the query value, intersect container `i`'s bits with `b` (or just clear it id the container is missing for the slice)

For inequality, `b` needs to be complemented at the end. 
Range queries are generally more complex to evaluate than this, but all queries are evaluated in this slice by slice in ascending row order fashion.