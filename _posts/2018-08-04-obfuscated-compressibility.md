---
ID: 11148
title: Obfuscated Compressibility
author: Richard Startin
post_excerpt: ""
layout: post
redirect_from:
  - /obfuscated-compressibility/

published: true
date: 2018-08-04 13:01:42
tags: compression
---
In any real world system there are often multiple layers of encoding and compression applied to data; a base 64 encoded image in an HTML file may be gzipped for transport; a snappy compressed byte array in a datastore might be base 64 encoded in a JSON message. Encoding and lossless compression are invertible transformations, and an invertible transformation must neither create nor destroy information. Yet, as can be seen in the <a href="https://richardstartin.github.io/posts/uuids-and-compressibility/">adversarial case of UUIDs</a>, various textual encodings prevent compression algorithms from reaching their potential (that is, the information content of the data).

Base 64 encoding translates arbitrary binary data to valid UTF-8 text, and is used for representing binary data in JSON messages, images embedded in HTML, and various tokens used for authentication and authorisation. Base 64 maps each 6-bit subword of a byte stream to one of 64 valid bytes, so requires four bytes to encode three input bytes: a 33% overhead. 

What would happen if we base 64 encode incompressible binary data (i.e. already compressed, or an encryption key or similar) in JSON, and then apply transport level compression to the JSON? Can any compression algorithm undo the 33% inflation? Of GZIP, LZ4 and Snappy, only GZIP is capable of doing so (albeit extremely slowly). The transformation is opaque to the much faster LZ4 and Snappy algorithms.

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th title="Field #1">Compression</th>
<th title="Field #2">Encoding</th>
<th title="Field #3">Count</th>
<th title="Field #4">Compressed Size (MB)</th>
</tr></thead>
<tbody><tr>
<td>Uncompressed</td>
<td>binary</td>
<td align="right">1000000</td>
<td align="right">976.56</td>
</tr>
<tr>
<td>Uncompressed</td>
<td>base64</td>
<td align="right">1000000</td>
<td align="right">1304.63</td>
</tr>
<tr>
<td>GZIP</td>
<td>binary</td>
<td align="right">1000000</td>
<td align="right">976.86</td>
</tr>
<tr>
<td>GZIP</td>
<td>base64</td>
<td align="right">1000000</td>
<td align="right">988.74</td>
</tr>
<tr>
<td>LZ4</td>
<td>binary</td>
<td align="right">1000000</td>
<td align="right">980.39</td>
</tr>
<tr>
<td>LZ4</td>
<td>base64</td>
<td align="right">1000000</td>
<td align="right">1309.74</td>
</tr>
<tr>
<td>Snappy</td>
<td>binary</td>
<td align="right">1000000</td>
<td align="right">976.61</td>
</tr>
<tr>
<td>Snappy</td>
<td>base64</td>
<td align="right">1000000</td>
<td align="right">1304.69</td>
</tr>
</tbody></table>
</div>

Writing monotonically increasing numbers into a `byte[]` prior to base 64 encoding tells another story. GZIP, as usual, takes a very long time to achieve a reasonable compression ratio, but the ratio depends on the encoding. LZ4 and Snappy are insensitive to base 64 encoding but they can't compress beyond the size of the original data.

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th title="Field #1">Compression</th>
<th title="Field #2">Encoding</th>
<th title="Field #3">Count</th>
<th title="Field #4">Compressed Size (MB)</th>
</tr></thead>
<tbody><tr>
<td>Uncompressed</td>
<td>binary</td>
<td align="right">1000000</td>
<td align="right">976.56</td>
</tr>
<tr>
<td>Uncompressed</td>
<td>base64</td>
<td align="right">1000000</td>
<td align="right">1304.63</td>
</tr>
<tr>
<td>GZIP</td>
<td>binary</td>
<td align="right">1000000</td>
<td align="right">337.67</td>
</tr>
<tr>
<td>GZIP</td>
<td>base64</td>
<td align="right">1000000</td>
<td align="right">523.80</td>
</tr>
<tr>
<td>LZ4</td>
<td>binary</td>
<td align="right">1000000</td>
<td align="right">980.39</td>
</tr>
<tr>
<td>LZ4</td>
<td>base64</td>
<td align="right">1000000</td>
<td align="right">987.99</td>
</tr>
<tr>
<td>Snappy</td>
<td>binary</td>
<td align="right">1000000</td>
<td align="right">976.61</td>
</tr>
<tr>
<td>Snappy</td>
<td>base64</td>
<td align="right">1000000</td>
<td align="right">948.17</td>
</tr>
</tbody></table>
</div>

There is only a single bit difference between each subsequent four byte sequence in this data: it could be abbreviated by storing the first value, and the difference of the difference between each four byte sequence, and the position of each inflection point. This particular data <em>could</em> take up less than 100 bits, but in order to exploit it, we would have to be expecting this pattern and hope it hasn't been scrambled base 64. 

Text encoding is a good way to confound a compression algorithm, but how do compression algorithms compose? This isn't that odd a question: imagine you store a compressed BLOB in some kind of datastore, and provide an HTTP interface to that datastore. Maybe even without realising it, it's likely that the compression algorithm used for the BLOBs will be composed with GZIP for the transport, and if the interchange format is JSON, there will be a layer of base 64 encoding involved too.

For monotonic integers, neither LZ4 nor snappy compress the data, but at least they don't get in GZIP's way.

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th>Compression</th>
<th>Pre-Compression</th>
<th>Count</th>
<th>Compressed Size (MB)</th>
</tr></thead>
<tbody><tr>
<td>Uncompressed</td>
<td>Uncompressed</td>
<td align="right">1000000</td>
<td align="right">976.56</td>
</tr>
<tr>
<td>Uncompressed</td>
<td>Snappy</td>
<td align="right">1000000</td>
<td align="right">981.33</td>
</tr>
<tr>
<td>Uncompressed</td>
<td>LZ4</td>
<td align="right">1000000</td>
<td align="right">981.33</td>
</tr>
<tr>
<td>LZ4</td>
<td>Uncompressed</td>
<td align="right">1000000</td>
<td align="right">980.39</td>
</tr>
<tr>
<td>LZ4</td>
<td>Snappy</td>
<td align="right">1000000</td>
<td align="right">981.32</td>
</tr>
<tr>
<td>LZ4</td>
<td>LZ4</td>
<td align="right">1000000</td>
<td align="right">981.32</td>
</tr>
<tr>
<td>Snappy</td>
<td>Uncompressed</td>
<td align="right">1000000</td>
<td align="right">976.61</td>
</tr>
<tr>
<td>Snappy</td>
<td>Snappy</td>
<td align="right">1000000</td>
<td align="right">981.37</td>
</tr>
<tr>
<td>Snappy</td>
<td>LZ4</td>
<td align="right">1000000</td>
<td align="right">981.37</td>
</tr>
<tr>
<td>GZIP</td>
<td>Uncompressed</td>
<td align="right">1000000</td>
<td align="right">337.67</td>
</tr>
<tr>
<td>GZIP</td>
<td>Snappy</td>
<td align="right">1000000</td>
<td align="right">339.95</td>
</tr>
<tr>
<td>GZIP</td>
<td>LZ4</td>
<td align="right">1000000</td>
<td align="right">339.95</td>
</tr>
</tbody></table>
</div>

It's worth stressing that both LZ4 and Snappy <em>can</em> compress <em>some</em> data very well, they just aren't well suited to monotonic integers. Both algorithms are much faster than GZIP, prioritising speed over compression ratios. I haven't measured it, but the GZIP code used in these benchmarks is too slow to be practical, and its compression ratio is still a long way from optimal. 

I often see decisions to use a compression algorithm taken rather arbitrarily, without due consideration of the data being compressed. This is often driven by the quest for modularity. Modularity entails composition, which can occasionally be toxic, and often requires that we forget aspects of domain knowledge that could be exploited to great effect. 



<blockquote>My code for this blog post is at <a href="https://github.com/richardstartin/compression-experiment" rel="noopener" target="_blank">github</a>.</blockquote>
