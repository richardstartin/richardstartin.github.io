---
ID: 4986
post_title: Sum of Squares
author: Richard Startin
post_excerpt: ""
layout: post
permalink: http://richardstartin.uk/sum-of-squares/
published: true
post_date: 2018-01-08 15:47:52
---
Streams and lambdas, especially the limited support offered for primitive types, are a fantastic addition to the Java language. They're not supposed to be fast, but how do these features compare to a good old <code language="java">for</code> loop? For a simple calculation amenable to instruction level parallelism, I compare modern and traditional implementations and observe the differences in instructions generated.

<h3>Sum of Squares</h3>
The sum of squares is the building block of a linear regression analysis so is ubiquitous in statistical computing. It is associative and therefore data-parallel. I compare four implementations: a sequential stream wrapping an array, a parallel stream wrapping an array, a generative sequential stream and a traditional <code>for</code> loop. The benchmark code is on <a href="https://github.com/richardstartin/simdbenchmarks/blob/master/src/main/java/com/openkappa/simd/ss/SumOfSquaresBlogPost.java" target="_blank">github</a>.

<code class="language-java">
  @Param({"1024", "8192"})
  int size;

  private double[] data;

  @Setup(Level.Iteration)
  public void init() {
    this.data = createDoubleArray(size);
  }

  @Benchmark
  public double SS_SequentialStream() {
    return DoubleStream.of(data)
            .map(x -> x * x)
            .reduce((x, y) -> x + y)
            .orElse(0D);
  }

  @Benchmark
  public double SS_ParallelStream() {
    return DoubleStream.of(data)
            .parallel()
            .map(x -> x * x)
            .reduce((x, y) -> x + y)
            .orElse(0);
  }

  @Benchmark
  public double SS_ForLoop() {
    double result = 0D;
    for (int i = 0; i < data.length; ++i) {
      result += data[i] * data[i];
    }
    return result;
  }

  @Benchmark
  public double SS_GenerativeSequentialStream() {
    return IntStream.iterate(0, i -> i < size, i -> i + 1)
            .mapToDouble(i -> data[i])
            .map(x -> x * x)
            .reduce((x, y) -> x + y)
            .orElse(0);
  }
</code>

I must admit I prefer the readability of the stream versions, but let's see if there is a comedown after the syntactic sugar rush.

<h3>Running a Benchmark</h3>

I compare the four implementations on an array of one million doubles. I am using <code>JDK 9.0.1, VM 9.0.1+11</code> on a fairly powerful laptop with 8 processors:

<pre>
$ cat /proc/cpuinfo
processor       : 0
vendor_id       : GenuineIntel
cpu family      : 6
model           : 94
model name      : Intel(R) Core(TM) i7-6700HQ CPU @ 2.60GHz
stepping        : 3
cpu MHz         : 2592.000
cache size      : 256 KB
physical id     : 0
siblings        : 8
core id         : 0
cpu cores       : 4
apicid          : 0
initial apicid  : 0
fpu             : yes
fpu_exception   : yes
cpuid level     : 22
wp              : yes
flags           : fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush dts acpi mmx fxsr sse sse2 ss ht tm pbe pni dtes64 monitor ds_cpl vmx est tm2 ssse3 fma cx16 xtpr pdcm sse4_1 sse4_2 x2apic movbe popcnt aes xsave osxsave avx f16c rdrand lahf_lm ida arat epb xsaveopt pln pts dtherm fsgsbase tsc_adjust bmi1 hle avx2 smep bmi2 erms invpcid rtm mpx rdseed adx smap clflushopt
clflush size    : 64
cache_alignment : 64
address sizes   : 39 bits physical, 48 bits virtual
power management:
</pre>

Before running the benchmark we might expect the <code>for</code> loop and stream to have similar performance, and the parallel version to be about eight times faster (though remember that the arrays aren't too big). The generative version is very similar to the <code>for</code> loop so a slow down might not be expected. 

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
<td>SS_ForLoop</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">258351.774491</td>
<td align="right">39797.567968</td>
<td>ops/s</td>
<td align="right">1024</td>
</tr>
<tr>
<td>SS_ForLoop</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">29463.408428</td>
<td align="right">4814.826388</td>
<td>ops/s</td>
<td align="right">8192</td>
</tr>
<tr>
<td>SS_GenerativeSequentialStream</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">219699.607567</td>
<td align="right">9095.569546</td>
<td>ops/s</td>
<td align="right">1024</td>
</tr>
<tr>
<td>SS_GenerativeSequentialStream</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">28351.900454</td>
<td align="right">828.513989</td>
<td>ops/s</td>
<td align="right">8192</td>
</tr>
<tr>
<td>SS_ParallelStream</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">22827.821827</td>
<td align="right">2826.577213</td>
<td>ops/s</td>
<td align="right">1024</td>
</tr>
<tr>
<td>SS_ParallelStream</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">23230.623610</td>
<td align="right">273.415352</td>
<td>ops/s</td>
<td align="right">8192</td>
</tr>
<tr>
<td>SS_SequentialStream</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">225431.985145</td>
<td align="right">9051.538442</td>
<td>ops/s</td>
<td align="right">1024</td>
</tr>
<tr>
<td>SS_SequentialStream</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">29123.734157</td>
<td align="right">1333.721437</td>
<td>ops/s</td>
<td align="right">8192</td>
</tr>
</tbody></table>
</div>

The <code>for</code> loop and stream are similar. The parallel version is a long way behind (yes that's right: more threads <em>less</em> power), but exhibits constant scaling (incidentally, a measurement like this is a good way to guess the minimum unit of work in a parallelised implementation). If the data is large it <em>could</em> become profitable to use it. The generative stream is surprisingly good, almost as good as the version that wraps the array, though there is a fail-safe way to slow it down: add a limit clause to the method chain (try it...). 

Profiling with perfasm, it is clear that the <code>for</code> loop body is being vectorised, but only the loads and multiplications are done in parallel - the complicated string of SSE instructions is the reduction, which must be done in order.

<pre>
<-- unrolled load -->
  0.01%    0x00000243d8969170: vmovdqu ymm1,ymmword ptr [r11+r8*8+0f0h]
  0.07%    0x00000243d896917a: vmovdqu ymm2,ymmword ptr [r11+r8*8+0d0h]
  0.75%    0x00000243d8969184: vmovdqu ymm3,ymmword ptr [r11+r8*8+0b0h]
  0.01%    0x00000243d896918e: vmovdqu ymm4,ymmword ptr [r11+r8*8+90h]
  0.02%    0x00000243d8969198: vmovdqu ymm5,ymmword ptr [r11+r8*8+70h]
  0.03%    0x00000243d896919f: vmovdqu ymm6,ymmword ptr [r11+r8*8+50h]
  0.77%    0x00000243d89691a6: vmovdqu ymm10,ymmword ptr [r11+r8*8+30h]
  0.02%    0x00000243d89691ad: vmovdqu ymm7,ymmword ptr [r11+r8*8+10h]
<-- multiplication starts -->
  0.01%    0x00000243d89691b4: vmulpd  ymm1,ymm1,ymm1
  0.02%    0x00000243d89691b8: vmovdqu ymmword ptr [rsp+28h],ymm1
  0.76%    0x00000243d89691be: vmulpd  ymm15,ymm7,ymm7
  0.00%    0x00000243d89691c2: vmulpd  ymm12,ymm2,ymm2
  0.01%    0x00000243d89691c6: vmulpd  ymm7,ymm3,ymm3
  0.02%    0x00000243d89691ca: vmulpd  ymm8,ymm4,ymm4
  0.72%    0x00000243d89691ce: vmulpd  ymm9,ymm5,ymm5
  0.00%    0x00000243d89691d2: vmulpd  ymm11,ymm6,ymm6
  0.01%    0x00000243d89691d6: vmulpd  ymm13,ymm10,ymm10
<-- multiplication ends here, scalar reduction starts -->
  0.03%    0x00000243d89691db: vaddsd  xmm0,xmm0,xmm15
  0.72%    0x00000243d89691e0: vpshufd xmm5,xmm15,0eh
  0.01%    0x00000243d89691e6: vaddsd  xmm0,xmm0,xmm5
  2.14%    0x00000243d89691ea: vextractf128 xmm6,ymm15,1h
  0.03%    0x00000243d89691f0: vaddsd  xmm0,xmm0,xmm6
  3.21%    0x00000243d89691f4: vpshufd xmm5,xmm6,0eh
  0.02%    0x00000243d89691f9: vaddsd  xmm0,xmm0,xmm5
  2.81%    0x00000243d89691fd: vaddsd  xmm0,xmm0,xmm13
  2.82%    0x00000243d8969202: vpshufd xmm5,xmm13,0eh
  0.03%    0x00000243d8969208: vaddsd  xmm0,xmm0,xmm5
  2.87%    0x00000243d896920c: vextractf128 xmm6,ymm13,1h
  0.01%    0x00000243d8969212: vaddsd  xmm0,xmm0,xmm6
  3.03%    0x00000243d8969216: vpshufd xmm5,xmm6,0eh
  0.03%    0x00000243d896921b: vaddsd  xmm0,xmm0,xmm5
  2.94%    0x00000243d896921f: vaddsd  xmm0,xmm0,xmm11
  2.70%    0x00000243d8969224: vpshufd xmm5,xmm11,0eh
  0.03%    0x00000243d896922a: vaddsd  xmm0,xmm0,xmm5
  2.98%    0x00000243d896922e: vextractf128 xmm6,ymm11,1h
  0.01%    0x00000243d8969234: vaddsd  xmm0,xmm0,xmm6
  3.11%    0x00000243d8969238: vpshufd xmm5,xmm6,0eh
  0.03%    0x00000243d896923d: vaddsd  xmm0,xmm0,xmm5
  2.95%    0x00000243d8969241: vaddsd  xmm0,xmm0,xmm9
  2.61%    0x00000243d8969246: vpshufd xmm5,xmm9,0eh
  0.02%    0x00000243d896924c: vaddsd  xmm0,xmm0,xmm5
  2.89%    0x00000243d8969250: vextractf128 xmm6,ymm9,1h
  0.04%    0x00000243d8969256: vaddsd  xmm0,xmm0,xmm6
  3.13%    0x00000243d896925a: vpshufd xmm5,xmm6,0eh
  0.01%    0x00000243d896925f: vaddsd  xmm0,xmm0,xmm5
  2.96%    0x00000243d8969263: vaddsd  xmm0,xmm0,xmm8
  2.83%    0x00000243d8969268: vpshufd xmm4,xmm8,0eh
  0.01%    0x00000243d896926e: vaddsd  xmm0,xmm0,xmm4
  3.00%    0x00000243d8969272: vextractf128 xmm10,ymm8,1h
  0.02%    0x00000243d8969278: vaddsd  xmm0,xmm0,xmm10
  3.13%    0x00000243d896927d: vpshufd xmm4,xmm10,0eh
  0.01%    0x00000243d8969283: vaddsd  xmm0,xmm0,xmm4
  3.01%    0x00000243d8969287: vaddsd  xmm0,xmm0,xmm7
  2.95%    0x00000243d896928b: vpshufd xmm1,xmm7,0eh
  0.02%    0x00000243d8969290: vaddsd  xmm0,xmm0,xmm1
  3.06%    0x00000243d8969294: vextractf128 xmm2,ymm7,1h
  0.01%    0x00000243d896929a: vaddsd  xmm0,xmm0,xmm2
  3.07%    0x00000243d896929e: vpshufd xmm1,xmm2,0eh
  0.02%    0x00000243d89692a3: vaddsd  xmm0,xmm0,xmm1
  3.07%    0x00000243d89692a7: vaddsd  xmm0,xmm0,xmm12
  2.92%    0x00000243d89692ac: vpshufd xmm3,xmm12,0eh
  0.02%    0x00000243d89692b2: vaddsd  xmm0,xmm0,xmm3
  3.11%    0x00000243d89692b6: vextractf128 xmm1,ymm12,1h
  0.01%    0x00000243d89692bc: vaddsd  xmm0,xmm0,xmm1
  3.02%    0x00000243d89692c0: vpshufd xmm3,xmm1,0eh
  0.02%    0x00000243d89692c5: vaddsd  xmm0,xmm0,xmm3
  2.97%    0x00000243d89692c9: vmovdqu ymm1,ymmword ptr [rsp+28h]
  0.02%    0x00000243d89692cf: vaddsd  xmm0,xmm0,xmm1
  3.05%    0x00000243d89692d3: vpshufd xmm2,xmm1,0eh
  0.03%    0x00000243d89692d8: vaddsd  xmm0,xmm0,xmm2
  2.97%    0x00000243d89692dc: vextractf128 xmm14,ymm1,1h
  0.01%    0x00000243d89692e2: vaddsd  xmm0,xmm0,xmm14
  2.99%    0x00000243d89692e7: vpshufd xmm2,xmm14,0eh
  0.02%    0x00000243d89692ed: vaddsd  xmm0,xmm0,xmm2 
</pre>

The sequential stream code is not as good - it is scalar - but the difference in performance is not as stark as it might be because of the inefficient scalar reduction in the <code language="java">for</code> loop: this is JLS floating point semantics twisting C2's arm behind its back.

<pre>
  0.00%    0x0000021a1df54c24: vmovsd  xmm0,qword ptr [rbx+r9*8+48h]
  0.00%    0x0000021a1df54c2b: vmovsd  xmm2,qword ptr [rbx+r9*8+18h]
  0.02%    0x0000021a1df54c32: vmovsd  xmm3,qword ptr [rbx+r9*8+40h]
  2.93%    0x0000021a1df54c39: vmovsd  xmm4,qword ptr [rbx+r9*8+38h]
  0.00%    0x0000021a1df54c40: vmovsd  xmm5,qword ptr [rbx+r9*8+30h]
  0.01%    0x0000021a1df54c47: vmovsd  xmm6,qword ptr [rbx+r9*8+28h]
  0.02%    0x0000021a1df54c4e: vmovsd  xmm7,qword ptr [rbx+r9*8+20h]
  2.99%    0x0000021a1df54c55: vmulsd  xmm8,xmm0,xmm0
  0.00%    0x0000021a1df54c59: vmulsd  xmm0,xmm7,xmm7
           0x0000021a1df54c5d: vmulsd  xmm6,xmm6,xmm6
  0.01%    0x0000021a1df54c61: vmulsd  xmm5,xmm5,xmm5
  2.91%    0x0000021a1df54c65: vmulsd  xmm4,xmm4,xmm4
  0.00%    0x0000021a1df54c69: vmulsd  xmm3,xmm3,xmm3
  0.00%    0x0000021a1df54c6d: vmulsd  xmm2,xmm2,xmm2
  0.02%    0x0000021a1df54c71: vaddsd  xmm1,xmm2,xmm1
  6.10%    0x0000021a1df54c75: vaddsd  xmm0,xmm0,xmm1
  5.97%    0x0000021a1df54c79: vaddsd  xmm0,xmm6,xmm0
 16.22%    0x0000021a1df54c7d: vaddsd  xmm0,xmm5,xmm0
  7.86%    0x0000021a1df54c81: vaddsd  xmm0,xmm4,xmm0
 11.16%    0x0000021a1df54c85: vaddsd  xmm1,xmm3,xmm0
 11.90%    0x0000021a1df54c89: vaddsd  xmm0,xmm8,xmm1
</pre>

The same code can be seen in <code language="java">SS_ParallelStream</code>. <code language="java">SS_GenerativeSequentialStream</code> is much more interesting because it hasn't been unrolled - see the interleaved control statements. It is also not vectorised.

<pre>
           0x0000013c1a639c17: vmovsd  xmm0,qword ptr [rbp+r9*8+10h]
  0.01%    0x0000013c1a639c1e: vmulsd  xmm2,xmm0,xmm0    
  0.01%    0x0000013c1a639c22: test    r8d,r8d
           0x0000013c1a639c25: jne     13c1a639e09h   
           0x0000013c1a639c2b: mov     r10d,dword ptr [r12+rax*8+8h]
           0x0000013c1a639c30: cmp     r10d,0f8022d85h 
           0x0000013c1a639c37: jne     13c1a639e3bh     
  0.01%    0x0000013c1a639c3d: vaddsd  xmm2,xmm1,xmm2
  0.01%    0x0000013c1a639c41: vmovsd  qword ptr [rdi+10h],xmm2
  0.00%    0x0000013c1a639c46: movsxd  r10,r9d
           0x0000013c1a639c49: vmovsd  xmm0,qword ptr [rbp+r10*8+18h]
  0.01%    0x0000013c1a639c50: vmulsd  xmm0,xmm0,xmm0
  0.01%    0x0000013c1a639c54: mov     r10d,dword ptr [r12+rax*8+8h]
  0.00%    0x0000013c1a639c59: cmp     r10d,0f8022d85h
           0x0000013c1a639c60: jne     13c1a639e30h
           0x0000013c1a639c66: vaddsd  xmm0,xmm0,xmm2
  0.02%    0x0000013c1a639c6a: vmovsd  qword ptr [rdi+10h],xmm0
  0.02%    0x0000013c1a639c6f: mov     r10d,r9d
           0x0000013c1a639c72: add     r10d,2h 
           0x0000013c1a639c76: cmp     r10d,r11d
           0x0000013c1a639c79: jnl     13c1a639d96h 
  0.01%    0x0000013c1a639c7f: add     r9d,4h 
  0.02%    0x0000013c1a639c83: vmovsd  xmm1,qword ptr [rbp+r10*8+10h]
  0.00%    0x0000013c1a639c8a: movzx   r8d,byte ptr [rdi+0ch]
  0.00%    0x0000013c1a639c8f: vmulsd  xmm1,xmm1,xmm1
  0.01%    0x0000013c1a639c93: test    r8d,r8d
           0x0000013c1a639c96: jne     13c1a639dfbh
  0.01%    0x0000013c1a639c9c: vaddsd  xmm1,xmm0,xmm1
  0.01%    0x0000013c1a639ca0: vmovsd  qword ptr [rdi+10h],xmm1
  0.02%    0x0000013c1a639ca5: movsxd  r8,r10d
  0.00%    0x0000013c1a639ca8: vmovsd  xmm0,qword ptr [rbp+r8*8+18h]
           0x0000013c1a639caf: vmulsd  xmm0,xmm0,xmm0
           0x0000013c1a639cb3: vaddsd  xmm0,xmm0,xmm1
  0.06%    0x0000013c1a639cb7: vmovsd  qword ptr [rdi+10h],xmm0
</pre>

So it looks like streams don't vectorise like good old <code language="java">for</code> loops, and you won't gain from <code language="java">Stream.parallelStream</code> unless you have <em>humungous</em> arrays (which you might be avoiding for other reasons). This was actually a very nice case for the <code language="java">Stream</code> because optimal code can't be generated for floating point reductions. What happens with sum of squares for <code language="java">int</code>s? Generating data in an unsurprising way:

<code class="language-java">
  @Benchmark
  public int SS_SequentialStream_Int() {
    return IntStream.of(intData)
            .map(x -> x * x)
            .reduce((x, y) -> x + y)
            .orElse(0);
  }

  @Benchmark
  public int SS_ParallelStream_Int() {
    return IntStream.of(intData)
            .parallel()
            .map(x -> x * x)
            .reduce((x, y) -> x + y)
            .orElse(0);
  }

  @Benchmark
  public int SS_ForLoop_Int() {
    int result = 0;
    for (int i = 0; i < intData.length; ++i) {
      result += intData[i] * intData[i];
    }
    return result;
  }

  @Benchmark
  public int SS_GenerativeSequentialStream_Int() {
    return IntStream.iterate(0, i -> i < size, i -> i + 1)
            .map(i -> intData[i])
            .map(x -> x * x)
            .reduce((x, y) -> x + y)
            .orElse(0);
  }
</code>

The landscape has completely changed, thanks to the exploitation of associative arithmetic and the <code language="java">VPHADDD</code> instruction which simplifies the reduction in the for loop. 

<pre>
<-- load -->
  0.00%    0x000001f5cdd8cd30: vmovdqu ymm0,ymmword ptr [rdi+r10*4+0f0h]
  1.93%    0x000001f5cdd8cd3a: vmovdqu ymm1,ymmword ptr [rdi+r10*4+0d0h]
  0.10%    0x000001f5cdd8cd44: vmovdqu ymm2,ymmword ptr [rdi+r10*4+0b0h]
  0.07%    0x000001f5cdd8cd4e: vmovdqu ymm3,ymmword ptr [rdi+r10*4+90h]
  0.05%    0x000001f5cdd8cd58: vmovdqu ymm4,ymmword ptr [rdi+r10*4+70h]
  1.75%    0x000001f5cdd8cd5f: vmovdqu ymm5,ymmword ptr [rdi+r10*4+50h]
  0.08%    0x000001f5cdd8cd66: vmovdqu ymm6,ymmword ptr [rdi+r10*4+30h]
  0.07%    0x000001f5cdd8cd6d: vmovdqu ymm7,ymmword ptr [rdi+r10*4+10h]
<-- multiply -->
  0.01%    0x000001f5cdd8cd74: vpmulld ymm0,ymm0,ymm0
  1.81%    0x000001f5cdd8cd79: vmovdqu ymmword ptr [rsp+28h],ymm0
  0.02%    0x000001f5cdd8cd7f: vpmulld ymm15,ymm7,ymm7
  1.79%    0x000001f5cdd8cd84: vpmulld ymm11,ymm1,ymm1
  0.06%    0x000001f5cdd8cd89: vpmulld ymm8,ymm2,ymm2
  1.82%    0x000001f5cdd8cd8e: vpmulld ymm9,ymm3,ymm3
  0.06%    0x000001f5cdd8cd93: vpmulld ymm10,ymm4,ymm4
  1.79%    0x000001f5cdd8cd98: vpmulld ymm12,ymm5,ymm5
  0.08%    0x000001f5cdd8cd9d: vpmulld ymm6,ymm6,ymm6
<-- vectorised reduce -->
  1.83%    0x000001f5cdd8cda2: vphaddd ymm4,ymm15,ymm15
  0.04%    0x000001f5cdd8cda7: vphaddd ymm4,ymm4,ymm7
  1.85%    0x000001f5cdd8cdac: vextracti128 xmm7,ymm4,1h
  0.07%    0x000001f5cdd8cdb2: vpaddd  xmm4,xmm4,xmm7
  1.78%    0x000001f5cdd8cdb6: vmovd   xmm7,r8d
  0.01%    0x000001f5cdd8cdbb: vpaddd  xmm7,xmm7,xmm4
  0.11%    0x000001f5cdd8cdbf: vmovd   r11d,xmm7
  0.05%    0x000001f5cdd8cdc4: vphaddd ymm4,ymm6,ymm6
  1.84%    0x000001f5cdd8cdc9: vphaddd ymm4,ymm4,ymm7
  5.43%    0x000001f5cdd8cdce: vextracti128 xmm7,ymm4,1h
  0.13%    0x000001f5cdd8cdd4: vpaddd  xmm4,xmm4,xmm7
  4.34%    0x000001f5cdd8cdd8: vmovd   xmm7,r11d
  0.36%    0x000001f5cdd8cddd: vpaddd  xmm7,xmm7,xmm4
  1.40%    0x000001f5cdd8cde1: vmovd   r8d,xmm7
  0.01%    0x000001f5cdd8cde6: vphaddd ymm6,ymm12,ymm12
  2.89%    0x000001f5cdd8cdeb: vphaddd ymm6,ymm6,ymm4
  3.25%    0x000001f5cdd8cdf0: vextracti128 xmm4,ymm6,1h
  0.87%    0x000001f5cdd8cdf6: vpaddd  xmm6,xmm6,xmm4
  6.36%    0x000001f5cdd8cdfa: vmovd   xmm4,r8d
  0.01%    0x000001f5cdd8cdff: vpaddd  xmm4,xmm4,xmm6
  1.69%    0x000001f5cdd8ce03: vmovd   r8d,xmm4
  0.03%    0x000001f5cdd8ce08: vphaddd ymm4,ymm10,ymm10
  1.83%    0x000001f5cdd8ce0d: vphaddd ymm4,ymm4,ymm7
  0.10%    0x000001f5cdd8ce12: vextracti128 xmm7,ymm4,1h
  3.29%    0x000001f5cdd8ce18: vpaddd  xmm4,xmm4,xmm7
  0.72%    0x000001f5cdd8ce1c: vmovd   xmm7,r8d
  0.23%    0x000001f5cdd8ce21: vpaddd  xmm7,xmm7,xmm4
  4.42%    0x000001f5cdd8ce25: vmovd   r11d,xmm7
  0.12%    0x000001f5cdd8ce2a: vphaddd ymm5,ymm9,ymm9
  1.69%    0x000001f5cdd8ce2f: vphaddd ymm5,ymm5,ymm1
  0.12%    0x000001f5cdd8ce34: vextracti128 xmm1,ymm5,1h
  3.28%    0x000001f5cdd8ce3a: vpaddd  xmm5,xmm5,xmm1
  0.22%    0x000001f5cdd8ce3e: vmovd   xmm1,r11d
  0.14%    0x000001f5cdd8ce43: vpaddd  xmm1,xmm1,xmm5
  3.81%    0x000001f5cdd8ce47: vmovd   r11d,xmm1
  0.22%    0x000001f5cdd8ce4c: vphaddd ymm0,ymm8,ymm8
  1.58%    0x000001f5cdd8ce51: vphaddd ymm0,ymm0,ymm3
  0.22%    0x000001f5cdd8ce56: vextracti128 xmm3,ymm0,1h
  2.82%    0x000001f5cdd8ce5c: vpaddd  xmm0,xmm0,xmm3
  0.36%    0x000001f5cdd8ce60: vmovd   xmm3,r11d
  0.20%    0x000001f5cdd8ce65: vpaddd  xmm3,xmm3,xmm0
  4.55%    0x000001f5cdd8ce69: vmovd   r8d,xmm3
  0.10%    0x000001f5cdd8ce6e: vphaddd ymm2,ymm11,ymm11
  1.71%    0x000001f5cdd8ce73: vphaddd ymm2,ymm2,ymm1
  0.09%    0x000001f5cdd8ce78: vextracti128 xmm1,ymm2,1h
  2.91%    0x000001f5cdd8ce7e: vpaddd  xmm2,xmm2,xmm1
  1.57%    0x000001f5cdd8ce82: vmovd   xmm1,r8d
  0.05%    0x000001f5cdd8ce87: vpaddd  xmm1,xmm1,xmm2
  4.84%    0x000001f5cdd8ce8b: vmovd   r11d,xmm1
  0.06%    0x000001f5cdd8ce90: vmovdqu ymm0,ymmword ptr [rsp+28h]
  0.03%    0x000001f5cdd8ce96: vphaddd ymm13,ymm0,ymm0
  1.83%    0x000001f5cdd8ce9b: vphaddd ymm13,ymm13,ymm14
  2.16%    0x000001f5cdd8cea0: vextracti128 xmm14,ymm13,1h
  0.14%    0x000001f5cdd8cea6: vpaddd  xmm13,xmm13,xmm14
  0.09%    0x000001f5cdd8ceab: vmovd   xmm14,r11d
  0.51%    0x000001f5cdd8ceb0: vpaddd  xmm14,xmm14,xmm13
</pre>

If you're the guy replacing all the <code language="java">for</code> loops with streams because it's 2018, you may be committing performance vandalism! That nice declarative <em>API</em> (as opposed to language feature) is at arms length and it really isn't well optimised yet.

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
<td>SS_ForLoop_Int</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1021725.018981</td>
<td align="right">74264.883362</td>
<td>ops/s</td>
<td align="right">1024</td>
</tr>
<tr>
<td>SS_ForLoop_Int</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">129250.855026</td>
<td align="right">5764.608094</td>
<td>ops/s</td>
<td align="right">8192</td>
</tr>
<tr>
<td>SS_GenerativeSequentialStream_Int</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">55069.227826</td>
<td align="right">1111.903102</td>
<td>ops/s</td>
<td align="right">1024</td>
</tr>
<tr>
<td>SS_GenerativeSequentialStream_Int</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">6769.176830</td>
<td align="right">684.970867</td>
<td>ops/s</td>
<td align="right">8192</td>
</tr>
<tr>
<td>SS_ParallelStream_Int</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">20970.387258</td>
<td align="right">719.846643</td>
<td>ops/s</td>
<td align="right">1024</td>
</tr>
<tr>
<td>SS_ParallelStream_Int</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">19621.397202</td>
<td align="right">1514.374286</td>
<td>ops/s</td>
<td align="right">8192</td>
</tr>
<tr>
<td>SS_SequentialStream_Int</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">586847.001223</td>
<td align="right">22390.512706</td>
<td>ops/s</td>
<td align="right">1024</td>
</tr>
<tr>
<td>SS_SequentialStream_Int</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">87620.959677</td>
<td align="right">3437.083075</td>
<td>ops/s</td>
<td align="right">8192</td>
</tr>
</tbody></table>
</div>

Parallel streams might not be the best thing to reach for.