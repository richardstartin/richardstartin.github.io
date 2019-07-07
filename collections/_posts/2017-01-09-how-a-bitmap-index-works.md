---
ID: 1207
post_title: How a Bitmap Index Works
author: Richard Startin
post_excerpt: ""
layout: post
permalink: >
  http://richardstartin.uk/how-a-bitmap-index-works/
published: true
post_date: 2017-01-09 15:35:55
---
Bitmap indices are used in various data technologies for efficient query processing. At a high level, a bitmap index can be thought of as a physical materialisation of a set of predicates over a data set, is naturally columnar and particularly good for multidimensional boolean query processing. <a href="https://wiki.postgresql.org/wiki/Bitmap_Indexes" target="_blank">PostgreSQL</a> materialises a bitmap index on the fly from query predicates when there are multiple attributes constrained by a query (for instance in a compound where clause). The filter caches in <a href="https://www.elastic.co/blog/frame-of-reference-and-roaring-bitmaps" target="_blank">ElasticSearch</a> and <a href="http://blog-archive.griddynamics.com/2014/01/segmented-filter-cache-in-solr.html" target="_blank">Solr</a> are implemented as bitmap indices on filter predicates over document IDs. <a href="https://github.com/pilosa/pilosa" target="_blank">Pilosa</a> is a distributed bitmap index query engine built in Go, with a Java client library.

Bitmap indices are not a one-size-fits-all data structure, and in degenerate cases can take up more space than the data itself; using a bitmap index in favour of a B-tree variant on a primary key should be considered an abuse. Various flavours of bitmap implementation exist, but the emerging <em>de facto</em> standard is <a href="http://roaringbitmap.org/" target="_blank">RoaringBitmap</a> led by <a href="http://lemire.me/blog/">Daniel Lemire</a>. RoaringBitmap is so ubiquitous that it is handled as a special case by <a href="https://github.com/apache/spark/blob/master/core/src/main/scala/org/apache/spark/serializer/KryoSerializer.scala" target="_blank">KryoSerializer</a> - no registration required if you want to use Spark to build indices.
<h4>Naive Bitmap Index</h4>
To introduce the concept, let's build a naive uncompressed bitmap index. Let's say you have a data set and some way of assigning an integer index, or <em>record index</em> from now on, to each record (the simplest example would be the line number in a CSV file), and have chosen some attributes to be indexed. For each distinct value of each indexed attribute of your data, compute the set of indices of records matching the predicate. For each attribute, create a map from the attribute values to the sets of corresponding record indices. The format used for the set doesn't matter yet, but either an <code class="java">int[]</code> or <code class="java">BitSet</code> would be suitable depending on properties of the data and the predicate (cardinality of the data set, sort order of the data set, cardinality of the records matching the predicate, for instance). Using a <code class="java">BitSet</code> to encode the nth record index as the nth bit of the <code class="java">BitSet</code> can be 32x smaller than an <code class="java">int[]</code> in some cases, and can be much larger when there are many distinct values of an attribute, which results in sparse bitmaps.

The tables below demonstrate the data structure. The first table represents a simple data set. The second and third tables represent bitmap indices on the data set, indexing the <em>Country</em> and <em>Sector</em> attributes.

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
<ol>
	<li>The number of bitmaps for an attribute is the attribute's distinct count.</li>
	<li>There are typically runs of zeroes or ones, and the lengths of these runs depend on the sort order of the record index attribute</li>
	<li>A bitmap index on the record index attribute itself would be as large as the data itself, and a much less concise representation. Bitmap indices do not compete with B-tree indices for primary key attributes.</li>
</ol>
<h4>Query Evaluation</h4>
This simple scheme effectively materialises the result of predicates on the data and is particularly appealing because these predicates can be composed by performing efficient logical operations on the bitmaps. Query evaluation is most efficient when both the number of bitmaps and size of each bitmap are as small as possible. An efficient query plan will touch as few bitmaps as possible, regardless of bitmap size. Here are some examples of queries and their evaluation plans.
<h5>Single Attribute Union</h5>
<code class="language-sql">
select *
from records
where country = "GB" or country = "FR"
</code>
<ol>
	<li> Access the country index, read the bitmaps for values "FR" and "GB"</li>
	<li>Apply a bitwise logical OR to get a new bitmap</li>
	<li>Access the data stored by record id with the retrieved indices</li>
</ol>
<h5>Multi Attribute Intersection</h5>
<code class="language-sql">
select *
from records
where country = "GB" and sector = "Energies"
</code>
<ol>
	<li>Access the country index, and read the bitmap for value "GB"</li>
	<li>Access the sector index, and read the bitmap for value "Energies".</li>
	<li>Apply a bitwise logical AND to get a new bitmap</li>
	<li>Access the data stored by record id with the retrieved indices</li>
</ol>
<h5>Single Attribute Except Clause</h5>
<code class="language-sql">
select *
from records
where country <> "GB"
</code>
<ol>
	<li>Access the country index, and read the bitmap for value "GB"</li>
	<li>Negate the bitmap</li>
	<li>Access the data stored by record id with the retrieved indices</li>
</ol>
The index lends itself to aggregate queries (and aggregates on predicates)
<h5>Count</h5>
<code class="language-sql">
select country, count(*)
from records
group by country
</code>
<ol>
	<li>Access the country index</li>
	<li>Iterate over the keys
<ul>
	<li>Count the bits in the bitmap, store the count against the key in a map</li>
</ul>
</li>
</ol>
<h5>Count with Filter</h5>
<code class="language-sql">
select country, count(*)
from records
where sector <> "Financials"
group by country
</code>
<ol>
	<li>Access the sector index and read the bitmap for "Financials"</li>
	<li>Negate the bitmap, call the negated bitmap <em>without_financials</em></li>
	<li>Access the country index</li>
	<li>Iterate over the keys
<ul>
	<li>Intersect each bitmap with <em>without_financials</em></li>
	<li>Count the bits in the resultant bitmap, store the count against the key in a map</li>
</ul>
</li>
</ol>
The two main factors affecting the performance of query processing are the number of bitmaps that need to be accessed, and the size of each bitmap (which concerns both memory/disk usage and CPU utilisation) - both should be minimised. Choosing the correct <em>encoding</em> for expected queries (one should expect range queries for dates, but equality and set membership queries for enumerations) can reduce the number of bitmap accesses required to evaluate a query; whereas <em>compression</em> can reduce the bitmap sizes.
<h4>Encoding</h4>
Only predicates for equality are efficient with the scheme so far. Suppose there is a well defined sort order for an attribute $latex a$. In order to evaluate

<code class="language-sql">
select *
from records
where a > x and a < y
</code>

every bitmap in the range $latex (x, y)$ would have to be accessed and united. This could easily become a performance bottleneck. The <em>encoding</em> could be adapted for evaluating range predicates. Instead of setting the nth bit if the nth record has $latex a = y$ (equality encoding), it could be set if the nth record has $latex a \le y$ (range encoding). In this encoding only one bitmap would need to be accessed to evaluate a predicate like $latex a \le y$, rather than the $latex |[a_{min}, y]|$ bitmaps required using the equality encoding. In order to evaluate $latex a \in [x, y]$, only the bitmaps for $latex x$ and $latex y$ are needed. Not much is lost in order to support equality predicates in a range encoding; only the bitmap for the value and its predecessor are required.
<h4>Compression</h4>
The scheme presented so far works as a toy model but the bitmaps are just too large to be practical. A bitmap index on a single attribute with $latex m$ distinct values over a data set consisting of $latex n$ records, using a <code>BitSet</code> would consume $latex mn$ bits, using an <code>int[]</code> would consume $latex 32mn$ bits. Therefore, some kind of compression is required to make the approach feasible.

Often in real world data sets, there are attributes with skewed histograms, a phenomenon known as <a href="https://en.wikipedia.org/wiki/Zipf%27s_law" target="_blank">Zipf's Law</a>. In a typical financial data set exhibiting this property, most trades will be in very few instruments (EURGBP for instance), and there will be very few trades in the rest of the traded instruments. The bitmaps for the values at both the head and tail of these histograms become less random and therefore compressible. At the head, the bits are mostly set; at the tail mostly unset. Compression seeks to exploit this.

One well understood compression strategy is run length encoding. If there are $latex m$ bits set in a row, followed by $latex n$ unset bits and again followed by $latex p$ bits set, 0x1...10..01..1 of size $latex m + n + p$ bit could be replaced by $latex m1n0p1$ which is typically a lot smaller (though worse if the runs are very short). Since there are only two possible values, only ranges of set bits need to be represented - it is only necessary to store the start index and length of each run, so the bitmap becomes the set of tuples $latex \{(0,m), (m+n, p)\}$. Notably the sort order of the record index with respect to the attribute affects the compression ratio for run length encoding because it can make runs longer or shorter.

In reality, run length encoding on bits is not practical since modern processors operate on words not bits. Instead of counting runs of bits, several algorithms count runs of bytes (BBC - <em>Byte-aligned Bitmap Compression</em>) or words (WAH - <em>Word Aligned Hybrid</em>, EWAH - <em>Enhanced Word Aligned Hybrid</em>). These algorithms are faster at the expense of reduced compression. In these schemes compression is improved when there are long runs of <em>clean</em> words (where all the bits in the word are the same), and the compression ratio is degraded when there are many <em>dirty</em> words, which cannot be compressed at all. The number of clean words and hence the compression ratio for a bitmap index depends on the order of the record index attribute. However, an optimal sort order with respect to an index on one attribute will generally be sub-optimal for an index on another.

In order to maintain the attractive boolean query processing capabilities, the OR, AND, XOR, NAND, NOR and NOT operations each need to redefined to operate on the compressed form of the bitmap, and in the case of algorithms like EWAH these adapted operations are more efficient, CPU and cache-friendly, than on naive uncompressed bitmaps.

Previously I was ambivalent between the use of <code>BitSet</code> and <code>int[]</code> to encode the sets of record indices (<code>Set</code> was not proposed because of the inherent cost of wrapped integers). This is because neither of these types is really appropriate for the task in all cases. If we use an uncompressed <code>BitSet</code> we end up with high memory usage for a large data set, even if most of the bits are unset, which is often compressible at the word level. With very sparse data, when most of the bits would be zero, it would take less space to store the record indices in an <code>int[]</code> instead. By choosing dynamically whether to use integers, uncompressed bits, or compressed words is actually roughly how the RoaringBitmap library optimises performance. More about that <a href="https://richardstartin.com/2017/03/01/a-quick-look-at-roaringbitmap" target="_blank">here</a>.

<h4>Reducing the Number of Bitmaps</h4>

Query evaluation performance degrades with the number of bitmaps that need to be accessed. Choosing the right encoding for query patterns and reducing the size of each bitmap are both key for performance and practicality, but it can help save storage space to have fewer bitmaps per attribute. So far each value has been encoded as a single bitmap, and each bitmap has been associated with only one value. The total number of bitmaps can be reduced by applying a factorisation on values with a bitmap per factor, so each bitmap will be associated with several values and each value will be associated with several bitmaps. To this end, mapping values into integers by some means would allow integer arithmetic to be used for index construction. A simple mechanism to map a set of objects to integers would be a dictionary, a more complicated but better mechanism might be a perfect hash function like CHM (an order preserving transformation!) or BZW (which trades order preservation for better compression).

<h5>Bit Slicing</h5>

Supposing a mapping between a set of values and the natural numbers has been chosen and implemented, we can define a basis to factorise each value. The number 571, for example, can be written down as either $latex 5*10^2 + 7*10^1 + 1*10^0$ in base-10 or $latex 1*8^3 + 0*8^2 + 7*8^1 + 3*8^0$ in base-8. Base-10 uses more coefficients, whereas base-8 uses more digits. Bit slice indexing is analogous to arithmetic expansion of integers, mapping coefficients to sets, or <em>slices</em>, of bitmaps; digits to bitmaps.

Mapping a set of objects $latex S$ into base $latex n$, where $latex \log_n(|S|) \approx \mathcal{O}(m)$, we can use $latex mn$ bitmaps to construct the index. The bases do not need to be identical (to work with date buckets we could choose to have four quarters, three months, and 31 days for example) but if they are the bases are said to be <em>uniform</em>. An example of a base 3 uniform index on currencies is below:

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

To evaluate a query, map the value into its integer representation, factorise the number with respect to the bases of the index, and then intersect at most $latex m$ bitmaps together. This is slower than a single bitmap access, but has some useful properties if data is hierarchically bucketed as well as trading query performance for storage space. To evaluate queries at the top level of bucketing, only one bitmap access is required; at the second level, two bitmap accesses are required and so on. So there is a trade off between degraded performance with granular values with increased performance for roll-ups.
<h4>Links</h4>
Here are some links on the topic that I found interesting

<a href="http://roaringbitmap.org/">Roaring Bitmap</a>
<a href="http://www.comp.nus.edu.sg/~chancy/sigmod98.pdf">Bitmap Index Design and Evaluation</a>
<a href="https://arxiv.org/pdf/0901.3751.pdf">Sorting improves word-aligned bitmap indexes</a>
<a href="https://arxiv.org/pdf/1603.06549.pdf">Consistently faster and smaller compressed bitmaps with Roaring</a>