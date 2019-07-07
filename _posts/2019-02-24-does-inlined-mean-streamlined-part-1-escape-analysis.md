---
ID: 11484
title: 'Does Inlined Mean Streamlined? Part 1: Escape Analysis'
author: Richard Startin
post_excerpt: ""
layout: post
theme: minima
published: true
date: 2019-02-24 09:35:00
---
There's a lot of folklore about the importance of inlining in the JVM. Undoubtedly, inlining can improve performance by removing the overhead of function calls, but, more importantly, various optimisations are disabled or reduced in scope when it can't happen. However, I think the importance of inlining is often overstated, especially considering the trade off between flexibility and ability to inline. This post is the first in a series where I use JMH to run simple experiments to assess the impact of failure to inline on C2's ability to optimise programs. This post is about how inlining affects escape analysis, and whether you should care.

Inlining is the process of replacing function calls with the function's code, much like denormalisation of databases. Just as database denormalisation can eliminate the overhead of performing joins at the expense of increasing the level of data duplication and therefore database size, inlining removes the overhead of function calls, at the expense of the amount of space required to represent the program. The analogy breaks down because copying the function's code into the call site also aids an optimising compiler like C2 by increasing the scope of what can be optimised within a method, so C2 does this aggressively. It's well known that there are two ways to confound inlining: code size (`InlineSmallCode` sets the limit of what can be inlined to 2KB by default), and having lots of polymorphism. Failure to inline can also be provoked by the JMH annotation `@CompilerControl(DONT_INLINE)`.

In the first benchmark, I will look at a contrived example of the kind of small method you may find in Java code written in a functional style. Functional programming exploits monads, which represent a generic computation as a wrapper type, a wrapping operation known as the unit function, and a way to compose functions applied to the wrapper type, known as the bind function. You can also think of them as burritos. Some monadic types common in functionally tinged Java are `Either` (contains an instance of one type or another), `Try` (produces an output or an exception) and `Optional` which exists in the JDK. One drawback of monadic types in Java is that the wrapper type needs to be materialised (rather than exist only as a figment of the compiler's imagination) and risks being allocated.

Here is an interface exposing a method returning an `Optional` intended to safely map a potentially null value of type `S` to type `Optional<T>` via a mapping between the unwrapped types `S` and `T`. To avoid measuring the cost of different implementations, it is implemented the same way three times to reach the threshold where Hotspot will give up on inlining calls to the escapee.

```java
public interface Escapee<T> {
  <S> Optional<T> map(S value, Function<S, T> mapper);
}

public class Escapee1<T> implements Escapee<T> {
  @Override
  public <S> Optional<T> map(S value, Function<S, T> mapper) {
    return Optional.ofNullable(value).map(mapper);
  }
}
```

In the benchmark, we can simulate conditions where we call between one and four implementations. We should probably expect the benchmark to behave differently when the input value is null because a different branch will be taken. To isolate the difference in throughput just for taking the other branch, the same function, which allocates an `Instant`, is evaluated on either branch. No attempt is made to make the branch unpredictable since it's beside the point. `Instant.now()` is chosen because it is volatile and impure, meaning that its evaluation shouldn't be eliminated by some other optimisation.

```java  
  @State(Scope.Benchmark)
  public static class InstantEscapeeState {
    @Param({"ONE", "TWO", "THREE", "FOUR"})
    Scenario scenario;
    @Param({"true", "false"})
    boolean isPresent;
    Escapee<Instant>[] escapees;
    int size = 4;
    String input;

    @Setup(Level.Trial)
    public void init() {
      escapees = new Escapee[size];
      scenario.fill(escapees);
      input = isPresent ? "" : null;
    }
  }

  @Benchmark
  @OperationsPerInvocation(4)
  public void mapValue(InstantEscapeeState state, Blackhole bh) {
    for (Escapee<Instant> escapee : state.escapees) {
      bh.consume(escapee.map(state.input, x -> Instant.now()).orElseGet(Instant::now));
    }
  }
```

Based on common knowledge about C2's inlining capabilities, we should expect scenarios THREE and FOUR not to inline, whereas ONE should be inlined, and TWO should be inlined with a conditional. Verifying this well known outcome by printing inlining with `-XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining` is trivial. See Aleksey Shipilёv's <a href="https://shipilev.net/blog/2015/black-magic-method-dispatch/" rel="noopener noreferrer" target="_blank">authoritative post</a> for reference.

The benchmark is run with the following arguments. Tiered compilation is disabled to bypass C1. A large heap is allocated to avoid measuring garbage collection pauses, and the low overhead SerialGC is selected to minimise interference from instrumented write barriers. 

<pre>taskset -c 0 java -jar target/benchmarks.jar -wi 5 -w 1 -r 1 -i 5 -f 3 -rf CSV -rff escapee.csv -prof gc 
-jvmArgs="-XX:-TieredCompilation -XX:+UseSerialGC -mx8G" EscapeeBenchmark.mapValue$</pre>

Despite there being little absolute difference in throughput (the scenarios where we expect inlining to occur have slightly higher throughputs than when we expect inlining not to take place), the results are quite interesting. 

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th title="Field #1">Benchmark</th>
<th title="Field #2">Mode</th>
<th title="Field #3">Threads</th>
<th title="Field #4">Samples</th>
<th title="Field #5">Score</th>
<th title="Field #6">Score Error (99.9%)</th>
<th title="Field #7">Unit</th>
<th title="Field #8">Param: isPresent</th>
<th title="Field #9">Param: scenario</th>
</tr></thead>
<tbody><tr>
<td>mapValue</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">24.013132</td>
<td align="right">0.459482</td>
<td>ops/us</td>
<td>true</td>
<td>ONE</td>
</tr>
<tr>
<td>mapValue</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">22.448583</td>
<td align="right">0.430733</td>
<td>ops/us</td>
<td>true</td>
<td>TWO</td>
</tr>
<tr>
<td>mapValue</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">20.291617</td>
<td align="right">0.898656</td>
<td>ops/us</td>
<td>true</td>
<td>THREE</td>
</tr>
<tr>
<td>mapValue</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">20.651088</td>
<td align="right">0.552091</td>
<td>ops/us</td>
<td>true</td>
<td>FOUR</td>
</tr>
<tr>
<td>mapValue</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">24.625237</td>
<td align="right">0.535002</td>
<td>ops/us</td>
<td>false</td>
<td>ONE</td>
</tr>
<tr>
<td>mapValue</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">24.039407</td>
<td align="right">0.432007</td>
<td>ops/us</td>
<td>false</td>
<td>TWO</td>
</tr>
<tr>
<td>mapValue</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">21.976675</td>
<td align="right">0.741998</td>
<td>ops/us</td>
<td>false</td>
<td>THREE</td>
</tr>
<tr>
<td>mapValue</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">22.183469</td>
<td align="right">0.43514</td>
<td>ops/us</td>
<td>false</td>
<td>FOUR</td>
</tr>
</tbody></table>
</div>

The megamorphic cases are slightly faster when the input value is null, which highlights how easy it would be to not capture the relevant effects at all. When the input value is always null, and when there is only one implementation and the input value is not null, the normalised allocation rate are all 24B/op, and just over half that of the non-null input multi implementation scenarios, which are all about the same at 40B/op.

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th title="Field #1">Benchmark</th>
<th title="Field #2">Mode</th>
<th title="Field #3">Threads</th>
<th title="Field #4">Samples</th>
<th title="Field #5">Score</th>
<th title="Field #6">Score Error (99.9%)</th>
<th title="Field #7">Unit</th>
<th title="Field #8">Param: isPresent</th>
<th title="Field #9">Param: scenario</th>
</tr></thead>
<tbody><tr>
<td>mapValue:·gc.alloc.rate.norm</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">24.000017</td>
<td align="right">0.000001</td>
<td>B/op</td>
<td>true</td>
<td>ONE</td>
</tr>
<tr>
<td>mapValue:·gc.alloc.rate.norm</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">40.000018</td>
<td align="right">0.000001</td>
<td>B/op</td>
<td>true</td>
<td>TWO</td>
</tr>
<tr>
<td>mapValue:·gc.alloc.rate.norm</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">40.00002</td>
<td align="right">0.000001</td>
<td>B/op</td>
<td>true</td>
<td>THREE</td>
</tr>
<tr>
<td>mapValue:·gc.alloc.rate.norm</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">40.00002</td>
<td align="right">0.000001</td>
<td>B/op</td>
<td>true</td>
<td>FOUR</td>
</tr>
<tr>
<td>mapValue:·gc.alloc.rate.norm</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">24.000017</td>
<td align="right">0.000001</td>
<td>B/op</td>
<td>false</td>
<td>ONE</td>
</tr>
<tr>
<td>mapValue:·gc.alloc.rate.norm</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">24.000017</td>
<td align="right">0.000001</td>
<td>B/op</td>
<td>false</td>
<td>TWO</td>
</tr>
<tr>
<td>mapValue:·gc.alloc.rate.norm</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">24.000019</td>
<td align="right">0.000001</td>
<td>B/op</td>
<td>false</td>
<td>THREE</td>
</tr>
<tr>
<td>mapValue:·gc.alloc.rate.norm</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">24.000019</td>
<td align="right">0.000001</td>
<td>B/op</td>
<td>false</td>
<td>FOUR</td>
</tr>
</tbody></table>
</div>

24B/op is the size of instances of the `Instant` class (when a simple garbage collector like SerialGC is used), which contains an 8 byte number of seconds since 1970 and a 4 byte number of nanoseconds, plus a 12 byte object header. So the wrapper type can't have been allocated in these cases! 40B/op includes the 16 bytes taken up by the materialised `Optional` (12 bytes for the header and 4 bytes for a compressed reference to the `Instant`). The difference is caused by the limitations of escape analysis: it gives up trying to prove allocation is unnecessary whenever the allocating method can't be inlined, and incidentally gives up when the allocation takes place within a conditional statement. In scenario TWO, a conditional statement is introduced by inlining two possible implementations, which means each operation allocates the 16 bytes required for the optional.

The signal is fairly weak in this benchmark, and is almost entirely masked by the fact the benchmark will allocate a 24 byte `Instant` per invocation. To accentuate the difference, we can isolate background allocation from the benchmark and track the same metrics.

```java
  @State(Scope.Benchmark)
  public static class StringEscapeeState {
    @Param({"ONE", "TWO", "THREE", "FOUR"})
    Scenario scenario;
    @Param({"true", "false"})
    boolean isPresent;
    Escapee<String>[] escapees;
    int size = 4;
    String input;
    String ifPresent;
    String ifAbsent;

    @Setup(Level.Trial)
    public void init() {
      escapees = new Escapee[size];
      scenario.fill(escapees);
      ifPresent = UUID.randomUUID().toString();
      ifAbsent = UUID.randomUUID().toString();
      input = isPresent ? "" : null;
    }
  }

  @Benchmark
  @OperationsPerInvocation(4)
  public void mapValueNoAllocation(StringEscapeeState state, Blackhole bh) {
    for (Escapee<String> escapee : state.escapees) {
      bh.consume(escapee.map(state.input, x -> state.ifPresent).orElseGet(() -> state.ifAbsent));
    }
  }
```

<pre>taskset -c 0 java -jar target/benchmarks.jar -wi 5 -w 1 -r 1 -i 5 -f 3 -rf CSV -rff escapee-string.csv -prof gc 
-jvmArgs="-XX:-TieredCompilation -XX:+UseSerialGC -mx8G" EscapeeBenchmark.mapValueNoAllocation</pre>

While even the cost of very low intensity realistic work (allocating a timestamp) is enough to mollify failure to inline, when the virtual call is a no-op we can make its impact look quite severe. ONE and TWO are much faster because they at least eliminate the virtual function call in each case, no matter whether the input is null or not.

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th title="Field #1">Benchmark</th>
<th title="Field #2">Mode</th>
<th title="Field #3">Threads</th>
<th title="Field #4">Samples</th>
<th title="Field #5">Score</th>
<th title="Field #6">Score Error (99.9%)</th>
<th title="Field #7">Unit</th>
<th title="Field #8">Param: isPresent</th>
<th title="Field #9">Param: scenario</th>
</tr></thead>
<tbody><tr>
<td>mapValueNoAllocation</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">206.913491</td>
<td align="right">3.003555</td>
<td>ops/us</td>
<td>true</td>
<td>ONE</td>
</tr>
<tr>
<td>mapValueNoAllocation</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">162.014816</td>
<td align="right">4.353872</td>
<td>ops/us</td>
<td>true</td>
<td>TWO</td>
</tr>
<tr>
<td>mapValueNoAllocation</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">77.959095</td>
<td align="right">2.174789</td>
<td>ops/us</td>
<td>true</td>
<td>THREE</td>
</tr>
<tr>
<td>mapValueNoAllocation</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">77.845562</td>
<td align="right">3.592952</td>
<td>ops/us</td>
<td>true</td>
<td>FOUR</td>
</tr>
<tr>
<td>mapValueNoAllocation</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">202.016045</td>
<td align="right">2.830117</td>
<td>ops/us</td>
<td>false</td>
<td>ONE</td>
</tr>
<tr>
<td>mapValueNoAllocation</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">198.241125</td>
<td align="right">2.351662</td>
<td>ops/us</td>
<td>false</td>
<td>TWO</td>
</tr>
<tr>
<td>mapValueNoAllocation</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">88.187145</td>
<td align="right">3.908423</td>
<td>ops/us</td>
<td>false</td>
<td>THREE</td>
</tr>
<tr>
<td>mapValueNoAllocation</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">89.715024</td>
<td align="right">2.234652</td>
<td>ops/us</td>
<td>false</td>
<td>FOUR</td>
</tr>
</tbody></table>
</div>

It's easy to imagine that allocation has been curtailed, only to be caught out by the limitations of escape analysis in the presence of polymorphism. In scenario ONE, there is never any allocation: escape analysis must have worked. In scenario TWO, because of the inlined conditional, the 16 byte `Optional` is allocated once per invocation with non-null input, and when the input is always null, there are fewer allocations. However, when the inlining doesn't work in scenarios THREE and FOUR, an extra 16 bytes is allocated once per invocation, but it's not related to inlining. The unintentional 16 bytes comes from capturing the variable in each case (a 12 byte header and 4 byte compressed reference to the `String`), but how often do you check your benchmarks to ensure you are measuring what you think you are?

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th title="Field #1">Benchmark</th>
<th title="Field #2">Mode</th>
<th title="Field #3">Threads</th>
<th title="Field #4">Samples</th>
<th title="Field #5">Score</th>
<th title="Field #6">Score Error (99.9%)</th>
<th title="Field #7">Unit</th>
<th title="Field #8">Param: isPresent</th>
<th title="Field #9">Param: scenario</th>
</tr></thead>
<tbody><tr>
<td>mapValueNoAllocation:·gc.alloc.rate.norm</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">0.000002</td>
<td>0</td>
<td>B/op</td>
<td>true</td>
<td>ONE</td>
</tr>
<tr>
<td>mapValueNoAllocation:·gc.alloc.rate.norm</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">16.000003</td>
<td>0</td>
<td>B/op</td>
<td>true</td>
<td>TWO</td>
</tr>
<tr>
<td>mapValueNoAllocation:·gc.alloc.rate.norm</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">32.000005</td>
<td>0</td>
<td>B/op</td>
<td>true</td>
<td>THREE</td>
</tr>
<tr>
<td>mapValueNoAllocation:·gc.alloc.rate.norm</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">32.000005</td>
<td>0</td>
<td>B/op</td>
<td>true</td>
<td>FOUR</td>
</tr>
<tr>
<td>mapValueNoAllocation:·gc.alloc.rate.norm</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">0.000002</td>
<td>0</td>
<td>B/op</td>
<td>false</td>
<td>ONE</td>
</tr>
<tr>
<td>mapValueNoAllocation:·gc.alloc.rate.norm</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">0.000002</td>
<td>0</td>
<td>B/op</td>
<td>false</td>
<td>TWO</td>
</tr>
<tr>
<td>mapValueNoAllocation:·gc.alloc.rate.norm</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">16.000005</td>
<td>0</td>
<td>B/op</td>
<td>false</td>
<td>THREE</td>
</tr>
<tr>
<td>mapValueNoAllocation:·gc.alloc.rate.norm</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">16.000005</td>
<td>0</td>
<td>B/op</td>
<td>false</td>
<td>FOUR</td>
</tr>
</tbody></table>
</div>

It's not the sort of thing that can be exploited in real programs, but it looks as if allocations are better eliminated when the method, be it virtual or inlined, only ever sees a null value. Actually, `Optional.empty()` always returns the same instance, so there were no allocations in the first place.

Having contrived a case to accentuate the effect, it's worth noting that the impact of failure to inline is smaller than the difference in the cost of allocating an instance and storing the value with different garbage collectors, which is a cost some developers seem to be unaware of.

```java
  @State(Scope.Benchmark)
  public static class InstantStoreEscapeeState {
    @Param({"ONE", "TWO", "THREE", "FOUR"})
    Scenario scenario;
    @Param({"true", "false"})
    boolean isPresent;
    int size = 4;
    String input;
    Escapee<Instant>[] escapees;
    Instant[] target;

    @Setup(Level.Trial)
    public void init() {
      escapees = new Escapee[size];
      target = new Instant[size];
      scenario.fill(escapees);
      input = isPresent ? "" : null;
    }
  }

  @Benchmark
  @OperationsPerInvocation(4)
  public void mapAndStoreValue(InstantStoreEscapeeState state, Blackhole bh) {
    for (int i = 0; i < state.escapees.length; ++i) {
      state.target[i] = state.escapees[i].map(state.input, x -> Instant.now()).orElseGet(Instant::now);
    }
    bh.consume(state.target);
  }
```

I run the same benchmark in two modes:

<pre>taskset -c 0 java -jar target/benchmarks.jar -wi 5 -w 1 -r 1 -i 5 -f 3 -rf CSV -rff escapee-store-serial.csv 
-prof gc -jvmArgs="-XX:-TieredCompilation -XX:+UseSerialGC -mx8G" EscapeeBenchmark.mapAndStoreValue$
</pre>

<pre>taskset -c 0 java -jar target/benchmarks.jar -wi 5 -w 1 -r 1 -i 5 -f 3 -rf CSV -rff escapee-store-g1.csv 
-prof gc -jvmArgs="-XX:-TieredCompilation -XX:+UseG1GC -mx8G" EscapeeBenchmark.mapAndStoreValue$
</pre>

The cost of changing the garbage collector when <a href="https://richardstartin.github.io/posts/garbage-collectors-affect-microbenchmarks">triggering the write barriers</a> (simple in the case of the serial collector and complex in the case of G1) is about as large as the cost of missing out on inlining. Note that this is <strong>not</strong> an argument that garbage collector overhead is unacceptable!

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th title="Field #1">Benchmark</th>
<th title="Field #2">GC</th>
<th title="Field #3">Mode</th>
<th title="Field #4">Threads</th>
<th title="Field #5">Samples</th>
<th title="Field #6">Score</th>
<th title="Field #7">Score Error (99.9%)</th>
<th title="Field #8">Unit</th>
<th title="Field #9">Param: isPresent</th>
<th title="Field #10">Param: scenario</th>
</tr></thead>
<tbody><tr>
<td>mapAndStoreValue</td>
<td>SerialGC</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">23.739993</td>
<td align="right">0.297493</td>
<td>ops/us</td>
<td>true</td>
<td>ONE</td>
</tr>
<tr>
<td>mapAndStoreValue</td>
<td>SerialGC</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">22.41715</td>
<td align="right">0.502928</td>
<td>ops/us</td>
<td>true</td>
<td>TWO</td>
</tr>
<tr>
<td>mapAndStoreValue</td>
<td>SerialGC</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">21.096494</td>
<td align="right">0.629228</td>
<td>ops/us</td>
<td>true</td>
<td>THREE</td>
</tr>
<tr>
<td>mapAndStoreValue</td>
<td>SerialGC</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">20.656528</td>
<td align="right">0.604725</td>
<td>ops/us</td>
<td>true</td>
<td>FOUR</td>
</tr>
<tr>
<td>mapAndStoreValue</td>
<td>SerialGC</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">24.098976</td>
<td align="right">0.479819</td>
<td>ops/us</td>
<td>false</td>
<td>ONE</td>
</tr>
<tr>
<td>mapAndStoreValue</td>
<td>SerialGC</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">23.759017</td>
<td align="right">0.460972</td>
<td>ops/us</td>
<td>false</td>
<td>TWO</td>
</tr>
<tr>
<td>mapAndStoreValue</td>
<td>SerialGC</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">21.473803</td>
<td align="right">0.411786</td>
<td>ops/us</td>
<td>false</td>
<td>THREE</td>
</tr>
<tr>
<td>mapAndStoreValue</td>
<td>SerialGC</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">21.524173</td>
<td align="right">0.393322</td>
<td>ops/us</td>
<td>false</td>
<td>FOUR</td>
</tr>
<tr>
<td>mapAndStoreValue</td>
<td>G1GC</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">20.522258</td>
<td align="right">0.463444</td>
<td>ops/us</td>
<td>true</td>
<td>ONE</td>
</tr>
<tr>
<td>mapAndStoreValue</td>
<td>G1GC</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">18.520677</td>
<td align="right">0.229133</td>
<td>ops/us</td>
<td>true</td>
<td>TWO</td>
</tr>
<tr>
<td>mapAndStoreValue</td>
<td>G1GC</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">18.359042</td>
<td align="right">0.276809</td>
<td>ops/us</td>
<td>true</td>
<td>THREE</td>
</tr>
<tr>
<td>mapAndStoreValue</td>
<td>G1GC</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">18.446654</td>
<td align="right">0.272189</td>
<td>ops/us</td>
<td>true</td>
<td>FOUR</td>
</tr>
<tr>
<td>mapAndStoreValue</td>
<td>G1GC</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">20.768856</td>
<td align="right">0.496087</td>
<td>ops/us</td>
<td>false</td>
<td>ONE</td>
</tr>
<tr>
<td>mapAndStoreValue</td>
<td>G1GC</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">20.277051</td>
<td align="right">0.411466</td>
<td>ops/us</td>
<td>false</td>
<td>TWO</td>
</tr>
<tr>
<td>mapAndStoreValue</td>
<td>G1GC</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">18.875519</td>
<td align="right">0.399535</td>
<td>ops/us</td>
<td>false</td>
<td>THREE</td>
</tr>
<tr>
<td>mapAndStoreValue</td>
<td>G1GC</td>
<td>thrpt</td>
<td>1</td>
<td align="right">15</td>
<td align="right">18.824234</td>
<td align="right">0.657469</td>
<td>ops/us</td>
<td>false</td>
<td>FOUR</td>
</tr>
</tbody></table>
</div>

Inlining makes escape analysis possible, but is only effective when only one implementation is used. The marginal benefit decreases in the presence of even trivial allocation, but can be expected to increase with the size of the eliminated allocation. The difference can even be smaller than the runtime cost of write barriers in some garbage collectors. My benchmarks are on <a href="https://github.com/richardstartin/runtime-benchmarks/tree/master/src/main/java/com/openkappa/runtime/inlining/escapee" rel="noopener noreferrer" target="_blank">github</a>, they were run with OpenJDK 11+28 on Ubuntu 18.04.2 LTS.

Perhaps this analysis is facile; many optimisations more powerful than escape analysis depend on inlining. The next post in the series will be on the benefits, or lack thereof, of inlining a reduction operation such as a hash code.
