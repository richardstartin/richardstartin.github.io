---
ID: 10147
post_title: Autovectorised FMA in JDK10
author: Richard Startin
post_excerpt: ""
layout: post
permalink: >
  http://richardstartin.uk/autovectorised-fma-in-jdk10/
published: true
post_date: 2017-12-29 22:37:06
---
<em>Fused-multiply-add</em> (FMA) allows floating point expressions of the form `a * x + b` to be evaluated in a single instruction, which is useful for numerical linear algebra. Despite the obvious appeal of FMA, JVM implementors are rather constrained when it comes to floating point arithmetic because Java programs are expected to be <strong>reproducible</strong> across versions and target architectures. FMA does not produce precisely the same result as the equivalent multiplication and addition instructions (this is caused by the compounding effect of rounding) so its use is a change in semantics rather than an optimisation; the user must opt in. To the best of my knowledge, support for FMA was first proposed in <a href="https://jcp.org/en/jsr/detail?id=84" rel="noopener" target="_blank">2000</a>, along with reorderable floating point operations, which would have been activated by a `fastfp` keyword, but this proposal was withdrawn. In Java 9, the intrinsic `Math.fma` was introduced to provide access to FMA for the first time.

<h3>DAXPY Benchmark</h3>

A good use case to evaluate `Math.fma` is <em>DAXPY</em> from the Basic Linear Algebra Subroutine library. The <a href="https://github.com/richardstartin/simdbenchmarks/blob/master/src/main/java/com/openkappa/simd/saxpy/DAXPY.java" rel="noopener" target="_blank">code below</a> will compile with JDK9+

```java@OutputTimeUnit(TimeUnit.MILLISECONDS)
@State(Scope.Thread)
public class DAXPY {
  
  double s;

  @Setup(Level.Invocation)
  public void init() {
    s = ThreadLocalRandom.current().nextDouble();
  }

  @Benchmark
  public void daxpyFMA(DoubleData state, Blackhole bh) {
    double[] a = state.data1;
    double[] b = state.data2;
    for (int i = 0; i < a.length; ++i) {
      a[i] = Math.fma(s, b[i], a[i]);
    }
    bh.consume(a);
  }

  @Benchmark
  public void daxpy(DoubleData state, Blackhole bh) {
    double[] a = state.data1;
    double[] b = state.data2;
    for (int i = 0; i < a.length; ++i) {
      a[i] += s * b[i];
    }
    bh.consume(a);
  }
}
```

Running this benchmark with Java 9, you may wonder why you bothered because the code is actually slower.

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
<td align="right">25.011242</td>
<td align="right">2.259007</td>
<td>ops/ms</td>
<td align="right">100000</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.706180</td>
<td align="right">0.046146</td>
<td>ops/ms</td>
<td align="right">1000000</td>
</tr>
<tr>
<td>daxpyFMA</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">15.334652</td>
<td align="right">0.271946</td>
<td>ops/ms</td>
<td align="right">100000</td>
</tr>
<tr>
<td>daxpyFMA</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.623838</td>
<td align="right">0.018041</td>
<td>ops/ms</td>
<td align="right">1000000</td>
</tr>
</tbody></table>
</div>

This is because using `Math.fma` disables autovectorisation. Taking a look at `PrintAssembly` you can see that the naive `daxpy` routine exploits AVX2, whereas `daxpyFMA` reverts to scalar usage of SSE2.


<pre>
// daxpy routine, code taken from main vectorised loop
vmovdqu ymm1,ymmword ptr [r10+rdx*8+10h]
vmulpd  ymm1,ymm1,ymm2
vaddpd  ymm1,ymm1,ymmword ptr [r8+rdx*8+10h]
vmovdqu ymmword ptr [r8+rdx*8+10h],ymm1

// daxpyFMA routine
vmovsd  xmm2,qword ptr [rcx+r13*8+10h]
vfmadd231sd xmm2,xmm0,xmm1
vmovsd  qword ptr [rcx+r13*8+10h],xmm2
</pre>

Not to worry, this seems to have been <a href="https://bugs.openjdk.java.net/browse/JDK-8181616" rel="noopener" target="_blank">fixed in JDK 10</a>. Since Java 10's release is around the corner, there are <a href="http://jdk.java.net/10/" rel="noopener" target="_blank">early access builds available</a> for all platforms. Rerunning this benchmark, FMA no longer incurs costs, and it doesn't bring the performance boost some people might expect. The benefit is that there is less floating point error because the total number of roundings is halved.

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
<td align="right">2582.363228</td>
<td align="right">116.637400</td>
<td>ops/ms</td>
<td align="right">1000</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">405.904377</td>
<td align="right">32.364782</td>
<td>ops/ms</td>
<td align="right">10000</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">25.210111</td>
<td align="right">1.671794</td>
<td>ops/ms</td>
<td align="right">100000</td>
</tr>
<tr>
<td>daxpy</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.608660</td>
<td align="right">0.112512</td>
<td>ops/ms</td>
<td align="right">1000000</td>
</tr>
<tr>
<td>daxpyFMA</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">2650.264580</td>
<td align="right">211.342407</td>
<td>ops/ms</td>
<td align="right">1000</td>
</tr>
<tr>
<td>daxpyFMA</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">389.274693</td>
<td align="right">43.567450</td>
<td>ops/ms</td>
<td align="right">10000</td>
</tr>
<tr>
<td>daxpyFMA</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">24.941172</td>
<td align="right">2.393358</td>
<td>ops/ms</td>
<td align="right">100000</td>
</tr>
<tr>
<td>daxpyFMA</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.671310</td>
<td align="right">0.158470</td>
<td>ops/ms</td>
<td align="right">1000000</td>
</tr>
</tbody></table>
</div>

<pre>
// vectorised daxpyFMA routine, code taken from main loop (you can still see the old code in pre/post loops)
vmovdqu ymm0,ymmword ptr [r9+r13*8+10h]
vfmadd231pd ymm0,ymm1,ymmword ptr [rbx+r13*8+10h]
vmovdqu ymmword ptr [r9+r13*8+10h],ymm0
</pre>



<blockquote>Paul Sandoz discussed `Math.fma` at Oracle Code One 2018.</blockquote>
<iframe width="560" height="315" src="https://www.youtube.com/embed/h7AtDzqbaoQ?start=2051" frameborder="0" allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>