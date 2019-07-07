---
ID: 10213
title: The Much Aligned Garbage Collector
author: Richard Startin
post_excerpt: ""
layout: post
published: true
date: 2018-01-03 21:22:04
---
A power of two is often a good choice for the size of an array. Sometimes you might see this being exploited to replace an integer division with a bitwise intersection. You can see why with a toy benchmark of a bloom filter, which deliberately folds in a representative cost of a hash function and array access to highlight the significance of the differential cost of the division mechanism to a method that does real work: 

```java
@State(Scope.Thread)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
public class BloomFilter {

  private long[] bitset;

  @Param({"1000", "1024"})
  int size;


  @Setup(Level.Trial)
  public void init() {
    bitset = DataUtil.createLongArray(size);
  }

  @Benchmark
  public boolean containsAnd() {
    int hash = hash();
    int pos = hash & (size - 1);
    return (bitset[pos >>> 6] & (1L << pos)) != 0;
  }

  @Benchmark
  public boolean containsAbsMod() {
    int hash = hash();
    int pos = Math.abs(hash % size);
    return (bitset[pos >>> 6] & (1L << pos)) != 0;
  }

  private int hash() {
    return ThreadLocalRandom.current().nextInt(); // a stand in for a hash function;
  }
}
```

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th>Benchmark</th>
<th>Mode</th>
<th>Threads</th>
<th>Samples</th>
<th>Score</th>
<th>Score Error (99.9%)</th>
<th>Unit</th>
<th>Param: size</th>
</tr></thead>
<tbody><tr>
<td>containsAbsMod</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">104.063744</td>
<td align="right">4.068283</td>
<td>ops/us</td>
<td align="right">1000</td>
</tr>
<tr>
<td>containsAbsMod</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">103.849577</td>
<td align="right">4.991040</td>
<td>ops/us</td>
<td align="right">1024</td>
</tr>
<tr>
<td>containsAnd</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right"><strong>161.917397</strong></td>
<td align="right">3.807912</td>
<td>ops/us</td>
<td align="right">1024</td>
</tr>
</tbody></table>
</div>

Disregarding the case which produces an incorrect result, you can do two thirds as many lookups again in the same period of time if you just use a 1024 element bloom filter. Note that the compiler clearly won't magically transform cases like `AbsMod 1024`; you need to do this yourself. You can readily see this property exploited in any open source bit set, hash set, or bloom filter you care to look at. This is boring, at least, we often get this right by accident. What is quite interesting is a multiplicative decrease in throughput of DAXPY as a result of this same choice of lengths:

```java
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@State(Scope.Thread)
public class DAXPYAlignment {

  @Param({"250", "256", "1000", "1024"})
  int size;

  double s;
  double[] a;
  double[] b;

  @Setup(Level.Trial)
  public void init() {
    s = ThreadLocalRandom.current().nextDouble();
    a = createDoubleArray(size);
    b = createDoubleArray(size);
  }

  @Benchmark
  public void daxpy(Blackhole bh) {
    for (int i = 0; i < a.length; ++i) {
      a[i] += s * b[i];
    }
    bh.consume(a);
  }
}
```

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th>Benchmark</th>
<th>Mode</th>
<th>Threads</th>
<th>Samples</th>
<th>Score</th>
<th>Score Error (99.9%)</th>
<th>Unit</th>
<th>Param: size</th>
</tr></thead>
<tbody><tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">23.499857</td>
<td align="right">0.891309</td>
<td>ops/us</td>
<td align="right">250</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">22.425412</td>
<td align="right">0.989512</td>
<td>ops/us</td>
<td align="right">256</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right"><strong>2.420674</strong></td>
<td align="right">0.098991</td>
<td>ops/us</td>
<td align="right">1000</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">6.263005</td>
<td align="right">0.175048</td>
<td>ops/us</td>
<td align="right">1024</td>
</tr>
</tbody></table>
</div>

1000 and 1024 are somehow very different, yet 250 and 256 are almost equivalent. The placement of the second array, which, being allocated on the same thread, will be next to the first array in the TLAB (thread-local allocation buffer) happens to be very unlucky on Intel hardware. Let's allocate an array in between the two we want to loop over, to vary the offsets between the two arrays:

```java
  @Param({"0", "6", "12", "18", "24"})
  int offset;

  double s;
  double[] a;
  double[] b;
  double[] padding;

  @Setup(Level.Trial)
  public void init() {
    s = ThreadLocalRandom.current().nextDouble();
    a = createDoubleArray(size);
    padding = new double[offset];
    b = createDoubleArray(size);
  }
```

<div class="table-holder"><table class="table table-bordered table-hover table-condensed">
<thead><tr><th>Benchmark</th>
<th>Mode</th>
<th>Threads</th>
<th>Samples</th>
<th>Score</th>
<th>Score Error (99.9%)</th>
<th>Unit</th>
<th>Param: offset</th>
<th>Param: size</th>
</tr></thead>
<tbody><tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">2.224875</td>
<td align="right">0.247778</td>
<td>ops/us</td>
<td align="right">0</td>
<td align="right">1000</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">6.159791</td>
<td align="right">0.441525</td>
<td>ops/us</td>
<td align="right">0</td>
<td align="right">1024</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">2.350425</td>
<td align="right">0.136992</td>
<td>ops/us</td>
<td align="right">6</td>
<td align="right">1000</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">6.047009</td>
<td align="right">0.360723</td>
<td>ops/us</td>
<td align="right">6</td>
<td align="right">1024</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">3.332370</td>
<td align="right">0.253739</td>
<td>ops/us</td>
<td align="right">12</td>
<td align="right">1000</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">6.506141</td>
<td align="right">0.155733</td>
<td>ops/us</td>
<td align="right">12</td>
<td align="right">1024</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">6.621031</td>
<td align="right">0.345151</td>
<td>ops/us</td>
<td align="right">18</td>
<td align="right">1000</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">6.827635</td>
<td align="right">0.970527</td>
<td>ops/us</td>
<td align="right">18</td>
<td align="right">1024</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">7.456584</td>
<td align="right">0.214229</td>
<td>ops/us</td>
<td align="right">24</td>
<td align="right">1000</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">7.451441</td>
<td align="right">0.104871</td>
<td>ops/us</td>
<td align="right">24</td>
<td align="right">1024</td>
</tr>
</tbody></table>
</div>

The pattern is curious (pay attention to the offset parameter) - the ratio of the throughputs for each size ranging from 3x throughput degradation through to parity:

<img src="https://richardstartin.github.io/assets/2018/01/Plot-54.png" alt="" width="1096" height="615" class="size-full wp-image-10237" />

The loop in question is vectorised, which can be disabled by setting `-XX:-UseSuperWord`. Doing so is revealing, because the trend is still present but it is dampened to the extent it could be waved away as noise:

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th>Benchmark</th>
<th>Mode</th>
<th>Threads</th>
<th>Samples</th>
<th>Score</th>
<th>Score Error (99.9%)</th>
<th>Unit</th>
<th>Param: offset</th>
<th>Param: size</th>
</tr></thead>
<tbody><tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.416452</td>
<td align="right">0.079905</td>
<td>ops/us</td>
<td align="right">0</td>
<td align="right">1000</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.806841</td>
<td align="right">0.200231</td>
<td>ops/us</td>
<td align="right">0</td>
<td align="right">1024</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.408526</td>
<td align="right">0.085147</td>
<td>ops/us</td>
<td align="right">6</td>
<td align="right">1000</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.921026</td>
<td align="right">0.049655</td>
<td>ops/us</td>
<td align="right">6</td>
<td align="right">1024</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.459186</td>
<td align="right">0.076427</td>
<td>ops/us</td>
<td align="right">12</td>
<td align="right">1000</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.809220</td>
<td align="right">0.199885</td>
<td>ops/us</td>
<td align="right">12</td>
<td align="right">1024</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.824435</td>
<td align="right">0.169680</td>
<td>ops/us</td>
<td align="right">18</td>
<td align="right">1000</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.842230</td>
<td align="right">0.204414</td>
<td>ops/us</td>
<td align="right">18</td>
<td align="right">1024</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.934717</td>
<td align="right">0.229822</td>
<td>ops/us</td>
<td align="right">24</td>
<td align="right">1000</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.964316</td>
<td align="right">0.039893</td>
<td>ops/us</td>
<td align="right">24</td>
<td align="right">1024</td>
</tr>
</tbody></table>
</div>

<img src="https://richardstartin.github.io/assets/2018/01/Plot-56.png" alt="" width="1096" height="615" class="alignnone size-full wp-image-10240" />

The point is, you may not have cared about alignment much before because it's unlikely you would have noticed unless you were <em>really</em> looking for it. Decent autovectorisation seems to raise the stakes enormously.

<h3>Analysis with Perfasm</h3>

It's impossible to know for sure what the cause of this behaviour is without profiling. Since I observed this effect on my Windows development laptop, I use xperf via `WinPerfAsmProfiler`, which is part of JMH.

I did some instruction profiling. The same code is going to get generated in each case, with a preloop, main loop and post loop, but by looking at the sampled instruction frequency we can see what's taking the most time in the vectorised main loop. From now on, superword parallelism is never disabled. The full output of this run can be seen at <a href="https://gist.github.com/richardstartin/9b019f61aee901b20d7fbae9ae76c25d" rel="noopener" target="_blank">github</a>. Here is the main loop for size=1024, offset=0, which is unrolled, spending most time loading and storing data (`vmovdqu`) but spending a decent amount of time in the multiplication:

<pre>
  0.18%    0x0000020dddc5af90: vmovdqu ymm0,ymmword ptr [r10+r8*8+10h]
  9.27%    0x0000020dddc5af97: vmulpd  ymm0,ymm0,ymm2
  0.22%    0x0000020dddc5af9b: vaddpd  ymm0,ymm0,ymmword ptr [r11+r8*8+10h]
  7.48%    0x0000020dddc5afa2: vmovdqu ymmword ptr [r11+r8*8+10h],ymm0
 10.16%    0x0000020dddc5afa9: vmovdqu ymm0,ymmword ptr [r10+r8*8+30h]
  0.09%    0x0000020dddc5afb0: vmulpd  ymm0,ymm0,ymm2
  3.62%    0x0000020dddc5afb4: vaddpd  ymm0,ymm0,ymmword ptr [r11+r8*8+30h]
 10.60%    0x0000020dddc5afbb: vmovdqu ymmword ptr [r11+r8*8+30h],ymm0
  0.26%    0x0000020dddc5afc2: vmovdqu ymm0,ymmword ptr [r10+r8*8+50h]
  3.76%    0x0000020dddc5afc9: vmulpd  ymm0,ymm0,ymm2
  0.20%    0x0000020dddc5afcd: vaddpd  ymm0,ymm0,ymmword ptr [r11+r8*8+50h]
 13.23%    0x0000020dddc5afd4: vmovdqu ymmword ptr [r11+r8*8+50h],ymm0
  9.46%    0x0000020dddc5afdb: vmovdqu ymm0,ymmword ptr [r10+r8*8+70h]
  0.11%    0x0000020dddc5afe2: vmulpd  ymm0,ymm0,ymm2
  4.63%    0x0000020dddc5afe6: vaddpd  ymm0,ymm0,ymmword ptr [r11+r8*8+70h]
  9.78%    0x0000020dddc5afed: vmovdqu ymmword ptr [r11+r8*8+70h],ymm0
</pre>

In the worst performer (size=1000, offset=0) a lot more time is spent on the stores, a much smaller fraction of observed instructions are involved with multiplication or addition. This indicates either a measurement bias (perhaps there's some mechanism that makes a store/load easier to observe) or an increase in load/store cost.

<pre>
  0.24%    0x000002d1a946f510: vmovdqu ymm0,ymmword ptr [r10+r8*8+10h]
  3.61%    0x000002d1a946f517: vmulpd  ymm0,ymm0,ymm2
  4.63%    0x000002d1a946f51b: vaddpd  ymm0,ymm0,ymmword ptr [r11+r8*8+10h]
  9.73%    0x000002d1a946f522: vmovdqu ymmword ptr [r11+r8*8+10h],ymm0
  4.34%    0x000002d1a946f529: vmovdqu ymm0,ymmword ptr [r10+r8*8+30h]
  2.13%    0x000002d1a946f530: vmulpd  ymm0,ymm0,ymm2
  7.77%    0x000002d1a946f534: vaddpd  ymm0,ymm0,ymmword ptr [r11+r8*8+30h]
 13.46%    0x000002d1a946f53b: vmovdqu ymmword ptr [r11+r8*8+30h],ymm0
  3.37%    0x000002d1a946f542: vmovdqu ymm0,ymmword ptr [r10+r8*8+50h]
  0.47%    0x000002d1a946f549: vmulpd  ymm0,ymm0,ymm2
  1.47%    0x000002d1a946f54d: vaddpd  ymm0,ymm0,ymmword ptr [r11+r8*8+50h]
 13.00%    0x000002d1a946f554: vmovdqu ymmword ptr [r11+r8*8+50h],ymm0
  4.24%    0x000002d1a946f55b: vmovdqu ymm0,ymmword ptr [r10+r8*8+70h]
  2.40%    0x000002d1a946f562: vmulpd  ymm0,ymm0,ymm2
  8.92%    0x000002d1a946f566: vaddpd  ymm0,ymm0,ymmword ptr [r11+r8*8+70h]
 14.10%    0x000002d1a946f56d: vmovdqu ymmword ptr [r11+r8*8+70h],ymm0
</pre>

This trend can be seen to generally improve as 1024 is approached from below, and do bear in mind that this is a noisy measure. Interpret the numbers below as probabilities: were you to stop the execution of daxpy at random, at offset zero, you would have a 94% chance of finding yourself within the main vectorised loop. You would have a 50% chance of observing a store, and only 31% chance of observing a multiply or add. As we get further from 1024, the stores dominate the main loop, and the main loop comes to dominate the method. Again, this is approximate. When the arrays aren't well aligned, we spend less time loading, less time multiplying and adding, and much more time storing.

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th>classification</th>
<th>offset = 0</th>
<th>offset = 6</th>
<th>offset = 12</th>
<th>offset = 18</th>
<th>offset = 24</th>
</tr></thead>
<tbody><tr>
<td>add</td>
<td align="right">22.79</td>
<td align="right">21.46</td>
<td align="right">15.41</td>
<td align="right">7.77</td>
<td align="right">8.03</td>
</tr>
<tr>
<td>load</td>
<td align="right">12.19</td>
<td align="right">11.95</td>
<td align="right">15.55</td>
<td align="right">21.9</td>
<td align="right">21.19</td>
</tr>
<tr>
<td>multiply</td>
<td align="right">8.61</td>
<td align="right">7.7</td>
<td align="right">9.54</td>
<td align="right">13.15</td>
<td align="right">8.33</td>
</tr>
<tr>
<td>store</td>
<td align="right">50.29</td>
<td align="right">51.3</td>
<td align="right">49.16</td>
<td align="right">42.34</td>
<td align="right">44.56</td>
</tr>
<tr>
<td>main loop</td>
<td align="right">93.88</td>
<td align="right">92.41</td>
<td align="right">89.66</td>
<td align="right">85.16</td>
<td align="right">82.11</td>
</tr>
</tbody></table>
</div>

The effect observed here is also a contributing factor to fluctuations in throughput observed in <a href="https://bugs.openjdk.java.net/browse/JDK-8150730" rel="noopener" target="_blank">JDK-8150730</a>.

<h3>Garbage Collection</h3>

Is it necessary to make sure all arrays are of a size equal to a power of two and aligned with pages? In this microbenchmark, it's easy to arrange that, for typical developers this probably isn't feasible (which isn't to say there aren't people out there who do this). Fortunately, this isn't necessary for most use cases. True to the title, this post has something to do with garbage collection. The arrays were allocated in order, and no garbage would be produced during the benchmarks, so the second array will be split across pages. Let's put some code into the initialisation of the benchmark bound to trigger garbage collection:

```java
  String acc = "";

  @Setup(Level.Trial)
  public void init() {
    s = ThreadLocalRandom.current().nextDouble();
    a = createDoubleArray(size);
    b = createDoubleArray(size);
    // don't do this in production
    for (int i = 0; i < 10000; ++i) {
      acc += UUID.randomUUID().toString();
    }
  }
```

A miracle occurs: the code speeds up!

<div class="language-java">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th>Benchmark</th>
<th>Mode</th>
<th>Threads</th>
<th>Samples</th>
<th>Score</th>
<th>Score Error (99.9%)</th>
<th>Unit</th>
<th>Param: size</th>
</tr></thead>
<tbody><tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">6.854161</td>
<td align="right">0.261247</td>
<td>ops/us</td>
<td align="right">1000</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">6.328602</td>
<td align="right">0.163391</td>
<td>ops/us</td>
<td align="right">1024</td>
</tr>
</tbody></table>
</div>

Why? G1 has rearranged the heap and that second array is no longer right next to the first array, and the bad luck of the initial placement has been undone. This makes the cost of garbage collection difficult to quantify, because if it takes resources with one hand it gives them back with another.

The benchmark code is available at <a href="https://github.com/richardstartin/simdbenchmarks/blob/master/src/main/java/com/openkappa/simd/saxpy/DAXPYAlignment.java" rel="noopener" target="_blank">github</a>.