---
title: "How a Bitmap Index Works"
layout: post
date: 2017-01-09
---
Bitmap indices are used in various data technologies for efficient query processing. At a high level, a bitmap index can be thought of as a physical materialisation of a set of predicates over a data set, is naturally columnar and particularly good for multidimensional boolean query processing. [PostgreSQL](https://wiki.postgresql.org/wiki/Bitmap_Indexes) materialises a bitmap index on the fly from query predicates when there are multiple attributes constrained by a query (for instance in a compound where clause). The filter caches in [ElasticSearch](https://www.elastic.co/blog/frame-of-reference-and-roaring-bitmaps) and [Solr](http://blog-archive.griddynamics.com/2014/01/segmented-filter-cache-in-solr.html) are implemented as bitmap indices on filter predicates over document IDs. [Pilosa](https://github.com/pilosa/pilosa) is a distributed bitmap index query engine built in Go, with a Java client library.

Bitmap indices are not a one-size-fits-all data structure, and in degenerate cases can take up more space than the data itself; using a bitmap index in favour of a B-tree variant on a primary key should be considered an abuse. Various flavours of bitmap implementation exist, but the emerging _de facto_ standard is [RoaringBitmap](http://roaringbitmap.org/) led by [Daniel Lemire](http://lemire.me/blog/). RoaringBitmap is so ubiquitous that it is handled as a special case by [KryoSerializer](https://github.com/apache/spark/blob/master/core/src/main/scala/org/apache/spark/serializer/KryoSerializer.scala) - no registration required if you want to use Spark to build indices.

#### Naive Bitmap Index

To introduce the concept, let's build a naive uncompressed bitmap index. Let's say you have a data set and some way of assigning an integer index, or _record index_ from now on, to each record (the simplest example would be the line number in a CSV file), and have chosen some attributes to be indexed. For each distinct value of each indexed attribute of your data, compute the set of indices of records matching the predicate. For each attribute, create a map from the attribute values to the sets of corresponding record indices. The format used for the set doesn't matter yet, but either an `int[]` or `BitSet` would be suitable depending on properties of the data and the predicate (cardinality of the data set, sort order of the data set, cardinality of the records matching the predicate, for instance). Using a `BitSet` to encode the nth record index as the nth bit of the `BitSet` can be 32x smaller than an `int[]` in some cases, and can be much larger when there are many distinct values of an attribute, which results in sparse bitmaps.

The tables below demonstrate the data structure. The first table represents a simple data set. The second and third tables represent bitmap indices on the data set, indexing the _Country_ and _Sector_ attributes.

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead>
<th>Record Index</th>
<th>Country</th>
<th>Sector</th>
</thead>
<tbody>
<tr>
<td>0</td>
<td>GB</td>
<td>Financials</td>
</tr>
<tr>
<td>1</td>
<td>DE</td>
<td>Manufacturing</td>
</tr>
<tr>
<td>2</td>
<td>FR</td>
<td>Agriculturals</td>
</tr>
<tr>
<td>3</td>
<td>FR</td>
<td>Financials</td>
</tr>
<tr>
<td>4</td>
<td>GB</td>
<td>Energies</td>
</tr>
</tbody>
</table>
</div>
The bitmap index consists of the two tables below:

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed"><caption>Country</caption>
<thead>
<th>Value</th>
<th>Record Indices</th>
<th>Bitmap</th>
</thead>
<tbody>
<tr>
<td>GB</td>
<td>0,4</td>
<td>0x10001</td>
</tr>
<tr>
<td>DE</td>
<td>1</td>
<td>0x10</td>
</tr>
<tr>
<td>FR</td>
<td>2,3</td>
<td>0x1100</td>
</tr>
</tbody>
</table>
</div>

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed"><caption>Sector</caption>
<thead>
<th>Value</th>
<th>Record Indices</th>
<th>Bitmap</th>
</thead>
<tbody>
<tr>
<td>Financials</td>
<td>0,3</td>
<td>0x1001</td>
</tr>
<tr>
<td>Manufacturing</td>
<td>1</td>
<td>0x10</td>
</tr>
<tr>
<td>Agriculturals</td>
<td>2</td>
<td>0x100</td>
</tr>
<tr>
<td>Energies</td>
<td>4</td>
<td>0x10000</td>
</tr>
</tbody>
</table>
</div>

It's worth noting three patterns in the tables above.

1. The number of bitmaps for an attribute is the attribute's distinct count.
2. There are typically runs of zeroes or ones, and the lengths of these runs depend on the sort order of the record index attribute.
3. A bitmap index on the record index attribute itself would be as large as the data itself, and a much less concise representation. Bitmap indices do not compete with B-tree indices for primary key attributes.

#### Query Evaluation

This simple scheme effectively materialises the result of predicates on the data and is particularly appealing because these predicates can be composed by performing efficient logical operations on the bitmaps. Query evaluation is most efficient when both the number of bitmaps and size of each bitmap are as small as possible. An efficient query plan will touch as few bitmaps as possible, regardless of bitmap size. Here are some examples of queries and their evaluation plans.

##### Single Attribute Union

```sql
select *
from records
where country = "GB" or country = "FR"
```

1. Access the country index, read the bitmaps for values "FR" and "GB".
2. Apply a bitwise logical OR to get a new bitmap.
3. Access the data stored by record id with the retrieved indices.

##### Multi Attribute Intersection

```sql
select *
from records
where country = "GB" and sector = "Energies"
```

1. Access the country index, and read the bitmap for value "GB".
2. Access the sector index, and read the bitmap for value "Energies".
3. Apply a bitwise logical AND to get a new bitmap.
4. Access the data stored by record id with the retrieved indices.

##### Single Attribute Except Clause

```sql
select *
from records
where country <> "GB"
```

1. Access the country index, and read the bitmap for value "GB".
2. Negate the bitmap.
3. Access the data stored by record id with the retrieved indices.

The index lends itself to aggregate queries (and aggregates on predicates)
##### Count

```sql 
select country, count(*)
from records
group by country
```

1. Iterate over the keys in the country index and count the bits in each bitmap, store the count against the key in a map.

##### Count with Filter

```sql
select country, count(*)
from records
where sector <> "Financials"
group by country
```

1. Access the sector index and read the bitmap for "Financials".
2. Negate the bitmap, call the negated bitmap `without_financials`.
3. Access the country index.
4. Iterate over the keys:
⋅⋅1. Intersect each bitmap with `without_financials`.
⋅⋅2. Count the bits in the resultant bitmap, store the count against the key in a map.

The two main factors affecting the performance of query processing are the number of bitmaps that need to be accessed, and the size of each bitmap (which concerns both memory/disk usage and CPU utilisation) - both should be minimised. Choosing the correct <em>encoding</em> for expected queries (one should expect range queries for dates, but equality and set membership queries for enumerations) can reduce the number of bitmap accesses required to evaluate a query; whereas <em>compression</em> can reduce the bitmap sizes.

##### Encoding

Only predicates for equality are efficient with the scheme so far. Suppose there is a well defined sort order for an attribute `a`. In order to evaluate

```sql
select *
from records
where a > x and a < y
```

every bitmap in the range `(x, y)` would have to be accessed and united. This could easily become a performance bottleneck. The _encoding_ could be adapted for evaluating range predicates. Instead of setting the nth bit if the nth record has `a = y` (equality encoding), it could be set if the nth record has `a ≤ y` (range encoding). In this encoding only one bitmap would need to be accessed to evaluate a predicate like `a ≤ y`, rather than the`|[min(a), y]|` bitmaps required using the equality encoding. In order to evaluate `a ∈ [x, y]`, only the bitmaps for `x` and `y` are needed. Not much is lost in order to support equality predicates in a range encoding; only the bitmap for the value and its predecessor are required.

#### Compression

The scheme presented so far works as a toy model but the bitmaps are just too large to be practical. A bitmap index on a single attribute with `m` distinct values over a data set consisting of `n` records, using a `BitSet` would consume `mn` bits, using an `int[]` would consume `32mn` bits. Therefore, some kind of compression is required to make the approach feasible.

Often in real world data sets, there are attributes with skewed histograms, a phenomenon known as [Zipf's Law](https://en.wikipedia.org/wiki/Zipf%27s_law). In a typical financial data set exhibiting this property, most trades will be in very few instruments (_EURGBP_ for instance), and there will be very few trades in the rest of the traded instruments. The bitmaps for the values at both the head and tail of these histograms become less random and therefore compressible. At the head, the bits are mostly set; at the tail mostly unset. Compression seeks to exploit this.

One well understood compression strategy is run length encoding. If there are `m` bits set in a row, followed by `n` unset bits and again followed by $latex p$ bits set, 0x1...10..01..1 of size `m + n + p` bit could be replaced by `m1n0p1` which is typically a lot smaller (though worse if the runs are very short). Since there are only two possible values, only ranges of set bits need to be represented - it is only necessary to store the start index and length of each run, so the bitmap becomes the set of tuples `{(0,m), (m+n, p)}`. Notably the sort order of the record index with respect to the attribute affects the compression ratio for run length encoding because it can make runs longer or shorter.

Historically, run length encoding on bits has been considered impractical because processors operate on words not bits. Instead of counting runs of bits, several algorithms count runs of bytes (BBC - _Byte-aligned Bitmap Compression_) or words (WAH - _Word Aligned Hybrid_, EWAH - _Enhanced Word Aligned Hybrid_). These algorithms are faster at the expense of reduced compression. In these schemes compression is improved when there are long runs of _clean_ words (where all the bits in the word are the same), and the compression ratio is degraded when there are many _dirty_ words, which cannot be compressed at all. The number of clean words and hence the compression ratio for a bitmap index depends on the order of the record index attribute. However, an optimal sort order with respect to an index on one attribute will generally be sub-optimal for an index on another.

In order to maintain the attractive boolean query processing capabilities, the OR, AND, XOR, NAND, NOR and NOT operations each need to redefined to operate on the compressed form of the bitmap, and in the case of algorithms like EWAH these adapted operations are more efficient, CPU and cache-friendly, than on naive uncompressed bitmaps.

Previously I was ambivalent between the use of _BitSet_ and _int[]_ to encode the sets of record indices (_Set_ was not proposed because of the inherent cost of wrapped integers). This is because neither of these types is really appropriate for the task in all cases. If we use an uncompressed _BitSet_ we end up with high memory usage for a large data set, even if most of the bits are unset, which is often compressible at the word level. With very sparse data, when most of the bits would be zero, it would take less space to store the record indices in an _int[]_ instead. By choosing dynamically whether to use integers, uncompressed bits, or compressed words is actually roughly how the RoaringBitmap library optimises performance. More about that [here](https://richardstartin.github.io/http:/richardstartin.uk/a-quick-look-at-roaringbitmap/).

#### Reducing the Number of Bitmaps

Query evaluation performance degrades with the number of bitmaps that need to be accessed. Choosing the right encoding for query patterns and reducing the size of each bitmap are both key for performance and practicality, but it can help save storage space to have fewer bitmaps per attribute. So far each value has been encoded as a single bitmap, and each bitmap has been associated with only one value. The total number of bitmaps can be reduced by applying a factorisation on values with a bitmap per factor, so each bitmap will be associated with several values and each value will be associated with several bitmaps. To this end, mapping values into integers by some means would allow integer arithmetic to be used for index construction. A simple mechanism to map a set of objects to integers would be a dictionary, a more complicated but better mechanism might be a perfect hash function like CHM (an order preserving transformation!) or BZW (which trades order preservation for better compression).

##### Bit Slicing

Supposing a mapping between a set of values and the natural numbers has been chosen and implemented, we can define a basis to factorise each value. The number 571, for example, can be written down as either `5*10^2 + 7*10^1 + 1*10^0` in base-10 or `1*8^3 + 0*8^2 + 7*8^1 + 3*8^0` in base-8. Base-10 uses more coefficients, whereas base-8 uses more digits. Bit slice indexing is analogous to arithmetic expansion of integers, mapping coefficients to sets, or _slices_, of bitmaps; digits to bitmaps.

Mapping a set of objects `S` into base `n`, where `log_n(|S|) ~ O(m)`, we can use `mn` bitmaps to construct the index. The bases do not need to be identical (to work with date buckets we could choose to have four quarters, three months, and 31 days for example) but if they are the bases are said to be _uniform_. An example of a base 3 uniform index on currencies is below:

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed"><caption>Records</caption>
<thead>
<th>Record Index</th>
<th>Currency</th>
</thead>
<tbody>
<tr>
<td>0</td>
<td>USD</td>
</tr>
<tr>
<td>1</td>
<td>GBP</td>
</tr>
<tr>
<td>2</td>
<td>GBP</td>
</tr>
<tr>
<td>3</td>
<td>EUR</td>
</tr>
<tr>
<td>4</td>
<td>CHF</td>
</tr>
</tbody>
</table>
</div>

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed"><caption>Currency Encoding</caption>
<thead>
<th>Currency</th>
<th>Code</th>
<th>Base 3 Expansion</th>
</thead>
<tbody>
<tr>
<td>USD</td>
<td>0</td>
<td>0*3 + 0</td>
</tr>
<tr>
<td>GBP</td>
<td>1</td>
<td>0*3 + 1</td>
</tr>
<tr>
<td>EUR</td>
<td>2</td>
<td>0*3 + 2</td>
</tr>
<tr>
<td>CHF</td>
<td>3</td>
<td>1*3 + 0</td>
</tr>
</tbody>
</table>
</div>

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed"><caption>Single Component Currency Index</caption>
<thead>
<th>Currency</th>
<th>Bitmap</th>
</thead>
<tbody>
<tr>
<td>USD</td>
<td>0x1</td>
</tr>
<tr>
<td>GBP</td>
<td>0x110</td>
</tr>
<tr>
<td>EUR</td>
<td>0x1000</td>
</tr>
<tr>
<td>CHF</td>
<td>0x10000</td>
</tr>
</tbody>
</table>
</div>

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed"><caption>Bit Sliced Currency Index</caption>
<thead>
<th>Power of 3</th>
<th>Remainder</th>
<th>Bitmap</th>
</thead>
<tbody>
<tr>
<td>1</td>
<td>0</td>
<td>0x1111</td>
</tr>
<tr>
<td>1</td>
<td>1</td>
<td>0x10000</td>
</tr>
<tr>
<td>1</td>
<td>2</td>
<td>0x0</td>
</tr>
<tr>
<td>0</td>
<td>0</td>
<td>0x10001</td>
</tr>
<tr>
<td>0</td>
<td>1</td>
<td>0x110</td>
</tr>
<tr>
<td>0</td>
<td>2</td>
<td>0x1000</td>
</tr>
</tbody>
</table>
</div>

Here we have actually used six bitmaps instead of four, but the factorisation comes into its own when more currencies are added. With a 2-component base-3 index, we can use six bitmaps to encode up to nine values.

To evaluate a query, map the value into its integer representation, factorise the number with respect to the bases of the index, and then intersect at most `m` bitmaps together. This is slower than a single bitmap access, but has some useful properties if data is hierarchically bucketed as well as trading query performance for storage space. To evaluate queries at the top level of bucketing, only one bitmap access is required; at the second level, two bitmap accesses are required and so on. So there is a trade off between degraded performance with granular values with increased performance for roll-ups.

#### Links
Here are some links on the topic that I found interesting

* [Roaring Bitmap](http://roaringbitmap.org/)
* [Bitmap Index Design and Evaluation](http://www.comp.nus.edu.sg/~chancy/sigmod98.pdf)
* [Sorting improves word-aligned bitmap indexes](https://arxiv.org/pdf/0901.3751.pdf)
* [Consistently faster and smaller compressed bitmaps with Roaring](https://arxiv.org/pdf/1603.06549.pdf")
