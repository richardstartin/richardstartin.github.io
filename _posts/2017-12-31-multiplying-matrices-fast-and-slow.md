---
ID: 10156
title: Multiplying Matrices, Fast and Slow
author: Richard Startin
post_excerpt: ""
layout: post

published: true
date: 2017-12-31 08:14:06
---
I recently read a <a href="https://astojanov.github.io/blog/2017/12/20/scala-simd.html" rel="noopener" target="_blank">very interesting blog post</a> about exposing Intel SIMD intrinsics via a fork of the Scala compiler (<a href="https://github.com/TiarkRompf/scala-virtualized" rel="noopener" target="_blank">scala-virtualized</a>), which reports multiplicative improvements in throughput over HotSpot JIT compiled code. The <a href="https://astojanov.github.io/publications/preprint/004_cgo18-simd.pdf" rel="noopener" target="_blank">academic paper</a> (<em>SIMD Intrinsics on Managed Language Runtimes</em>), which has been accepted at <a href="http://cgo.org/cgo2018/" rel="noopener" target="_blank">CGO 2018</a>, proposes a powerful alternative to the traditional JVM approach of pairing dumb programmers with a (hopefully) smart JIT compiler. <em>Lightweight Modular Staging</em> (<a href="https://infoscience.epfl.ch/record/150347/files/gpce63-rompf.pdf" rel="noopener" target="_blank">LMS</a>) allows the generation of an executable binary from a high level representation: handcrafted representations of vectorised algorithms, written in a dialect of Scala, can be compiled natively and later invoked with a single JNI call. This approach bypasses C2 without incurring excessive JNI costs. The freely available <a href="https://github.com/astojanov/NGen" rel="noopener" target="_blank">benchmarks</a> can be easily run to reproduce the results in the paper, which is an achievement in itself, but some of the Java implementations used as baselines look less efficient than they could be. This post is about improving the efficiency of the Java matrix multiplication the LMS generated code is benchmarked against. Despite finding edge cases where autovectorisation fails, I find it is possible to get performance comparable to LMS with plain Java (and a JDK upgrade).

Two <a href="https://github.com/astojanov/NGen/blob/master/src/ch/ethz/acl/ngen/mmm/JMMM.java" rel="noopener" target="_blank">implementations</a> of Java matrix multiplication are provided in the NGen benchmarks: `JMMM.baseline` - a naive but cache unfriendly matrix multiplication - and `JMMM.blocked` which is supplied as an improvement. `JMMM.blocked` is something of a local maximum because it does manual loop unrolling: this actually removes the trigger for autovectorisation analysis. I provide a simple and cache-efficient Java implementation (with the same asymptotic complexity, the improvement is just technical) and benchmark these implementations using JDK8 and the soon to be released JDK10 separately.

```java
   public void fast(float[] a, float[] b, float[] c, int n) {
   int in = 0;
   for (int i = 0; i < n; ++i) {
       int kn = 0;
       for (int k = 0; k < n; ++k) {
           float aik = a[in + k];
           for (int j = 0; j < n; ++j) {
               c[in + j] += aik * b[kn + j];
           }
           kn += n;
       }
       in += n;
    }
}
```

With JDK 1.8.0_131, the "fast" implementation is only 2x faster than the blocked algorithm; this is nowhere near fast enough to match LMS. In fact, LMS does a lot better than 5x blocked (6x-8x) on my Skylake laptop at 2.6GHz, and performs between 2x and 4x better than the improved implementation. <em>Flops / Cycle</em> is calculated as `size ^ 3 * 2 / CPU frequency Hz`.

<pre>
====================================================
Benchmarking MMM.jMMM.fast (JVM implementation)
----------------------------------------------------
    Size (N) | Flops / Cycle
----------------------------------------------------
           8 | 0.4994459272
          32 | 1.0666533335
          64 | 0.9429120397
         128 | 0.9692385519
         192 | 0.9796619688
         256 | 1.0141446247
         320 | 0.9894415771
         384 | 1.0046245750
         448 | 1.0221353392
         512 | 0.9943527764
         576 | 0.9952093603
         640 | 0.9854689714
         704 | 0.9947153752
         768 | 1.0197765248
         832 | 1.0479691069
         896 | 1.0060121097
         960 | 0.9937347412
        1024 | 0.9056494897
====================================================

====================================================
Benchmarking MMM.nMMM.blocked (LMS generated)
----------------------------------------------------
    Size (N) | Flops / Cycle
----------------------------------------------------
           8 | 0.2500390686
          32 | 3.9999921875
          64 | 4.1626523901
         128 | 4.4618695374
         192 | 3.9598982956
         256 | 4.3737341517
         320 | 4.2412225389
         384 | 3.9640163416
         448 | 4.0957167537
         512 | 3.3801071278
         576 | 4.1869326167
         640 | 3.8225244883
         704 | 3.8648224140
         768 | 3.5240611589
         832 | 3.7941562681
         896 | 3.1735179981
         960 | 2.5856903789
        1024 | 1.7817152313
====================================================

====================================================
Benchmarking MMM.jMMM.blocked (JVM implementation)
----------------------------------------------------
    Size (N) | Flops / Cycle
----------------------------------------------------
           8 | 0.3333854248
          32 | 0.6336670915
          64 | 0.5733484649
         128 | 0.5987433798
         192 | 0.5819900921
         256 | 0.5473562109
         320 | 0.5623263520
         384 | 0.5583823292
         448 | 0.5657882256
         512 | 0.5430879470
         576 | 0.5269635678
         640 | 0.5595204791
         704 | 0.5297557807
         768 | 0.5493631388
         832 | 0.5471832673
         896 | 0.4769554752
         960 | 0.4985080443
        1024 | 0.4014589400
====================================================
</pre>

JDK10 is about to be released so it's worth looking at the effect of recent improvements to C2, including better use of AVX2 and support for vectorised FMA. Since LMS depends on scala-virtualized, which currently only supports Scala 2.11, the LMS implementation cannot be run with a more recent JDK so its performance running in JDK10 could only be extrapolated. Since its <em>raison d'être</em> is to <em>bypass</em> C2, it could be reasonably assumed it is insulated from JVM performance improvements (or regressions). Measurements of floating point operations per cycle provide a sensible comparison, in any case.

Moving away from ScalaMeter, I created a <a href="https://github.com/richardstartin/simdbenchmarks/blob/master/src/main/java/com/openkappa/simd/mmm/MMM.java" rel="noopener" target="_blank">JMH benchmark</a> to see how matrix multiplication behaves in JDK10.

```java
@OutputTimeUnit(TimeUnit.SECONDS)
@State(Scope.Benchmark)
public class MMM {

  @Param({"8", "32", "64", "128", "192", "256", "320", "384", "448", "512" , "576", "640", "704", "768", "832", "896", "960", "1024"})
  int size;

  private float[] a;
  private float[] b;
  private float[] c;

  @Setup(Level.Trial)
  public void init() {
    a = DataUtil.createFloatArray(size * size);
    b = DataUtil.createFloatArray(size * size);
    c = new float[size * size];
  }

  @Benchmark
  public void fast(Blackhole bh) {
    fast(a, b, c, size);
    bh.consume(c);
  }

  @Benchmark
  public void baseline(Blackhole bh) {
    baseline(a, b, c, size);
    bh.consume(c);
  }


  @Benchmark
  public void blocked(Blackhole bh) {
    blocked(a, b, c, size);
    bh.consume(c);
  }

  //
  // Baseline implementation of a Matrix-Matrix-Multiplication
  //
  public void baseline (float[] a, float[] b, float[] c, int n){
    for (int i = 0; i < n; i += 1) {
      for (int j = 0; j < n; j += 1) {
        float sum = 0.0f;
        for (int k = 0; k < n; k += 1) {
          sum += a[i * n + k] * b[k * n + j];
        }
        c[i * n + j] = sum;
      }
    }
  }

  //
  // Blocked version of MMM, reference implementation available at:
  // http://csapp.cs.cmu.edu/2e/waside/waside-blocking.pdf
  //
  public void blocked(float[] a, float[] b, float[] c, int n) {
    int BLOCK_SIZE = 8;
    for (int kk = 0; kk < n; kk += BLOCK_SIZE) {
      for (int jj = 0; jj < n; jj += BLOCK_SIZE) {
        for (int i = 0; i < n; i++) {
          for (int j = jj; j < jj + BLOCK_SIZE; ++j) {
            float sum = c[i * n + j];
            for (int k = kk; k < kk + BLOCK_SIZE; ++k) {
              sum += a[i * n + k] * b[k * n + j];
            }
            c[i * n + j] = sum;
          }
        }
      }
    }
  }

  public void fast(float[] a, float[] b, float[] c, int n) {
    int in = 0;
    for (int i = 0; i < n; ++i) {
      int kn = 0;
      for (int k = 0; k < n; ++k) {
        float aik = a[in + k];
        for (int j = 0; j < n; ++j) {
          c[in + j] = Math.fma(aik,  b[kn + j], c[in + j]);
        }
        kn += n;
      }
      in += n;
    }
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
<th>Ratio to blocked</th>
<th>Flops/Cycle</th>
</tr></thead>
<tbody><tr>
<td>baseline</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1228544.82</td>
<td align="right">38793.17392</td>
<td>ops/s</td>
<td align="right">8</td>
<td align="right">1.061598336</td>
<td align="right">0.483857652</td>
</tr>
<tr>
<td>baseline</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">22973.03402</td>
<td align="right">1012.043446</td>
<td>ops/s</td>
<td align="right">32</td>
<td align="right">1.302266947</td>
<td align="right">0.57906183</td>
</tr>
<tr>
<td>baseline</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">2943.088879</td>
<td align="right">221.57475</td>
<td>ops/s</td>
<td align="right">64</td>
<td align="right">1.301414733</td>
<td align="right">0.593471609</td>
</tr>
<tr>
<td>baseline</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">358.010135</td>
<td align="right">9.342801</td>
<td>ops/s</td>
<td align="right">128</td>
<td align="right">1.292889618</td>
<td align="right">0.577539747</td>
</tr>
<tr>
<td>baseline</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">105.758366</td>
<td align="right">4.275503</td>
<td>ops/s</td>
<td align="right">192</td>
<td align="right">1.246415143</td>
<td align="right">0.575804515</td>
</tr>
<tr>
<td>baseline</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">41.465557</td>
<td align="right">1.112753</td>
<td>ops/s</td>
<td align="right">256</td>
<td align="right">1.430003946</td>
<td align="right">0.535135851</td>
</tr>
<tr>
<td>baseline</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">20.479081</td>
<td align="right">0.462547</td>
<td>ops/s</td>
<td align="right">320</td>
<td align="right">1.154267894</td>
<td align="right">0.516198866</td>
</tr>
<tr>
<td>baseline</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">11.686685</td>
<td align="right">0.263476</td>
<td>ops/s</td>
<td align="right">384</td>
<td align="right">1.186535349</td>
<td align="right">0.509027985</td>
</tr>
<tr>
<td>baseline</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">7.344184</td>
<td align="right">0.269656</td>
<td>ops/s</td>
<td align="right">448</td>
<td align="right">1.166421127</td>
<td align="right">0.507965526</td>
</tr>
<tr>
<td>baseline</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">3.545153</td>
<td align="right">0.108086</td>
<td>ops/s</td>
<td align="right">512</td>
<td align="right">0.81796657</td>
<td align="right">0.366017216</td>
</tr>
<tr>
<td>baseline</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">3.789384</td>
<td align="right">0.130934</td>
<td>ops/s</td>
<td align="right">576</td>
<td align="right">1.327168294</td>
<td align="right">0.557048123</td>
</tr>
<tr>
<td>baseline</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.981957</td>
<td align="right">0.040136</td>
<td>ops/s</td>
<td align="right">640</td>
<td align="right">1.020965271</td>
<td align="right">0.399660104</td>
</tr>
<tr>
<td>baseline</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.76672</td>
<td align="right">0.036386</td>
<td>ops/s</td>
<td align="right">704</td>
<td align="right">1.168272442</td>
<td align="right">0.474179037</td>
</tr>
<tr>
<td>baseline</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.01026</td>
<td align="right">0.049853</td>
<td>ops/s</td>
<td align="right">768</td>
<td align="right">0.845514112</td>
<td align="right">0.352024966</td>
</tr>
<tr>
<td>baseline</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.115814</td>
<td align="right">0.03803</td>
<td>ops/s</td>
<td align="right">832</td>
<td align="right">1.148752171</td>
<td align="right">0.494331667</td>
</tr>
<tr>
<td>baseline</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.703561</td>
<td align="right">0.110626</td>
<td>ops/s</td>
<td align="right">896</td>
<td align="right">0.938435436</td>
<td align="right">0.389298235</td>
</tr>
<tr>
<td>baseline</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.629896</td>
<td align="right">0.052448</td>
<td>ops/s</td>
<td align="right">960</td>
<td align="right">1.081741651</td>
<td align="right">0.428685898</td>
</tr>
<tr>
<td>baseline</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.407772</td>
<td align="right">0.019079</td>
<td>ops/s</td>
<td align="right">1024</td>
<td align="right">1.025356561</td>
<td align="right">0.336801424</td>
</tr>
<tr>
<td>blocked</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1157259.558</td>
<td align="right">49097.48711</td>
<td>ops/s</td>
<td align="right">8</td>
<td align="right">1</td>
<td align="right">0.455782226</td>
</tr>
<tr>
<td>blocked</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">17640.8025</td>
<td align="right">1226.401298</td>
<td>ops/s</td>
<td align="right">32</td>
<td align="right">1</td>
<td align="right">0.444656782</td>
</tr>
<tr>
<td>blocked</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">2261.453481</td>
<td align="right">98.937035</td>
<td>ops/s</td>
<td align="right">64</td>
<td align="right">1</td>
<td align="right">0.456020355</td>
</tr>
<tr>
<td>blocked</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">276.906961</td>
<td align="right">22.851857</td>
<td>ops/s</td>
<td align="right">128</td>
<td align="right">1</td>
<td align="right">0.446704605</td>
</tr>
<tr>
<td>blocked</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">84.850033</td>
<td align="right">4.441454</td>
<td>ops/s</td>
<td align="right">192</td>
<td align="right">1</td>
<td align="right">0.461968485</td>
</tr>
<tr>
<td>blocked</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">28.996813</td>
<td align="right">7.585551</td>
<td>ops/s</td>
<td align="right">256</td>
<td align="right">1</td>
<td align="right">0.374219842</td>
</tr>
<tr>
<td>blocked</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">17.742052</td>
<td align="right">0.627629</td>
<td>ops/s</td>
<td align="right">320</td>
<td align="right">1</td>
<td align="right">0.447208892</td>
</tr>
<tr>
<td>blocked</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">9.84942</td>
<td align="right">0.367603</td>
<td>ops/s</td>
<td align="right">384</td>
<td align="right">1</td>
<td align="right">0.429003641</td>
</tr>
<tr>
<td>blocked</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">6.29634</td>
<td align="right">0.402846</td>
<td>ops/s</td>
<td align="right">448</td>
<td align="right">1</td>
<td align="right">0.435490676</td>
</tr>
<tr>
<td>blocked</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">4.334105</td>
<td align="right">0.384849</td>
<td>ops/s</td>
<td align="right">512</td>
<td align="right">1</td>
<td align="right">0.447472097</td>
</tr>
<tr>
<td>blocked</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">2.85524</td>
<td align="right">0.199102</td>
<td>ops/s</td>
<td align="right">576</td>
<td align="right">1</td>
<td align="right">0.419726816</td>
</tr>
<tr>
<td>blocked</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.941258</td>
<td align="right">0.10915</td>
<td>ops/s</td>
<td align="right">640</td>
<td align="right">1</td>
<td align="right">0.391453182</td>
</tr>
<tr>
<td>blocked</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.51225</td>
<td align="right">0.076621</td>
<td>ops/s</td>
<td align="right">704</td>
<td align="right">1</td>
<td align="right">0.40588053</td>
</tr>
<tr>
<td>blocked</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.194847</td>
<td align="right">0.063147</td>
<td>ops/s</td>
<td align="right">768</td>
<td align="right">1</td>
<td align="right">0.416344283</td>
</tr>
<tr>
<td>blocked</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.971327</td>
<td align="right">0.040421</td>
<td>ops/s</td>
<td align="right">832</td>
<td align="right">1</td>
<td align="right">0.430320551</td>
</tr>
<tr>
<td>blocked</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.749717</td>
<td align="right">0.042997</td>
<td>ops/s</td>
<td align="right">896</td>
<td align="right">1</td>
<td align="right">0.414837526</td>
</tr>
<tr>
<td>blocked</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.582298</td>
<td align="right">0.016725</td>
<td>ops/s</td>
<td align="right">960</td>
<td align="right">1</td>
<td align="right">0.39629231</td>
</tr>
<tr>
<td>blocked</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.397688</td>
<td align="right">0.043639</td>
<td>ops/s</td>
<td align="right">1024</td>
<td align="right">1</td>
<td align="right">0.328472491</td>
</tr>
<tr>
<td>fast</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1869676.345</td>
<td align="right">76416.50848</td>
<td>ops/s</td>
<td align="right">8</td>
<td align="right">1.615606743</td>
<td align="right">0.736364837</td>
</tr>
<tr>
<td>fast</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">48485.47216</td>
<td align="right">1301.926828</td>
<td>ops/s</td>
<td align="right">32</td>
<td align="right">2.748484496</td>
<td align="right">1.222132271</td>
</tr>
<tr>
<td>fast</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">6431.341657</td>
<td align="right">153.905413</td>
<td>ops/s</td>
<td align="right">64</td>
<td align="right">2.843897392</td>
<td align="right">1.296875098</td>
</tr>
<tr>
<td>fast</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">840.601821</td>
<td align="right">45.998723</td>
<td>ops/s</td>
<td align="right">128</td>
<td align="right">3.035683242</td>
<td align="right">1.356053685</td>
</tr>
<tr>
<td>fast</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">260.386996</td>
<td align="right">13.022418</td>
<td>ops/s</td>
<td align="right">192</td>
<td align="right">3.068790745</td>
<td align="right">1.417684611</td>
</tr>
<tr>
<td>fast</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">107.895708</td>
<td align="right">6.584674</td>
<td>ops/s</td>
<td align="right">256</td>
<td align="right">3.720950575</td>
<td align="right">1.392453537</td>
</tr>
<tr>
<td>fast</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">56.245336</td>
<td align="right">2.729061</td>
<td>ops/s</td>
<td align="right">320</td>
<td align="right">3.170170846</td>
<td align="right">1.417728592</td>
</tr>
<tr>
<td>fast</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">32.917996</td>
<td align="right">2.196624</td>
<td>ops/s</td>
<td align="right">384</td>
<td align="right">3.342125323</td>
<td align="right">1.433783932</td>
</tr>
<tr>
<td>fast</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">20.960189</td>
<td align="right">2.077684</td>
<td>ops/s</td>
<td align="right">448</td>
<td align="right">3.328948087</td>
<td align="right">1.449725854</td>
</tr>
<tr>
<td>fast</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">14.005186</td>
<td align="right">0.7839</td>
<td>ops/s</td>
<td align="right">512</td>
<td align="right">3.231390564</td>
<td align="right">1.445957112</td>
</tr>
<tr>
<td>fast</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">8.827584</td>
<td align="right">0.883654</td>
<td>ops/s</td>
<td align="right">576</td>
<td align="right">3.091713481</td>
<td align="right">1.297675056</td>
</tr>
<tr>
<td>fast</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">7.455607</td>
<td align="right">0.442882</td>
<td>ops/s</td>
<td align="right">640</td>
<td align="right">3.840605937</td>
<td align="right">1.503417416</td>
</tr>
<tr>
<td>fast</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">5.322894</td>
<td align="right">0.464362</td>
<td>ops/s</td>
<td align="right">704</td>
<td align="right">3.519850554</td>
<td align="right">1.428638807</td>
</tr>
<tr>
<td>fast</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">4.308522</td>
<td align="right">0.153846</td>
<td>ops/s</td>
<td align="right">768</td>
<td align="right">3.605919419</td>
<td align="right">1.501303934</td>
</tr>
<tr>
<td>fast</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">3.375274</td>
<td align="right">0.106715</td>
<td>ops/s</td>
<td align="right">832</td>
<td align="right">3.474910097</td>
<td align="right">1.495325228</td>
</tr>
<tr>
<td>fast</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">2.320152</td>
<td align="right">0.367881</td>
<td>ops/s</td>
<td align="right">896</td>
<td align="right">3.094703735</td>
<td align="right">1.28379924</td>
</tr>
<tr>
<td>fast</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">2.057478</td>
<td align="right">0.150198</td>
<td>ops/s</td>
<td align="right">960</td>
<td align="right">3.533376381</td>
<td align="right">1.400249889</td>
</tr>
<tr>
<td>fast</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.66255</td>
<td align="right">0.181116</td>
<td>ops/s</td>
<td align="right">1024</td>
<td align="right">4.180538513</td>
<td align="right">1.3731919</td>
</tr>
</tbody></table>
</div>

Interestingly, the blocked algorithm is now the worst native JVM implementation. The code generated by C2 got a lot faster, but peaks at 1.5 flops/cycle, which still doesn't compete with LMS. Why? Taking a look at the assembly, it's clear that the autovectoriser choked on the array offsets and produced scalar SSE2 code, just like the implementations in the paper. I wasn't expecting this.


```asm
vmovss  xmm5,dword ptr [rdi+rcx*4+10h]
vfmadd231ss xmm5,xmm6,xmm2
vmovss  dword ptr [rdi+rcx*4+10h],xmm5
```

Is this the end of the story? No, with some hacks and the cost of array allocation and a copy or two, autovectorisation can be tricked into working again to generate faster code:


```java
    public void fast(float[] a, float[] b, float[] c, int n) {
        float[] bBuffer = new float[n];
        float[] cBuffer = new float[n];
        int in = 0;
        for (int i = 0; i < n; ++i) {
            int kn = 0;
            for (int k = 0; k < n; ++k) {
                float aik = a[in + k];
                System.arraycopy(b, kn, bBuffer, 0, n);
                saxpy(n, aik, bBuffer, cBuffer);
                kn += n;
            }
            System.arraycopy(cBuffer, 0, c, in, n); 
            Arrays.fill(cBuffer, 0f);
            in += n;
        }
    }

    private void saxpy(int n, float aik, float[] b, float[] c) {
        for (int i = 0; i < n; ++i) {
            c[i] += aik * b[i];
        }
    }
```

Adding this hack into the <a href="https://github.com/astojanov/NGen/pull/1" rel="noopener" target="_blank">NGen benchmark</a> (back in JDK 1.8.0_131) I get closer to the LMS generated code, and beat it beyond L3 cache residency (6MB). LMS is still faster when both matrices fit in L3 concurrently, but by percentage points rather than a multiple. The cost of the hacky array buffers gives the game up for small matrices.

<pre>
====================================================
Benchmarking MMM.jMMM.fast (JVM implementation)
----------------------------------------------------
    Size (N) | Flops / Cycle
----------------------------------------------------
           8 | 0.2500390686
          32 | 0.7710872405
          64 | 1.1302489072
         128 | 2.5113453810
         192 | 2.9525859816
         256 | 3.1180920385
         320 | 3.1081563593
         384 | 3.1458423577
         448 | 3.0493148252
         512 | 3.0551158263
         576 | 3.1430376938
         640 | 3.2169923048
         704 | 3.1026513283
         768 | 2.4190053777
         832 | 3.3358586705
         896 | 3.0755689237
         960 | 2.9996690697
        1024 | 2.2935654309
====================================================

====================================================
Benchmarking MMM.nMMM.blocked (LMS generated)
----------------------------------------------------
    Size (N) | Flops / Cycle
----------------------------------------------------
           8 | 1.0001562744
          32 | 5.3330416826
          64 | 5.8180867784
         128 | 5.1717318641
         192 | 5.1639907462
         256 | 4.3418618628
         320 | 5.2536572701
         384 | 4.0801359215
         448 | 4.1337007093
         512 | 3.2678160754
         576 | 3.7973028890
         640 | 3.3557513664
         704 | 4.0103133240
         768 | 3.4188362575
         832 | 3.2189488327
         896 | 3.2316685219
         960 | 2.9985655539
        1024 | 1.7750946796
====================================================
</pre>

With the benchmark below I calculate flops/cycle with improved JDK10 autovectorisation.

```java
  @Benchmark
  public void fastBuffered(Blackhole bh) {
    fastBuffered(a, b, c, size);
    bh.consume(c);
  }

  public void fastBuffered(float[] a, float[] b, float[] c, int n) {
    float[] bBuffer = new float[n];
    float[] cBuffer = new float[n];
    int in = 0;
    for (int i = 0; i < n; ++i) {
      int kn = 0;
      for (int k = 0; k < n; ++k) {
        float aik = a[in + k];
        System.arraycopy(b, kn, bBuffer, 0, n);
        saxpy(n, aik, bBuffer, cBuffer);
        kn += n;
      }
      System.arraycopy(cBuffer, 0, c, in, n);
      Arrays.fill(cBuffer, 0f);
      in += n;
    }
  }

  private void saxpy(int n, float aik, float[] b, float[] c) {
    for (int i = 0; i < n; ++i) {
      c[i] = Math.fma(aik, b[i], c[i]);
    }
  }
```

Just as in the modified NGen benchmark, this starts paying off once the matrices have 64 rows and columns. Finally, and it took an upgrade and a hack, I breached 4 Flops per cycle:

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
<th>Flops / Cycle</th>
</tr></thead>
<tbody><tr>
<td>fastBuffered</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1047184.034</td>
<td align="right">63532.95095</td>
<td>ops/s</td>
<td align="right">8</td>
<td align="right">0.412429404</td>
</tr>
<tr>
<td>fastBuffered</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">58373.56367</td>
<td align="right">3239.615866</td>
<td>ops/s</td>
<td align="right">32</td>
<td align="right">1.471373026</td>
</tr>
<tr>
<td>fastBuffered</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">12099.41654</td>
<td align="right">497.33988</td>
<td>ops/s</td>
<td align="right">64</td>
<td align="right">2.439838038</td>
</tr>
<tr>
<td>fastBuffered</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">2136.50264</td>
<td align="right">105.038006</td>
<td>ops/s</td>
<td align="right">128</td>
<td align="right">3.446592911</td>
</tr>
<tr>
<td>fastBuffered</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">673.470622</td>
<td align="right">102.577237</td>
<td>ops/s</td>
<td align="right">192</td>
<td align="right">3.666730488</td>
</tr>
<tr>
<td>fastBuffered</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">305.541519</td>
<td align="right">25.959163</td>
<td>ops/s</td>
<td align="right">256</td>
<td align="right">3.943181586</td>
</tr>
<tr>
<td>fastBuffered</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">158.437372</td>
<td align="right">6.708384</td>
<td>ops/s</td>
<td align="right">320</td>
<td align="right">3.993596774</td>
</tr>
<tr>
<td>fastBuffered</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">88.283718</td>
<td align="right">7.58883</td>
<td>ops/s</td>
<td align="right">384</td>
<td align="right">3.845306266</td>
</tr>
<tr>
<td>fastBuffered</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">58.574507</td>
<td align="right">4.248521</td>
<td>ops/s</td>
<td align="right">448</td>
<td align="right">4.051345968</td>
</tr>
<tr>
<td>fastBuffered</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">37.183635</td>
<td align="right">4.360319</td>
<td>ops/s</td>
<td align="right">512</td>
<td align="right">3.839002314</td>
</tr>
<tr>
<td>fastBuffered</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">29.949884</td>
<td align="right">0.63346</td>
<td>ops/s</td>
<td align="right">576</td>
<td align="right">4.40270151</td>
</tr>
<tr>
<td>fastBuffered</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">20.715833</td>
<td align="right">4.175897</td>
<td>ops/s</td>
<td align="right">640</td>
<td align="right">4.177331789</td>
</tr>
<tr>
<td>fastBuffered</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">10.824837</td>
<td align="right">0.902983</td>
<td>ops/s</td>
<td align="right">704</td>
<td align="right">2.905333492</td>
</tr>
<tr>
<td>fastBuffered</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">8.285254</td>
<td align="right">1.438701</td>
<td>ops/s</td>
<td align="right">768</td>
<td align="right">2.886995686</td>
</tr>
<tr>
<td>fastBuffered</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">6.17029</td>
<td align="right">0.746537</td>
<td>ops/s</td>
<td align="right">832</td>
<td align="right">2.733582608</td>
</tr>
<tr>
<td>fastBuffered</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">4.828872</td>
<td align="right">1.316901</td>
<td>ops/s</td>
<td align="right">896</td>
<td align="right">2.671937962</td>
</tr>
<tr>
<td>fastBuffered</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">3.6343</td>
<td align="right">1.293923</td>
<td>ops/s</td>
<td align="right">960</td>
<td align="right">2.473381573</td>
</tr>
<tr>
<td>fastBuffered</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">2.458296</td>
<td align="right">0.171224</td>
<td>ops/s</td>
<td align="right">1024</td>
<td align="right">2.030442485</td>
</tr>
</tbody></table>
</div>

The code generated for the core of the loop looks better now:

```asm
vmovdqu ymm1,ymmword ptr [r13+r11*4+10h]
vfmadd231ps ymm1,ymm3,ymmword ptr [r14+r11*4+10h]
vmovdqu ymmword ptr [r13+r11*4+10h],ymm1                                               
```

These benchmark results can be compared on a line chart.

<div class="table-holder">
<img src="https://richardstartin.github.io/assets/2017/12/Plot-52-2.png" alt="" width="700" height="500" class="alignnone size-full wp-image-10222" style="overflow-x: scroll;" />
</div>

Given this improvement, it would be exciting to see how LMS can profit from JDK9 or JDK10 - does LMS provide the impetus to resume maintenance of scala-virtualized? L3 cache, which the LMS generated code seems to depend on for throughput, is typically shared between cores: a single thread rarely enjoys exclusive access. I would like to see benchmarks for the LMS generated code in the presence of concurrency.