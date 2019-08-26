---
ID: 10448
title: Building RoaringBitmaps from Streams
author: Richard Startin
post_excerpt: ""
layout: post

published: true
date: 2018-01-29 18:37:10
---
<a href="https://github.com/RoaringBitmap/RoaringBitmap" rel="noopener" target="_blank">RoaringBitmap</a> is a <a href="http://db.ucsd.edu/wp-content/uploads/2017/03/sidm338-wangA.pdf" rel="noopener" target="_blank">fast</a> compressed bitset format. In the Java implementation of Roaring, it was until recently preferential to build a bitset in one go from sorted data; there were performance penalties of varying magnitude for incremental or unordered insertions. In a recent <a href="https://github.com/RoaringBitmap/RoaringBitmap/pull/199" rel="noopener" target="_blank">pull request</a>, I wanted to improve incremental monotonic insertion so I could build bitmaps from streams, but sped up unsorted batch creation significantly by accident.

<h3>Incremental Ordered Insertion</h3>

If you want to build a bitmap, you can do so efficiently with the `RoaringBitmap.bitmapOf` factory method.

```java
int[] data = ...
RoaringBitmap bitmap = RoaringBitmap.bitmapOf(data);
```

However, I often find that I want to stream integers into a bitmap. Given that the integers being inserted into a bitmap often represent indices into an array, such a stream is likely to be monotonic. You might implement this like so:

```java
IntStream stream = ...
RoaringBitmap bitmap = new RoaringBitmap();
stream.forEach(bitmap::add);
```

While this is OK, it has a few inefficiencies compared to the batch creation method.

<ul>
	<li>Indirection: the container being written to must be located on each insertion</li>
	<li>Eagerness: the cardinality must be kept up to date on each insertion</li>
	<li>Allocation pressure: the best container type can't be known in advance. Choice of container may change as data is inserted, this requires allocations of new instances.</li>
</ul>

You could also collect the stream into an `int[]` and use the batch method, but it could be a large temporary object with obvious drawbacks.

<h3>OrderedWriter</h3>

The solution I proposed is to create a writer object (<a href="https://github.com/RoaringBitmap/RoaringBitmap/blob/master/roaringbitmap/src/main/java/org/roaringbitmap/RoaringBitmapWriter.java" rel="noopener" target="_blank">OrderedWriter</a>) which allocates a small buffer of 8KB, to use as a bitmap large enough to cover 16 bits. The stream to bitmap code becomes:

```java
IntStream stream = ...
RoaringBitmap bitmap = new RoaringBitmap();
OrderedWriter writer = new OrderedWriter(bitmap);
stream.forEach(writer::add);
writer.flush(); // clear the buffer out
```

This is implemented so that changes in key (where the most significant 16 bits of each integer is stored) trigger a flush of the buffer. 

```java
  public void add(int value) {
    short key = Util.highbits(value);
    short low = Util.lowbits(value);
    if (key != currentKey) {
      if (Util.compareUnsigned(key, currentKey) < 0) {
        throw new IllegalStateException("Must write in ascending key order");
      }
      flush();
    }
    int ulow = low & 0xFFFF;
    bitmap[(ulow >>> 6)] |= (1L << ulow);
    currentKey = key;
    dirty = true;
  }
```

When a flush occurs, a container type is chosen and appended to the bitmap's prefix index.

```java
  public void flush() {
    if (dirty) {
      RoaringArray highLowContainer = underlying.highLowContainer;
      // we check that it's safe to append since RoaringArray.append does no validation
      if (highLowContainer.size > 0) {
        short key = highLowContainer.getKeyAtIndex(highLowContainer.size - 1);
        if (Util.compareUnsigned(currentKey, key) <= 0) {
          throw new IllegalStateException("Cannot write " + currentKey + " after " + key);
        }
      }
      highLowContainer.append(currentKey, chooseBestContainer());
      clearBitmap();
      dirty = false;
    }
  }
```

There are significant performance advantages in this approach. There is no indirection cost, and no searches in the prefix index for containers: the writes are just buffered. The buffer is small enough to fit in cache, and containers only need to be created when the writer is flushed, which happens whenever a new key is seen, or when `flush` is called manually. During a flush, the cardinality can be computed in one go, the best container can be chosen, and run optimisation only has to happen once. Computing the cardinality is the only bottleneck - it requires 1024 calls to `Long.bitCount` which can't be vectorised in a language like Java. It can't be incremented on insertion without either sacrificing idempotence or incurring the cost of a membership check. After the flush, the buffer needs to be cleared, using a call to `Arrays.fill` which is vectorised. So, despite the cost of the buffer, this can be quite efficient.

This approach isn't universally applicable. For instance, you must write data in ascending order of the most significant 16 bits. You must also remember to flush the writer when you're finished: until you've called flush, the data in the last container may not be in the bitmap. For my particular use case, this is reasonable. However, there are times when this is not fit for purpose, such as if you are occasionally inserting values and expect them to be available to queries immediately. In general, if you don't know when you'll stop adding data to the bitmap, this isn't a good fit because you won't know when to call flush. 

<h3>Benchmark</h3>

I <a href="https://github.com/RoaringBitmap/RoaringBitmap/blob/master/jmh/src/main/java/org/roaringbitmap/writer/WriteSequential.java" rel="noopener" target="_blank">benchmarked</a> the two approaches, varying bitmap sizes and randomness (likelihood of there <em>not</em> being a compressible run), and was amazed to find that this approach actually beats having a sorted array and using `RoaringBitmap.bitmapOf`. Less surprising was beating the existing API for incremental adds (this was the goal in the first place). Lower is better:

<img src="https://richardstartin.github.io/assets/2018/01/incremental.png" alt="" width="1488" height="583" class="alignnone size-full wp-image-10474" />

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th>Benchmark</th>
<th>(randomness)</th>
<th>(size)</th>
<th>Mode</th>
<th>Cnt</th>
<th>Score</th>
<th>Error</th>
<th>Units</th>
</tr></thead>
<tbody><tr>
<td>buildRoaringBitmap</td>
<td align="right">0.1</td>
<td align="right">10000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">54.263</td>
<td align="right">3.393</td>
<td>us/op</td>
</tr>
<tr>
<td>buildRoaringBitmap</td>
<td align="right">0.1</td>
<td align="right">100000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">355.188</td>
<td align="right">15.234</td>
<td>us/op</td>
</tr>
<tr>
<td>buildRoaringBitmap</td>
<td align="right">0.1</td>
<td align="right">1000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">3567.839</td>
<td align="right">135.149</td>
<td>us/op</td>
</tr>
<tr>
<td>buildRoaringBitmap</td>
<td align="right">0.1</td>
<td align="right">10000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">31982.046</td>
<td align="right">1227.325</td>
<td>us/op</td>
</tr>
<tr>
<td>buildRoaringBitmap</td>
<td align="right">0.5</td>
<td align="right">10000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">53.855</td>
<td align="right">0.887</td>
<td>us/op</td>
</tr>
<tr>
<td>buildRoaringBitmap</td>
<td align="right">0.5</td>
<td align="right">100000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">357.671</td>
<td align="right">14.111</td>
<td>us/op</td>
</tr>
<tr>
<td>buildRoaringBitmap</td>
<td align="right">0.5</td>
<td align="right">1000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">3556.152</td>
<td align="right">243.671</td>
<td>us/op</td>
</tr>
<tr>
<td>buildRoaringBitmap</td>
<td align="right">0.5</td>
<td align="right">10000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">34385.971</td>
<td align="right">3864.143</td>
<td>us/op</td>
</tr>
<tr>
<td>buildRoaringBitmap</td>
<td align="right">0.9</td>
<td align="right">10000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">59.354</td>
<td align="right">10.385</td>
<td>us/op</td>
</tr>
<tr>
<td>buildRoaringBitmap</td>
<td align="right">0.9</td>
<td align="right">100000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">374.245</td>
<td align="right">54.485</td>
<td>us/op</td>
</tr>
<tr>
<td>buildRoaringBitmap</td>
<td align="right">0.9</td>
<td align="right">1000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">3712.684</td>
<td align="right">657.964</td>
<td>us/op</td>
</tr>
<tr>
<td>buildRoaringBitmap</td>
<td align="right">0.9</td>
<td align="right">10000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">37223.976</td>
<td align="right">4691.297</td>
<td>us/op</td>
</tr>
<tr>
<td>incrementalNativeAdd</td>
<td align="right">0.1</td>
<td align="right">10000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">115.213</td>
<td align="right">31.909</td>
<td>us/op</td>
</tr>
<tr>
<td>incrementalNativeAdd</td>
<td align="right">0.1</td>
<td align="right">100000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">911.925</td>
<td align="right">127.922</td>
<td>us/op</td>
</tr>
<tr>
<td>incrementalNativeAdd</td>
<td align="right">0.1</td>
<td align="right">1000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">8889.49</td>
<td align="right">320.821</td>
<td>us/op</td>
</tr>
<tr>
<td>incrementalNativeAdd</td>
<td align="right">0.1</td>
<td align="right">10000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">102819.877</td>
<td align="right">14247.868</td>
<td>us/op</td>
</tr>
<tr>
<td>incrementalNativeAdd</td>
<td align="right">0.5</td>
<td align="right">10000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">116.878</td>
<td align="right">28.232</td>
<td>us/op</td>
</tr>
<tr>
<td>incrementalNativeAdd</td>
<td align="right">0.5</td>
<td align="right">100000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">947.076</td>
<td align="right">128.255</td>
<td>us/op</td>
</tr>
<tr>
<td>incrementalNativeAdd</td>
<td align="right">0.5</td>
<td align="right">1000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">7190.443</td>
<td align="right">202.012</td>
<td>us/op</td>
</tr>
<tr>
<td>incrementalNativeAdd</td>
<td align="right">0.5</td>
<td align="right">10000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">98843.303</td>
<td align="right">4325.924</td>
<td>us/op</td>
</tr>
<tr>
<td>incrementalNativeAdd</td>
<td align="right">0.9</td>
<td align="right">10000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">101.694</td>
<td align="right">6.579</td>
<td>us/op</td>
</tr>
<tr>
<td>incrementalNativeAdd</td>
<td align="right">0.9</td>
<td align="right">100000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">816.411</td>
<td align="right">65.678</td>
<td>us/op</td>
</tr>
<tr>
<td>incrementalNativeAdd</td>
<td align="right">0.9</td>
<td align="right">1000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">9114.624</td>
<td align="right">412.152</td>
<td>us/op</td>
</tr>
<tr>
<td>incrementalNativeAdd</td>
<td align="right">0.9</td>
<td align="right">10000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">108793.694</td>
<td align="right">22562.527</td>
<td>us/op</td>
</tr>
<tr>
<td>incrementalUseOrderedWriter</td>
<td align="right">0.1</td>
<td align="right">10000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">23.573</td>
<td align="right">5.962</td>
<td>us/op</td>
</tr>
<tr>
<td>incrementalUseOrderedWriter</td>
<td align="right">0.1</td>
<td align="right">100000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">289.588</td>
<td align="right">36.814</td>
<td>us/op</td>
</tr>
<tr>
<td>incrementalUseOrderedWriter</td>
<td align="right">0.1</td>
<td align="right">1000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">2785.659</td>
<td align="right">49.385</td>
<td>us/op</td>
</tr>
<tr>
<td>incrementalUseOrderedWriter</td>
<td align="right">0.1</td>
<td align="right">10000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">29489.758</td>
<td align="right">2601.39</td>
<td>us/op</td>
</tr>
<tr>
<td>incrementalUseOrderedWriter</td>
<td align="right">0.5</td>
<td align="right">10000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">23.57</td>
<td align="right">1.536</td>
<td>us/op</td>
</tr>
<tr>
<td>incrementalUseOrderedWriter</td>
<td align="right">0.5</td>
<td align="right">100000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">276.488</td>
<td align="right">9.662</td>
<td>us/op</td>
</tr>
<tr>
<td>incrementalUseOrderedWriter</td>
<td align="right">0.5</td>
<td align="right">1000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">2799.408</td>
<td align="right">198.77</td>
<td>us/op</td>
</tr>
<tr>
<td>incrementalUseOrderedWriter</td>
<td align="right">0.5</td>
<td align="right">10000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">28313.626</td>
<td align="right">1976.042</td>
<td>us/op</td>
</tr>
<tr>
<td>incrementalUseOrderedWriter</td>
<td align="right">0.9</td>
<td align="right">10000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">22.345</td>
<td align="right">1.574</td>
<td>us/op</td>
</tr>
<tr>
<td>incrementalUseOrderedWriter</td>
<td align="right">0.9</td>
<td align="right">100000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">280.205</td>
<td align="right">36.987</td>
<td>us/op</td>
</tr>
<tr>
<td>incrementalUseOrderedWriter</td>
<td align="right">0.9</td>
<td align="right">1000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">2779.732</td>
<td align="right">93.456</td>
<td>us/op</td>
</tr>
<tr>
<td>incrementalUseOrderedWriter</td>
<td align="right">0.9</td>
<td align="right">10000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">30568.591</td>
<td align="right">2140.826</td>
<td>us/op</td>
</tr>
</tbody></table>
</div>

These benchmarks don't go far enough to support replacing `RoaringBitmap.bitmapOf`.

<h3>Unsorted Input Data</h3>

In the cases benchmarked, this approach seems to be worthwhile. I can't actually think of a case where someone would want to build a bitmap from unsorted data, but it occurred to me that this approach might be fast enough to cover the cost of a sort. `OrderedWriter` is also relaxed enough that it only needs the most significant 16 bits to be monotonic, so a full sort isn't necessary. Implementing a <a href="https://github.com/RoaringBitmap/RoaringBitmap/blob/master/roaringbitmap/src/main/java/org/roaringbitmap/Util.java#L995" rel="noopener" target="_blank">radix sort</a> on the most significant 16 bits (stable in the least significant 16 bits), prior to incremental insertion via an `OrderedWriter`, leads to huge increases in performance over `RoaringBitmap.bitmapOf`. The implementation is as follows:

```java
  public static RoaringBitmap bitmapOfUnordered(final int... data) {
    partialRadixSort(data);
    RoaringBitmap bitmap = new RoaringBitmap();
    OrderedWriter writer = new OrderedWriter(bitmap);
    for (int i : data) {
      writer.add(i);
    }
    writer.flush();
    return bitmap;
  }
```

It did very well, according to <a href="https://github.com/RoaringBitmap/RoaringBitmap/blob/master/jmh/src/main/java/org/roaringbitmap/writer/WriteUnordered.java" rel="noopener" target="_blank">benchmarks</a>, even against various implementations of sort prior to `RoaringBitmap.bitmapOf`. Lower is better:

<img src="https://richardstartin.github.io/assets/2018/01/unordered.png" alt="" width="1517" height="603" class="alignnone size-full wp-image-10475" />

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th>Benchmark</th>
<th>(randomness)</th>
<th>(size)</th>
<th>Mode</th>
<th>Cnt</th>
<th>Score</th>
<th>Error</th>
<th>Units</th>
</tr></thead>
<tbody><tr>
<td>bitmapOf</td>
<td align="right">0.1</td>
<td align="right">10000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">1058.106</td>
<td align="right">76.013</td>
<td>us/op</td>
</tr>
<tr>
<td>bitmapOf</td>
<td align="right">0.1</td>
<td align="right">100000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">12323.905</td>
<td align="right">976.68</td>
<td>us/op</td>
</tr>
<tr>
<td>bitmapOf</td>
<td align="right">0.1</td>
<td align="right">1000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">171812.526</td>
<td align="right">9593.879</td>
<td>us/op</td>
</tr>
<tr>
<td>bitmapOf</td>
<td align="right">0.1</td>
<td align="right">10000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">3376296.157</td>
<td align="right">170362.195</td>
<td>us/op</td>
</tr>
<tr>
<td>bitmapOf</td>
<td align="right">0.5</td>
<td align="right">10000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">1096.663</td>
<td align="right">477.795</td>
<td>us/op</td>
</tr>
<tr>
<td>bitmapOf</td>
<td align="right">0.5</td>
<td align="right">100000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">12836.177</td>
<td align="right">1674.54</td>
<td>us/op</td>
</tr>
<tr>
<td>bitmapOf</td>
<td align="right">0.5</td>
<td align="right">1000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">171998.126</td>
<td align="right">4176</td>
<td>us/op</td>
</tr>
<tr>
<td>bitmapOf</td>
<td align="right">0.5</td>
<td align="right">10000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">3707804.439</td>
<td align="right">974532.361</td>
<td>us/op</td>
</tr>
<tr>
<td>bitmapOf</td>
<td align="right">0.9</td>
<td align="right">10000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">1124.881</td>
<td align="right">65.673</td>
<td>us/op</td>
</tr>
<tr>
<td>bitmapOf</td>
<td align="right">0.9</td>
<td align="right">100000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">14585.589</td>
<td align="right">1894.788</td>
<td>us/op</td>
</tr>
<tr>
<td>bitmapOf</td>
<td align="right">0.9</td>
<td align="right">1000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">198506.813</td>
<td align="right">8552.218</td>
<td>us/op</td>
</tr>
<tr>
<td>bitmapOf</td>
<td align="right">0.9</td>
<td align="right">10000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">3723942.934</td>
<td align="right">423704.363</td>
<td>us/op</td>
</tr>
<tr>
<td>bitmapOfUnordered</td>
<td align="right">0.1</td>
<td align="right">10000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">174.583</td>
<td align="right">17.475</td>
<td>us/op</td>
</tr>
<tr>
<td>bitmapOfUnordered</td>
<td align="right">0.1</td>
<td align="right">100000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">1768.613</td>
<td align="right">86.543</td>
<td>us/op</td>
</tr>
<tr>
<td>bitmapOfUnordered</td>
<td align="right">0.1</td>
<td align="right">1000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">17889.705</td>
<td align="right">135.714</td>
<td>us/op</td>
</tr>
<tr>
<td>bitmapOfUnordered</td>
<td align="right">0.1</td>
<td align="right">10000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">192645.352</td>
<td align="right">6482.726</td>
<td>us/op</td>
</tr>
<tr>
<td>bitmapOfUnordered</td>
<td align="right">0.5</td>
<td align="right">10000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">157.351</td>
<td align="right">3.254</td>
<td>us/op</td>
</tr>
<tr>
<td>bitmapOfUnordered</td>
<td align="right">0.5</td>
<td align="right">100000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">1674.919</td>
<td align="right">90.138</td>
<td>us/op</td>
</tr>
<tr>
<td>bitmapOfUnordered</td>
<td align="right">0.5</td>
<td align="right">1000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">16900.458</td>
<td align="right">778.999</td>
<td>us/op</td>
</tr>
<tr>
<td>bitmapOfUnordered</td>
<td align="right">0.5</td>
<td align="right">10000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">185399.32</td>
<td align="right">4383.485</td>
<td>us/op</td>
</tr>
<tr>
<td>bitmapOfUnordered</td>
<td align="right">0.9</td>
<td align="right">10000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">145.642</td>
<td align="right">1.257</td>
<td>us/op</td>
</tr>
<tr>
<td>bitmapOfUnordered</td>
<td align="right">0.9</td>
<td align="right">100000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">1515.845</td>
<td align="right">82.914</td>
<td>us/op</td>
</tr>
<tr>
<td>bitmapOfUnordered</td>
<td align="right">0.9</td>
<td align="right">1000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">15807.597</td>
<td align="right">811.048</td>
<td>us/op</td>
</tr>
<tr>
<td>bitmapOfUnordered</td>
<td align="right">0.9</td>
<td align="right">10000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">167863.49</td>
<td align="right">3501.132</td>
<td>us/op</td>
</tr>
<tr>
<td>partialSortThenBitmapOf</td>
<td align="right">0.1</td>
<td align="right">10000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">1060.152</td>
<td align="right">168.802</td>
<td>us/op</td>
</tr>
<tr>
<td>partialSortThenBitmapOf</td>
<td align="right">0.1</td>
<td align="right">100000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">10942.731</td>
<td align="right">347.583</td>
<td>us/op</td>
</tr>
<tr>
<td>partialSortThenBitmapOf</td>
<td align="right">0.1</td>
<td align="right">1000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">100606.506</td>
<td align="right">24705.341</td>
<td>us/op</td>
</tr>
<tr>
<td>partialSortThenBitmapOf</td>
<td align="right">0.1</td>
<td align="right">10000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">1035448.545</td>
<td align="right">157383.713</td>
<td>us/op</td>
</tr>
<tr>
<td>partialSortThenBitmapOf</td>
<td align="right">0.5</td>
<td align="right">10000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">1029.883</td>
<td align="right">100.291</td>
<td>us/op</td>
</tr>
<tr>
<td>partialSortThenBitmapOf</td>
<td align="right">0.5</td>
<td align="right">100000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">10472.509</td>
<td align="right">832.719</td>
<td>us/op</td>
</tr>
<tr>
<td>partialSortThenBitmapOf</td>
<td align="right">0.5</td>
<td align="right">1000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">101144.032</td>
<td align="right">16908.087</td>
<td>us/op</td>
</tr>
<tr>
<td>partialSortThenBitmapOf</td>
<td align="right">0.5</td>
<td align="right">10000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">958242.087</td>
<td align="right">39650.946</td>
<td>us/op</td>
</tr>
<tr>
<td>partialSortThenBitmapOf</td>
<td align="right">0.9</td>
<td align="right">10000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">1008.413</td>
<td align="right">70.999</td>
<td>us/op</td>
</tr>
<tr>
<td>partialSortThenBitmapOf</td>
<td align="right">0.9</td>
<td align="right">100000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">10458.34</td>
<td align="right">600.416</td>
<td>us/op</td>
</tr>
<tr>
<td>partialSortThenBitmapOf</td>
<td align="right">0.9</td>
<td align="right">1000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">103945.644</td>
<td align="right">2026.26</td>
<td>us/op</td>
</tr>
<tr>
<td>partialSortThenBitmapOf</td>
<td align="right">0.9</td>
<td align="right">10000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">1065638.269</td>
<td align="right">102257.059</td>
<td>us/op</td>
</tr>
<tr>
<td>setupCost</td>
<td align="right">0.1</td>
<td align="right">10000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">6.577</td>
<td align="right">0.121</td>
<td>us/op</td>
</tr>
<tr>
<td>setupCost</td>
<td align="right">0.1</td>
<td align="right">100000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">61.378</td>
<td align="right">24.113</td>
<td>us/op</td>
</tr>
<tr>
<td>setupCost</td>
<td align="right">0.1</td>
<td align="right">1000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">1021.588</td>
<td align="right">536.68</td>
<td>us/op</td>
</tr>
<tr>
<td>setupCost</td>
<td align="right">0.1</td>
<td align="right">10000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">13182.341</td>
<td align="right">196.773</td>
<td>us/op</td>
</tr>
<tr>
<td>setupCost</td>
<td align="right">0.5</td>
<td align="right">10000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">7.139</td>
<td align="right">2.216</td>
<td>us/op</td>
</tr>
<tr>
<td>setupCost</td>
<td align="right">0.5</td>
<td align="right">100000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">60.847</td>
<td align="right">23.395</td>
<td>us/op</td>
</tr>
<tr>
<td>setupCost</td>
<td align="right">0.5</td>
<td align="right">1000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">800.888</td>
<td align="right">14.711</td>
<td>us/op</td>
</tr>
<tr>
<td>setupCost</td>
<td align="right">0.5</td>
<td align="right">10000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">13431.625</td>
<td align="right">553.44</td>
<td>us/op</td>
</tr>
<tr>
<td>setupCost</td>
<td align="right">0.9</td>
<td align="right">10000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">6.599</td>
<td align="right">0.09</td>
<td>us/op</td>
</tr>
<tr>
<td>setupCost</td>
<td align="right">0.9</td>
<td align="right">100000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">60.946</td>
<td align="right">22.511</td>
<td>us/op</td>
</tr>
<tr>
<td>setupCost</td>
<td align="right">0.9</td>
<td align="right">1000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">813.445</td>
<td align="right">4.896</td>
<td>us/op</td>
</tr>
<tr>
<td>setupCost</td>
<td align="right">0.9</td>
<td align="right">10000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">13374.943</td>
<td align="right">349.314</td>
<td>us/op</td>
</tr>
<tr>
<td>sortThenBitmapOf</td>
<td align="right">0.1</td>
<td align="right">10000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">636.23</td>
<td align="right">13.423</td>
<td>us/op</td>
</tr>
<tr>
<td>sortThenBitmapOf</td>
<td align="right">0.1</td>
<td align="right">100000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">7411.756</td>
<td align="right">174.264</td>
<td>us/op</td>
</tr>
<tr>
<td>sortThenBitmapOf</td>
<td align="right">0.1</td>
<td align="right">1000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">92299.305</td>
<td align="right">3651.161</td>
<td>us/op</td>
</tr>
<tr>
<td>sortThenBitmapOf</td>
<td align="right">0.1</td>
<td align="right">10000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">1096374.443</td>
<td align="right">162575.234</td>
<td>us/op</td>
</tr>
<tr>
<td>sortThenBitmapOf</td>
<td align="right">0.5</td>
<td align="right">10000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">634.957</td>
<td align="right">47.447</td>
<td>us/op</td>
</tr>
<tr>
<td>sortThenBitmapOf</td>
<td align="right">0.5</td>
<td align="right">100000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">7939.074</td>
<td align="right">409.328</td>
<td>us/op</td>
</tr>
<tr>
<td>sortThenBitmapOf</td>
<td align="right">0.5</td>
<td align="right">1000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">93505.427</td>
<td align="right">5409.749</td>
<td>us/op</td>
</tr>
<tr>
<td>sortThenBitmapOf</td>
<td align="right">0.5</td>
<td align="right">10000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">1147933.592</td>
<td align="right">57485.51</td>
<td>us/op</td>
</tr>
<tr>
<td>sortThenBitmapOf</td>
<td align="right">0.9</td>
<td align="right">10000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">661.072</td>
<td align="right">6.717</td>
<td>us/op</td>
</tr>
<tr>
<td>sortThenBitmapOf</td>
<td align="right">0.9</td>
<td align="right">100000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">7915.506</td>
<td align="right">356.148</td>
<td>us/op</td>
</tr>
<tr>
<td>sortThenBitmapOf</td>
<td align="right">0.9</td>
<td align="right">1000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">93403.343</td>
<td align="right">5454.583</td>
<td>us/op</td>
</tr>
<tr>
<td>sortThenBitmapOf</td>
<td align="right">0.9</td>
<td align="right">10000000</td>
<td>avgt</td>
<td align="right">5</td>
<td align="right">1095960.734</td>
<td align="right">85753.917</td>
<td>us/op</td>
</tr>
</tbody></table>
</div>

It looks like there are good performance gains available here, but these things tend to depend on particular data sets. I would be interested in hearing from anyone who has tried to use this class in a real application.