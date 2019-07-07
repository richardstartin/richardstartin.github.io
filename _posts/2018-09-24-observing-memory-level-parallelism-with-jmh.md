---
ID: 11345
post_title: >
  Observing Memory Level Parallelism with
  JMH
author: Richard Startin
post_excerpt: ""
layout: post
permalink: >
  http://richardstartin.uk/observing-memory-level-parallelism-with-jmh/
published: true
post_date: 2018-09-24 21:55:32
---
Quite some time ago I observed an <a href="http://richardstartin.uk/stages/" rel="noopener" target="_blank">effect</a> where breaking a cache-inefficient shuffle algorithm into short stages could improve throughput: when cache misses were likely, an improvement could be seen in throughput as a function of stage length. The implementations benchmarked were as follows, where `op` is either precomputed (a closure over an array of indices to swap) or a call to `ThreadLocalRandom`:

```java
  @Benchmark
  public void shuffle(Blackhole bh) {
    for (int i = data.length; i > 1; i--)
      swap(data, i - 1, op.applyAsInt(i));
    bh.consume(data);
  }

  @Benchmark
  public void shuffleBuffered(Blackhole bh) {
    for (int i = data.length; i - unroll > 1; i -= unroll) {
      for (int j = 0; j < buffer.length; ++j) {
        buffer[j] = op.applyAsInt(i - j);
      }
      for (int j = 0; j < buffer.length; ++j) {
        swap(data, i - j - 1, buffer[j]);
      }
    }
    bh.consume(data);
  }

  private static void swap(int[] arr, int i, int j) {
    arr[i] ^= arr[j];
    arr[j] ^= arr[i];
    arr[i] ^= arr[j];
  }
```

I couldn't explain the effect observed in terms of the default performance counters made available by JMH, but offered an intuitive explanation that the cache miss could be shared between four independent chains of execution so that cache misses in a given chain would not stall the others. This intuition was gleaned from perfasm: I guessed the bottleneck on this load was due to cache misses. In the simple shuffle, there was one big hit:

```asm
 73.97%   63.58%  │      ││  0x00007f8405c0a272: mov    %eax,0xc(%r11,%rcx,4) 
```

Executing the staged shuffle, I saw several smaller bottlenecks and could only guess the simpler code within each stage had more parallelism; these cache misses were happening at the same time and independently.

```asm
 10.33%   11.23%   ││  0x00007fdb35c09250: mov    %r9d,0xc(%rsi,%r10,4)  
 ...  
 10.40%   10.66%   ││  0x00007fdb35c09283: mov    %r9d,0x8(%rsi,%r10,4) 
```

Travis Downs left a great <a href="http://richardstartin.uk/stages/#comment-5918" rel="noopener" target="_blank">comment</a> on the post pointing me in the direction of the counters `l1d_pend_miss.pending` and `l1d_pend_miss.pending_cycles`. What do these counters mean? Many descriptions for counters are infuriating, <code language-"java">l1d_pend_miss.pending` especially so:

<blockquote>"This event counts duration of L1D miss outstanding, that is each
cycle number of Fill Buffers (FB) outstanding required by
Demand Reads. FB either is held by demand loads, or it is held by
non-demand loads and gets hit at least once by demand. The
valid outstanding interval is defined until the FB deallocation by
one of the following ways: from FB allocation, if FB is allocated
by demand; from the demand Hit FB, if it is allocated by
hardware or software prefetch.
Note: In the L1D, a Demand Read contains cacheable or
noncacheable demand loads, including ones causing cache-line
splits and reads due to page walks resulted from any request
type." (<a href="https://download.01.org/perfmon/index/broadwell.html" rel="noopener" target="_blank">source</a>)</blockquote>

In the words of the Virgin Mary, come again? There is clarity in the terseness of the description in the <a href="https://www.intel.com/content/dam/www/public/us/en/documents/manuals/64-ia-32-architectures-software-developer-vol-3b-part-2-manual.pdf" rel="noopener" target="_blank">Intel® 64 and IA-32 Architectures Software Developer’s Manual</a>.

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<tbody><tr>
<td>L1D_PEND_MISS.PENDING</td>
<td>Increments the number of outstanding L1D misses every cycle.</td>
</tr>
<tr>
<td>L1D_PEND_MISS.PENDING_CYCLES</td>
<td>Cycles with at least one outstanding L1D misses from this logical processor.</td>
</tr>
</tbody></table>
</div>

The first counter records how many loads from non L1 memory locations are in flight during a cycle (that is, how many L1 cache misses are happening right now), increasing whenever there is at least one cache miss happening, and increasing until the load is complete. The second counter records how many cycles have some kind of outstanding cache miss in flight during the cycle. If there's pipelining taking place, the first counter can increase by more than one per cycle, and if at least some work is done without experiencing a cache miss, the second counter will be less than the total number of cycles, and if there are two or more cache misses outstanding at the same time, the counter will take a smaller value than if the cache misses had taken place sequentially. Therefore, their ratio  `l1d_pend_miss.pending / l1d_pend_miss.pending_cycles`indicates how much memory level parallelism exists, that is, to what extent loads take place at the same time.

Can this be measured in JMH with the perfnorm profiler? Yes, I couldn't find any documentation for it but reverse engineered this from the `LinuxPerfNormProfiler` source code:

<pre>
-prof perfnorm:events=l1d_pend_miss.pending,l1d_pend_miss.pending_cycles
</pre>

Note that this argument will override the standard events, so CPI, cycles and so on need to be added at the command line explicitly. Now the hypothetical parallel cache misses can be quantified. The figures for shuffle (the implementation without any staging) is reassuringly flat as a function of stage length, whereas a clear positive trend can be seen in both the throughput and MLP ratio for the staged implementation.

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th title="Field #1">Mode</th>
<th title="Field #2">Benchmark</th>
<th title="Field #3">8</th>
<th title="Field #4">16</th>
<th title="Field #5">32</th>
<th title="Field #6">64</th>
</tr></thead>
<tbody><tr>
<td>PRECOMPUTED</td>
<td>shuffle</td>
<td align="right">0.347</td>
<td align="right">0.352</td>
<td align="right">0.345</td>
<td align="right">0.37</td>
</tr>
<tr>
<td>PRECOMPUTED</td>
<td>shuffle:l1d_pend_miss.pending</td>
<td align="right">17390603073</td>
<td align="right">17718936860</td>
<td align="right">15979073823</td>
<td align="right">20057689191</td>
</tr>
<tr>
<td>PRECOMPUTED</td>
<td>shuffle:l1d_pend_miss.pending_cycles</td>
<td align="right">3657159215</td>
<td align="right">3706319384</td>
<td align="right">3489256633</td>
<td align="right">3930306563</td>
</tr>
<tr>
<td>PRECOMPUTED</td>
<td>shuffle:ratio</td>
<td align="right">4.76</td>
<td align="right">4.78</td>
<td align="right">4.58</td>
<td align="right">5.10</td>
</tr>
<tr>
<td>THREAD_LOCAL_RANDOM</td>
<td>shuffle</td>
<td align="right">0.217</td>
<td align="right">0.233</td>
<td align="right">0.231</td>
<td align="right">0.214</td>
</tr>
<tr>
<td>THREAD_LOCAL_RANDOM</td>
<td>shuffle:l1d_pend_miss.pending</td>
<td align="right">18246771955</td>
<td align="right">17801360193</td>
<td align="right">17736302365</td>
<td align="right">19638836068</td>
</tr>
<tr>
<td>THREAD_LOCAL_RANDOM</td>
<td>shuffle:l1d_pend_miss.pending_cycles</td>
<td align="right">7280468758</td>
<td align="right">7093396781</td>
<td align="right">7086435578</td>
<td align="right">7843415714</td>
</tr>
<tr>
<td>THREAD_LOCAL_RANDOM</td>
<td>shuffle:ratio</td>
<td align="right">2.51</td>
<td align="right">2.51</td>
<td align="right">2.50</td>
<td align="right">2.50</td>
</tr>
<tr>
<td>THREAD_LOCAL_RANDOM</td>
<td>shuffleBuffered</td>
<td align="right">0.248</td>
<td align="right">0.307</td>
<td align="right">0.326</td>
<td align="right">0.345</td>
</tr>
<tr>
<td>THREAD_LOCAL_RANDOM</td>
<td>shuffleBuffered:l1d_pend_miss.pending</td>
<td align="right">21899069718</td>
<td align="right">23064517091</td>
<td align="right">23320550954</td>
<td align="right">22387833224</td>
</tr>
<tr>
<td>THREAD_LOCAL_RANDOM</td>
<td>shuffleBuffered:l1d_pend_miss.pending_cycles</td>
<td align="right">6203611528</td>
<td align="right">5021906699</td>
<td align="right">4539979273</td>
<td align="right">4132226201</td>
</tr>
<tr>
<td>THREAD_LOCAL_RANDOM</td>
<td>shuffleBuffered:ratio</td>
<td align="right">3.53</td>
<td align="right">4.59</td>
<td align="right">5.14</td>
<td align="right">5.42</td>
</tr>
</tbody></table>
</div>