---
ID: 10831
title: 'Garbage Collector Code Artifacts: Card Marking'
author: Richard Startin
post_excerpt: ""
layout: post
theme: jekyll-theme-slate
published: true
date: 2018-04-07 16:03:58
---
In the JVM, lots of evidence of garbage collection mechanics can be seen from JIT compiler output. This may be obvious if you think of garbage collection as a task of book-keeping: the various auxiliary data structures used to track inter-region or inter-generational references, relied on for faster marking, need to be kept up to date somehow. These data structures need maintenance, and this isn't something you control in application code: the maintenance aspect must must be instrumented somehow. If you profile your application's disassembly, you can find artifacts of the various garbage collectors, and these snippets of code can help you understand the throughput tradeoffs of each collector. You <em>can</em> also just read the documentation. 

A simple benchmark to illustrate this would compare the store of a primitive `int` and a boxed `Integer`. It may not be surprising that the classes below can be JIT compiled in very different ways, and that the real difference depends on the selected garbage collector.

```java
public class IntAcceptor {
  private int value;

  public void setValue(int value) {
    this.value = value;
  }
}

public class IntegerAcceptor {
  private Integer value;

  public void setValue(Integer value) {
    this.value = value;
  }
}
```

For instance, the simplest garbage collector, used mostly by specialist applications betting against garbage collection actually happening, is enabled by `-XX:+UseSerialGC`. If you benchmark throughput for storing these values, you will observe  that storing `int`s is cheaper than storing `Integer`s.

It's difficult to measure this accurately because there are numerous pitfalls. If you allocate a new `Integer` for each store, you conflate your measurement with allocation and introduce bias towards the primitive store. If you pre-allocate an `Integer[]` you can make the measured workload more cache-friendly, from a GC book-keeping point of view, which helps reduce the reference store cost. In a multithreaded context, this same property can create bias in the opposite direction. JMH can't prevent any of these biases. Be skeptical about the accuracy or generality of the numbers here (because there are a large number of unexplored dimensions to control, as I have alluded to) but you would hardly notice any difference in a single threaded benchmark storing the same boxed integer repeatedly.

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<tbody><tr>
<td>Benchmark</td>
<td>Mode</td>
<td>Threads</td>
<td>Samples</td>
<td>Score</td>
<td>Score Error (99.9%)</td>
<td>Unit</td>
</tr>
<tr>
<td>SerialGCStoreBenchmark.storeInt</td>
<td>thrpt</td>
<td>1</td>
<td>20</td>
<td>395.370723</td>
<td>10.092432</td>
<td>ops/us</td>
</tr>
<tr>
<td>SerialGCStoreBenchmark.storeInteger</td>
<td>thrpt</td>
<td>1</td>
<td>20</td>
<td>277.329797</td>
<td>18.036629</td>
<td>ops/us</td>
</tr>
</tbody></table>
</div>

You may see a large difference in a multithreaded benchmark, with an `Integer` instance per thread.

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<tbody><tr>
<td>Benchmark</td>
<td>Mode</td>
<td>Threads</td>
<td>Samples</td>
<td>Score</td>
<td>Score Error (99.9%)</td>
<td>Unit</td>
</tr>
<tr>
<td>SerialGCStoreBenchmark.storeInt</td>
<td>thrpt</td>
<td>4</td>
<td>20</td>
<td>1467.401084</td>
<td>5.917960</td>
<td>ops/us</td>
</tr>
<tr>
<td>SerialGCStoreBenchmark.storeInteger</td>
<td>thrpt</td>
<td>4</td>
<td>20</td>
<td>793.880064</td>
<td>459.304449</td>
<td>ops/us</td>
</tr>
</tbody></table>
</div>

The throughput of `storeInteger` seems to have a large error term, here are the iteration figures:

<pre>
Iteration   1: 1176.474 ops/us
Iteration   2: 85.966 ops/us
Iteration   3: 1180.612 ops/us
Iteration   4: 90.930 ops/us
Iteration   5: 1180.955 ops/us
Iteration   6: 1181.966 ops/us
Iteration   7: 88.801 ops/us
Iteration   8: 1180.723 ops/us
Iteration   9: 1177.895 ops/us
Iteration  10: 1138.446 ops/us
Iteration  11: 1177.302 ops/us
Iteration  12: 91.551 ops/us
Iteration  13: 1144.591 ops/us
Iteration  14: 102.143 ops/us
Iteration  15: 1179.683 ops/us
Iteration  16: 1184.222 ops/us
Iteration  17: 85.365 ops/us
Iteration  18: 1183.874 ops/us
Iteration  19: 95.979 ops/us
Iteration  20: 1150.123 ops/us
</pre>

This is bimodal, varying from iteration to iteration between almost as good to an order of magnitude slower, with nothing in between. If you compare the disassembly for loops setting distinct values, such as in my simplistic <a href="https://github.com/richardstartin/runtime-benchmarks/blob/master/src/main/java/com/openkappa/runtime/gc/SerialGCStoreBenchmark.java" rel="noopener" target="_blank">benchmark</a>, you will see the assembly is virtually identical, but you'll notice these instructions for the reference stores:

```asm
  0.98%    1.12%  │  0x00007f54a96462ee: shr    $0x9,%r10
  2.22%    2.17%  │  0x00007f54a96462f2: movabs $0x7f54c1bc5000,%r11
  2.30%    2.69%  │  0x00007f54a96462fc: mov    %r12b,(%r11,%r10,1) 
```

This code does <em>card marking</em>, which tracks bucketed references between different sections of the heap. The byte array is the <em>card table</em>, which has logical pages of 512 bytes. The right shift divides the reference of the stored object by 512 to get the card it resides in. The byte at this index offset by the base address of the page tracking references out of the storing object's card is written to. In other words, a directed link is established between the storing object's page and stored object's page. This is what you would see if you squinted at the heap: the card table is a coarse approximation of the object graph which allows false positives (referenced pages may contain dead references) but no false negatives. 

The writes to the card table are volatile, and the card table is shared between threads, which can induce false sharing when objects in adjacent pages are stored in objects residing in the same page, and the stores happen on different threads. You can use <a href="https://blogs.oracle.com/dave/false-sharing-induced-by-card-table-marking">conditional marking</a> to avoid this because the stored object's page is often already marked. The bimodal behaviour is caused by unlucky combinations of addresses resulting in false sharing of the card table. It doesn't even happen all the time. Setting the `-XX:+UseCondCardMark` the difference gets much smaller, the noise disappears, and conditional marking logic can be seen in the disassembly.


<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<tbody><tr>
<td>Benchmark</td>
<td>Mode</td>
<td>Threads</td>
<td>Samples</td>
<td>Score</td>
<td>Score Error (99.9%)</td>
<td>Unit</td>
</tr>
<tr>
<td>SerialGCStoreBenchmark.storeInt</td>
<td>thrpt</td>
<td>4</td>
<td>20</td>
<td>1467.464828</td>
<td>12.866720</td>
<td>ops/us</td>
</tr>
<tr>
<td>SerialGCStoreBenchmark.storeInteger</td>
<td>thrpt</td>
<td>4</td>
<td>20</td>
<td>1114.612419</td>
<td>6.960193</td>
<td>ops/us</td>
</tr>
</tbody></table>

```asm
                  ╭││  0x00007f003164b9e4: je     0x00007f003164ba04 
                  │││                                                
                  │││                                               
  0.01%    0.00%  │││  0x00007f003164b9e6: mov    %r10,%r8
  4.92%    3.54%  │││  0x00007f003164b9e9: shr    $0x9,%r8
  0.01%    0.00%  │││  0x00007f003164b9ed: movabs $0x7f0048492000,%r9
  3.48%    2.12%  │││  0x00007f003164b9f7: add    %r8,%r9
  0.02%    0.01%  │││  0x00007f003164b9fa: movsbl (%r9),%ecx
  6.51%    6.53%  │││  0x00007f003164b9fe: test   %ecx,%ecx
  1.71%    1.85%  │╰│  0x00007f003164ba00: jne    0x00007f003164b994
                  │ │                                               
                  │ │                                               
                  │ │                                               
  4.76%    5.29%  │ ╰  0x00007f003164ba02: jmp    0x00007f003164b9a0
                  ↘    0x00007f003164ba04: mov    $0xfffffff6,%esi

```

I <em>intended</em> to provoke this behaviour, but what if I had been measuring something else and hadn't ensured conditional marking was enabled?

Card marking is common in older garbage collectors because it has low overhead, particularly with conditional marking, but different collectors intercept stores differently, and you can reverse engineer them all without reading the source code. In fact, Nitsan Wakart has written a <a href="http://psy-lob-saw.blogspot.co.uk/2014/10/the-jvm-write-barrier-card-marking.html" rel="noopener" target="_blank">great post</a> all about store barriers. 

The point of this post is that you can detect garbage collector mechanisms with benchmarks, you just need to write them to provoke the actions you think a garbage collector should make, and look for crop circles in the disassembly. However, this assumes you have some kind of mental model of a garbage collector to start with! The new ones are getting very creative, and you might not be able to guess what they do. In principle, garbage collector implementations could modify any application code so these artifacts could be anywhere.