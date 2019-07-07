---
ID: 11100
title: UUIDs and Compressibility
author: Richard Startin
post_excerpt: ""
layout: post
published: true
date: 2018-07-21 20:56:54
---
Universally unique identifiers, or UUIDs, are often used for database primary keys in scenarios where coordination of persistence is either impossible or impractical. UUIDs offer very good probabilistic guarantees of collision avoidance, at the cost of 128 bits per key. 128 bits for a key is quite problematic in key scans and joins: with appropriately structured data, these algorithms can benefit significantly from vector processing, but at 128 bits per element, vectorisation is probably a lost cause. The 128 bit cost is also a fixed cost, even if your database has fewer than one quintilliard rows. By virtue of being random enough to avoid collisions when generated in a distributed system, there is no way to compress UUID keys to the number of bits required to identify each record in the dataset. Data engineering is about tradeoffs, and none of this is to say UUIDs should never be used, but it is prudent to be aware of the costs. All of this applies in the best case: assuming the keys are stored in their binary format! How bad can it get if UUIDs are stored as text? Can compression undo the damage?

If you work with a relational database like Postgres, you can use an implementation specific <code class="java">uuid` type to ensure UUIDs take up as little space as possible. However, having worked on several projects using NoSQL databases, I have seen people store UUIDs as text on at least two occasions (though this is not the fault of the databases!). How harmful this is depends on the character encoding used, but UTF-8 is quite common (for the characters found in a UUID, this is equivalent to ISO-8859-1). A UUID represented by a string like <em>"9289f568-c33f-4667-8a3d-092aa4e21262"</em> can take up the following sizes, depending on the encoding used.

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<tbody><tr>
<th>Format</th>
<th>Size (bytes)</th>
<th>Ratio</th>
</tr>
<tr>
<td>binary</td>
<td>16</td>
<td>1</td>
</tr>
<tr>
<td>ISO-8859-1</td>
<td>36</td>
<td>2.25</td>
</tr>
<tr>
<td>UTF-8</td>
<td>36</td>
<td>2.25</td>
</tr>
<tr>
<td>UTF-16</td>
<td>74</td>
<td>4.625</td>
</tr>
</tbody></table>
</div>

The real issue here is not so much the extra storage burden, because keys are usually much smaller than the values, but that the keys are used to process queries. A representation requiring 2-5x more space requires 2-5x more data to pass through the processor when evaluating queries. Many NoSQL databases offer <a href="https://en.wikipedia.org/wiki/Succinct_data_structure" rel="noopener" target="_blank">succinct</a> compression options for keys, which allow the keys to be processed without decompression at a small computational cost, such as the prefix and delta encoding <a href="https://archive.cloudera.com/cdh5/cdh/5/hbase-0.98.6-cdh5.3.8/book/compression.html">available</a> in HBase. This approach can work wonders with well structured keys, but this will do absolutely nothing if your keys are random. 

Even heavyweight compression techniques requiring global or block level decompression before evaluation can't recover the bloat in a textual representation of a UUID because <em>the text is almost as random as the bytes</em>. I compressed collections of 1M UUIDs using compression algorithms typically reserved for "cold data": gzip, snappy and LZ4, using the code on <a href="https://github.com/richardstartin/compression-experiment/blob/master/src/main/java/uk/co/openkappa/compression/UUIDBlockCompression.java" rel="noopener" target="_blank">github</a>. 

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<tbody><tr>
<th>Compression</th>
<th>Encoding</th>
<th>Count</th>
<th>Size (MB)</th>
</tr>
<tr>
<td>Uncompressed</td>
<td>binary</td>
<td>1000000</td>
<td>15.26</td>
</tr>
<tr>
<td>Uncompressed</td>
<td>ISO-8859-1</td>
<td>1000000</td>
<td>34.33</td>
</tr>
<tr>
<td>Uncompressed</td>
<td>UTF-16</td>
<td>1000000</td>
<td>70.57</td>
</tr>
<tr>
<td>GZIP</td>
<td>binary</td>
<td>1000000</td>
<td>15.26</td>
</tr>
<tr>
<td>GZIP</td>
<td>ISO-8859-1</td>
<td>1000000</td>
<td>19.50</td>
</tr>
<tr>
<td>GZIP</td>
<td>UTF-16</td>
<td>1000000</td>
<td>23.73</td>
</tr>
<tr>
<td>LZ4</td>
<td>binary</td>
<td>1000000</td>
<td>15.32</td>
</tr>
<tr>
<td>LZ4</td>
<td>ISO-8859-1</td>
<td>1000000</td>
<td>32.56</td>
</tr>
<tr>
<td>LZ4</td>
<td>UTF-16</td>
<td>1000000</td>
<td>50.16</td>
</tr>
<tr>
<td>Snappy</td>
<td>binary</td>
<td>1000000</td>
<td>15.26</td>
</tr>
<tr>
<td>Snappy</td>
<td>ISO-8859-1</td>
<td>1000000</td>
<td>33.99</td>
</tr>
<tr>
<td>Snappy</td>
<td>UTF-16</td>
<td>1000000</td>
<td>37.97</td>
</tr>
</tbody></table>
</div>

Assuming you are OK with treating your keys as cold data, none of these algorithms will undo the inflation. What's interesting, assuming you've never thought about it before, is that none of these algorithms can compress the binary representation of the UUIDs. This is because the UUIDs are random, and random enough to be taken as unique in any given trillion year epoch. Even though there are only one million values, which could be represented by 20 bits per value, none of the compression algorithms improves on 128 bits per value. This reminds me of a passage from <em>Theories of Everything</em> by John D. Barrow:

<blockquote>The goal of science is to make sense of the diversity of nature. [Science] employs observation to gather information about the world and to test predictions about how the world will react to new circumstances, but in between these two procedures lies the heart of the scientific process. This is nothing more than the transformation of lists of observational data into abbreviated form by the recognition of patterns. The recognition of such a pattern allows the information content of the observed sequence of events to be replaced by a shorthand formula which possesses the same, or almost the same, information content...

We can extend this image of science in a manner that sharpens its focus. Suppose we are presented with any string of symbols. They do not have to be numbers but let us assume for the sake of illustration that they are. We say that the string is 'random' if there is no other representation of the string which is shorter than itself. But we say it is 'non-random' if there does exist an abbreviated representation.</blockquote>

Random data can't be compressed, and inflated textual representations of random bits are almost as random as the bits themselves, as far as any existing compression algorithm is concerned. Efficient representation of data requires the identification and exploitation of patterns, and using UUIDs instead of naturally occurring composite keys introduces randomness where there could often be order.