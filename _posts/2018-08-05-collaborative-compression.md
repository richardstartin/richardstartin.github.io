---
ID: 11175
title: Collaborative Compression
author: Richard Startin
post_excerpt: ""
layout: default
redirect_from:
  - /collaborative-compression/

published: true
date: 2018-08-05 22:15:20
---
I have recently become interested in the way the effects of compression algorithms and text encoding compose. I started looking at this in my <a href="https://richardstartin.github.io/posts/obfuscated-compressibility/" rel="noopener" target="_blank">last post</a>. Base 64 encoding extracts and maps each 6-bit subword of a byte stream to one of 64 possible bytes, which is guaranteed to waste 2 bits per byte, but can encode any binary data as UTF-8 text. On a block of incompressible binary data encoded as base 64, neither LZ4 nor Snappy can compress the text to the size of the original binary data, whereas GZIP can (undo a 33% inflation). With monotonically increasing integers, LZ4 and Snappy achieve size parity with uncompressed binary data, whereas GZIP compression can be less effective on base 64 encoded text than on equivalent binary data.

I was interested to see if using LZ4 or Snappy as an intermediate step between base 64 and GZIP would make a difference. Compressing monotonic integers again, my expectation was that LZ4/Snappy could "undo" the base 64 bloat, to get to parity in composition with GZIP on raw binary data, but that's not what happened:

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th>Compression</th>
<th>Transformation</th>
<th>Count</th>
<th>Compressed Size (MB)</th>
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
<td>Uncompressed</td>
<td>base64/snappy</td>
<td align="right">1000000</td>
<td align="right">969.20</td>
</tr>
<tr>
<td>Uncompressed</td>
<td>base64/lz4</td>
<td align="right">1000000</td>
<td align="right">993.98</td>
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
<td>GZIP</td>
<td>base64/snappy</td>
<td align="right">1000000</td>
<td align="right">61.60</td>
</tr>
<tr>
<td>GZIP</td>
<td>base64/lz4</td>
<td align="right">1000000</td>
<td align="right">31.53</td>
</tr>
</tbody></table>
</div>   

I had already noted that all three algorithms had poor compression ratios for this case, which is better suited to delta encoding. Applying base 64 encoding prior to a fast compression algorithm seems to prime the input for GZIP. I'm so confused by this result that I spent some time on sanity checks: verifying that the results are truly decompressible. 

This isn't very exciting: the result is not competitive with delta encoding, and I ran the same test with a sinusoidal byte stream and saw the opposite effect.

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th title="Field #1">Compression</th>
<th title="Field #2">Transformation</th>
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
<td>Uncompressed</td>
<td>base64/snappy</td>
<td align="right">1000000</td>
<td align="right">1087.73</td>
</tr>
<tr>
<td>Uncompressed</td>
<td>base64/lz4</td>
<td align="right">1000000</td>
<td align="right">1089.67</td>
</tr>
<tr>
<td>GZIP</td>
<td>binary</td>
<td align="right">1000000</td>
<td align="right">27.74</td>
</tr>
<tr>
<td>GZIP</td>
<td>base64</td>
<td align="right">1000000</td>
<td align="right">69.12</td>
</tr>
<tr>
<td>GZIP</td>
<td>base64/snappy</td>
<td align="right">1000000</td>
<td align="right">282.52</td>
</tr>
<tr>
<td>GZIP</td>
<td>base64/lz4</td>
<td align="right">1000000</td>
<td align="right">283.81</td>
</tr>
</tbody></table>
</div>

Still, it's hard to predict how multiple layers of data representation will interact.