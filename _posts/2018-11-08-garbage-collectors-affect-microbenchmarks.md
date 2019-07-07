---
ID: 11405
title: >
  Garbage Collectors Affect
  Microbenchmarks
author: Richard Startin
post_excerpt: ""
layout: post
theme: minima
published: true
date: 2018-11-08 23:13:45
---
When comparing garbage collectors there are two key metrics: how much time is spent collecting garbage, and the maximum pause time. There's another dimension to the choice of garbage collector though: how it instruments JIT compiled code and the consequences of that instrumentation. The cost of this instrumentation is usually a tiny price to pay for improved pause times which only matters to some applications, but it makes writing benchmarks for code which assigns and reads references potentially error prone: sometimes the effect of changing the garbage collector is larger than the difference between two competing implementations. To illustrate this I compare a microbenchmark for a document cursor with three garbage collectors: ParallelOld (the default in OpenJDK8), G1 (the default from OpenJDK 9 onwards) and the experimental ZGC available from JDK11 onwards.

The code being benchmarked is simple. Imagine a stream of JSON-like documents which need to be translated into another format. The documents contain a special field called the cursor, for which, for some reason, the last-encountered value must always be known. There is a callback which will be invoked whenever a value of a certain type is encountered (e.g. `writeLong(long value)`) and a callback which will be invoked whenever a name of an attribute is encountered: `writeName(String name)`. The interface being implemented cannot be changed to include a method `writeLong(String name, long value)` because it is owned by a third party, so the state between the two calls must be saved between the invocations. On each invocation of the `writeName` callback, we could save the name in the cursor object.

```java
public class CursoredScanner2 implements CursoredScanner {

  private final String trigger;
  private String current;
  private long cursor;

  public CursoredScanner2(String trigger) {
    this.trigger = trigger;
  }

  @Override
  public void writeName(String name) {
    this.current = name;
  }

  @Override
  public void writeLong(long value) {
    if (trigger.equals(current)) {
      this.cursor = value;
    }
  }

  @Override
  public long getCursor() {
    return cursor;
  }

}
```

Alternatively, we could do the same number of comparisons by storing whether the last name was the name of the cursor or not:

```java
public class CursoredScanner1 implements CursoredScanner {

  private final String trigger;

  private boolean atCursor;
  private long cursor;

  public CursoredScanner1(String trigger) {
    this.trigger = trigger;
  }

  @Override
  public void writeName(String name) {
    this.atCursor = trigger.equals(name);
  }

  @Override
  public void writeLong(long value) {
    if (atCursor) {
      this.cursor = value;
    }
  }

  @Override
  public long getCursor() {
    return cursor;
  }
}
```

Each implementation performs the same number of string comparisons. Supposing performance matters, how can one of the alternatives be selected? I wrote a <a href="https://github.com/richardstartin/runtime-benchmarks/blob/master/src/main/java/com/openkappa/runtime/gc/CursoredScannerBenchmark.java" rel="noopener" target="_blank">benchmark</a> which captures the cursor value from documents of varying sizes. I ran this benchmark with different garbage collector settings with JDK11. With ParallelOld, I saw that `CursoredScanner2` was slightly slower.

<pre>-XX:+UseCondCardMark -XX:+UseParallelOldGC -mx1G -XX:+AlwaysPreTouch</pre>

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th title="Field #1">Benchmark</th>
<th title="Field #2">Mode</th>
<th title="Field #3">Threads</th>
<th title="Field #4">Samples</th>
<th title="Field #5">Score</th>
<th title="Field #6">Score Error (99.9%)</th>
<th title="Field #7">Unit</th>
<th title="Field #8">Param: scannerType</th>
<th title="Field #9">Param: size</th>
<th title="Field #10">Param: triggerName</th>
</tr></thead>
<tbody><tr>
<td>scan</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">58.081438</td>
<td align="right">1.008727</td>
<td>ops/us</td>
<td>SCANNER1</td>
<td align="right">10</td>
<td>trigger1</td>
</tr>
<tr>
<td>scan</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">6.586134</td>
<td align="right">0.173920</td>
<td>ops/us</td>
<td>SCANNER1</td>
<td align="right">100</td>
<td>trigger1</td>
</tr>
<tr>
<td>scan</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">49.402537</td>
<td align="right">0.943554</td>
<td>ops/us</td>
<td>SCANNER2</td>
<td align="right">10</td>
<td>trigger1</td>
</tr>
<tr>
<td>scan</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">5.248657</td>
<td align="right">0.135281</td>
<td>ops/us</td>
<td>SCANNER2</td>
<td align="right">100</td>
<td>trigger1</td>
</tr>
</tbody></table>
</div>

The cost here can be attributed to the <a href="https://richardstartin.github.io/posts/garbage-collector-code-artifacts-card-marking/" rel="noopener" target="_blank">card marking</a> which keeps the approximation of inter-generational references up to date when references are assigned (see <a href="https://github.com/richardstartin/runtime-benchmarks/blob/master/src/main/resources/cursor/pgc.perfasm#L2022" rel="noopener" target="_blank">here</a>). By avoiding assigning the reference in `CursoredScanner1`, the garbage collector doesn't need to instrument anything at all, because the object graph isn't being mutated.

G1 offers significant reductions in maximum pause times by structuring the heap and tracking references differently, it also instruments reference assignments to keep its book-keeping data structures up to date. The effect of this is pronounced in this benchmark, the barrier can be seen <a href="https://github.com/richardstartin/runtime-benchmarks/blob/master/src/main/resources/cursor/g1gc.perfasm#L644" rel="noopener" target="_blank">here</a> with some skid implicating the innocent adjacent instruction.

<pre>-XX:+UseG1GC -mx1G -XX:+AlwaysPreTouch</pre>

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th title="Field #1">Benchmark</th>
<th title="Field #2">Mode</th>
<th title="Field #3">Threads</th>
<th title="Field #4">Samples</th>
<th title="Field #5">Score</th>
<th title="Field #6">Score Error (99.9%)</th>
<th title="Field #7">Unit</th>
<th title="Field #8">Param: scannerType</th>
<th title="Field #9">Param: size</th>
<th title="Field #10">Param: triggerName</th>
</tr></thead>
<tbody><tr>
<td>scan</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">62.633572</td>
<td align="right">0.995514</td>
<td>ops/us</td>
<td>SCANNER1</td>
<td align="right">10</td>
<td>trigger1</td>
</tr>
<tr>
<td>scan</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">7.660122</td>
<td align="right">0.231402</td>
<td>ops/us</td>
<td>SCANNER1</td>
<td align="right">100</td>
<td>trigger1</td>
</tr>
<tr>
<td>scan</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">23.833586</td>
<td align="right">0.379903</td>
<td>ops/us</td>
<td>SCANNER2</td>
<td align="right">10</td>
<td>trigger1</td>
</tr>
<tr>
<td>scan</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">2.757419</td>
<td align="right">0.148344</td>
<td>ops/us</td>
<td>SCANNER2</td>
<td align="right">100</td>
<td>trigger1</td>
</tr>
</tbody></table>
</div>

What about ZGC, one of the two upcoming ultra low pause garbage collectors? I can't pretend to understand in detail how ZGC works (beyond what I can glean from profilers) but suffice it to say: it works differently, and instruments application code differently. Rather than intercepting reference assignment, it seems to intercept reads. It’s not clear why both implementations perform slightly worse than `CursoredScanner1` with G1 or ParallelOld, but there's not much to choose between the two when using ZGC.

<pre>-XX:+UnlockExperimentalVMOptions -XX:+UseZGC -mx1G -XX:+AlwaysPreTouch</pre>

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th title="Field #1">Benchmark</th>
<th title="Field #2">Mode</th>
<th title="Field #3">Threads</th>
<th title="Field #4">Samples</th>
<th title="Field #5">Score</th>
<th title="Field #6">Score Error (99.9%)</th>
<th title="Field #7">Unit</th>
<th title="Field #8">Param: scannerType</th>
<th title="Field #9">Param: size</th>
<th title="Field #10">Param: triggerName</th>
</tr></thead>
<tbody><tr>
<td>scan</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">43.761915</td>
<td align="right">1.160516</td>
<td>ops/us</td>
<td>SCANNER1</td>
<td align="right">10</td>
<td>trigger1</td>
</tr>
<tr>
<td>scan</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">6.190803</td>
<td align="right">0.101114</td>
<td>ops/us</td>
<td>SCANNER1</td>
<td align="right">100</td>
<td>trigger1</td>
</tr>
<tr>
<td>scan</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">39.080922</td>
<td align="right">0.826591</td>
<td>ops/us</td>
<td>SCANNER2</td>
<td align="right">10</td>
<td>trigger1</td>
</tr>
<tr>
<td>scan</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">4.763075</td>
<td align="right">0.126938</td>
<td>ops/us</td>
<td>SCANNER2</td>
<td align="right">100</td>
<td>trigger1</td>
</tr>
</tbody></table>
</div>

Am I making a case for using ParallelOld and avoiding assigning references because the throughput is slightly better? Not really, while it's possible that's appropriate in some applications, the point is that unless benchmarks focus exclusively on primitive types, the garbage collector has to be considered, and results need to be qualified by this choice. It would be very hard to choose between these implementations without knowing in advance which garbage collector would be in use.

As an aside, this is the first time I have run ZGC, so I'm keen to track down the read barrier I have heard about. It looks like the sequence of instructions `mov`, `test`, `jne`  occurs on each read:

```asm
0x00007fe47c765295: mov    0x30(%r10),%r9
0x00007fe47c765299: test   %r9,0x20(%r15)
0x00007fe47c76529d: jne    0x00007fe47c765b68 
0x00007fe47c7652a3: mov    0x10(%r9),%r14    
0x00007fe47c7652a7: test   %r14,0x20(%r15)
0x00007fe47c7652ab: jne    0x00007fe47c765b76  
```

The assembly above can be seen whenever a reference is read, and sets up a data dependency between reads: the `mov` instruction must happen before the test instruction, which may trigger the `jne`, so the second move must depend on the jump and can't be reordered. I was wondering what the purpose of this was, and if the data dependency was the means or the end, and what's in `r15` and found a decent <a href="https://dinfuehr.github.io/blog/a-first-look-into-zgc/" rel="noopener" target="_blank">article</a> about this. Aleksey Shipilëv, who writes garbage collectors for a living and is better placed to interpret this output, gave some feedback: in Hotspot, `r15` is the base address for thread local storage. Here, `r15 + 0x20` is ZGC's so called bad mask, and failing the test means that the object needs to be marked or relocated. Neither marking nor relocation actually show up in this profile because there isn't enough garbage generated to trigger it, so the code at 0x00007fe47c765b68 can't be seen. If the test passes nothing need happen, and the next reference is read (and intercepted itself). What jumps out at me here is the data dependency, but there's also no obvious bottleneck in the profile.