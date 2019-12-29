---
title: "Faster Floating Point Reductions"
layout: post
redirect_from:
  - /faster-floating-point-reductions/
date: 2018-02-18 20:48:11
---
At the moment, I am working on a hobby project called <a href="https://github.com/richardstartin/splitmap" rel="noopener" target="_blank">SplitMap</a>, which aims to evaluate aggregations over complex boolean expressions as fast as possible using the same high level constructs of the streams API. It's already capable of performing logic that takes vanilla parallel streams 20ms in under 300μs, but I think sub 100μs is possible for these calculations. I have reached the stage where the bottleneck is floating point reductions: Java won't vectorise these because the result would be numerically unstable. This is a bit limiting, because it often doesn't matter very much: nobody represents money with floating point numbers, and if you're solving stiff differential equations it won't be numerical stability that stops you from using a more suitable language. The reality is, somebody somewhere probably really <em>cares</em> about this, and that's probably why there's no `fastfp` semantics in the language. This ancient <a href="https://jcp.org/en/jsr/detail?id=84" rel="noopener" target="_blank">proposal</a> lay stagnant before being withdrawn, and several optimisations just can't be implemented by the JIT compiler without violating language guarantees. An intrinsic for <a href="https://richardstartin.github.io/posts/new-methods-in-java-9-math-fma-and-arrays-mismatch/" rel="noopener" target="_blank">FMA</a> only arrived in Java 9, 15 years after JSR 84 was withdrawn, and <a href="https://richardstartin.github.io/posts/autovectorised-fma-in-jdk10/" rel="noopener" target="_blank">vectorised FMA is only available in JDK10</a>, 18 years after JSR 84 was proposed. Computing an average is hardly numerical computing, but Java just isn't a friendly language for this sort of thing.

Back to SplitMap. At this point, I've already maxed out the parallelism I can get from the fork join pool, so I want the code below to vectorise to squeeze out more performance:

```java
private double reduce(double[] data) {
    double reduced = 0D;
    for (int i = 0; i < data.length; ++i) {
      reduced += data[i];
    }
    return reduced;
  }
```

Looking at this with perfasm, it's clear that unrolled scalar code is generated:

```asm
  0.00%    0x000001db0c6f5730: vaddsd  xmm0,xmm0,mmword ptr [rdx+rdi*8+10h]
  6.17%    0x000001db0c6f5736: vaddsd  xmm0,xmm0,mmword ptr [rdx+rdi*8+18h]
  6.15%    0x000001db0c6f573c: vaddsd  xmm0,xmm0,mmword ptr [rdx+rdi*8+20h]
  6.23%    0x000001db0c6f5742: vaddsd  xmm0,xmm0,mmword ptr [rdx+rdi*8+28h]
  6.16%    0x000001db0c6f5748: vaddsd  xmm0,xmm0,mmword ptr [rdx+rdi*8+30h]
  6.37%    0x000001db0c6f574e: vaddsd  xmm0,xmm0,mmword ptr [rdx+rdi*8+38h]
  6.22%    0x000001db0c6f5754: vaddsd  xmm0,xmm0,mmword ptr [rdx+rdi*8+40h]
  6.21%    0x000001db0c6f575a: vaddsd  xmm0,xmm0,mmword ptr [rdx+rdi*8+48h]
  6.11%    0x000001db0c6f5760: vaddsd  xmm0,xmm0,mmword ptr [rdx+rdi*8+50h]
  6.18%    0x000001db0c6f5766: vaddsd  xmm0,xmm0,mmword ptr [rdx+rdi*8+58h]
  6.18%    0x000001db0c6f576c: vaddsd  xmm0,xmm0,mmword ptr [rdx+rdi*8+60h]
  6.30%    0x000001db0c6f5772: vaddsd  xmm0,xmm0,mmword ptr [rdx+rdi*8+68h]
  6.23%    0x000001db0c6f5778: vaddsd  xmm0,xmm0,mmword ptr [rdx+rdi*8+70h]
  6.33%    0x000001db0c6f577e: vaddsd  xmm0,xmm0,mmword ptr [rdx+rdi*8+78h]
  6.25%    0x000001db0c6f5784: vaddsd  xmm0,xmm0,mmword ptr [rdx+rdi*8+80h]
  6.31%    0x000001db0c6f578d: vaddsd  xmm0,xmm0,mmword ptr [rdx+rdi*8+88h]
```


Let's do something really dumb - allocate an array! Then I'll reduce vertically onto it, and do a small horizontal reduction at the end.

```java
  @Benchmark
  public double reduceBuffered() {
    double[] buffer = new double[1024];
    for (int i = 0; i < data.length; ++i) {
      buffer[i & 1023] += data[i];
    }
    return reduce(buffer);
  }
```

I benchmarked this against `reduce`. Using size 1024 as a sanity check, it's clear the work is just being done twice, which is reassuring. Once the array gets a bit bigger, the gains of (what I think should be) the faster vertical reduction prior to the horizontal reduction pays for the array allocation.


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
<td>reduceBuffered</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">333.990079</td>
<td align="right">3.542656</td>
<td>ops/ms</td>
<td align="right">1024</td>
</tr>
<tr>
<td>reduceBuffered</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">18.639314</td>
<td align="right">0.488300</td>
<td>ops/ms</td>
<td align="right">65536</td>
</tr>
<tr>
<td>reduceBuffered</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">9.313916</td>
<td align="right">0.343261</td>
<td>ops/ms</td>
<td align="right">131072</td>
</tr>
<tr>
<td>reduceSimple</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">656.408971</td>
<td align="right">1.771530</td>
<td>ops/ms</td>
<td align="right">1024</td>
</tr>
<tr>
<td>reduceSimple</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">9.840417</td>
<td align="right">0.032713</td>
<td>ops/ms</td>
<td align="right">65536</td>
</tr>
<tr>
<td>reduceSimple</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">4.881353</td>
<td align="right">0.076707</td>
<td>ops/ms</td>
<td align="right">131072</td>
</tr>
</tbody></table>
</div>

The code in `reduceBuffered` produces a slightly different result because the elements are summated in a different order, though you're hardly likely to notice. While, by any pragmatic definition, the function performs the same operation, it <strong>is</strong> semantically different. C2 actually doesn't vectorise this code, and I have no idea why it's so much faster! I won't dwell on this because this is a dead end. In any case, here's the perfasm output:

```asm
  0.20%    0x000001eaf2e49f50: vmovsd  xmm0,qword ptr [rdx+r9*8+10h]
  0.27%    0x000001eaf2e49f57: mov     ebx,r9d
  1.95%    0x000001eaf2e49f5a: add     ebx,0fh
  0.36%    0x000001eaf2e49f5d: and     ebx,3ffh
  0.21%    0x000001eaf2e49f63: mov     ecx,r9d
  0.30%    0x000001eaf2e49f66: and     ecx,3ffh          ;*iand {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@22 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  2.96%    0x000001eaf2e49f6c: vaddsd  xmm0,xmm0,mmword ptr [r8+rcx*8+10h]
  0.61%    0x000001eaf2e49f73: vmovsd  qword ptr [r8+rcx*8+10h],xmm0
                                                         ;*dastore {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@32 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  0.50%    0x000001eaf2e49f7a: mov     ecx,r9d
  1.78%    0x000001eaf2e49f7d: inc     ecx
  0.37%    0x000001eaf2e49f7f: and     ecx,3ffh          ;*iand {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@22 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  0.17%    0x000001eaf2e49f85: vmovsd  xmm0,qword ptr [r8+rcx*8+10h]
  0.49%    0x000001eaf2e49f8c: vaddsd  xmm0,xmm0,mmword ptr [rdx+r9*8+18h]
  2.51%    0x000001eaf2e49f93: vmovsd  qword ptr [r8+rcx*8+10h],xmm0
                                                         ;*dastore {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@32 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  1.21%    0x000001eaf2e49f9a: mov     ecx,r9d
  0.34%    0x000001eaf2e49f9d: add     ecx,2h
  0.90%    0x000001eaf2e49fa0: and     ecx,3ffh          ;*iand {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@22 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  0.32%    0x000001eaf2e49fa6: vmovsd  xmm0,qword ptr [r8+rcx*8+10h]
  1.28%    0x000001eaf2e49fad: vaddsd  xmm0,xmm0,mmword ptr [rdx+r9*8+20h]
  1.43%    0x000001eaf2e49fb4: vmovsd  qword ptr [r8+rcx*8+10h],xmm0
                                                         ;*dastore {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@32 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  1.38%    0x000001eaf2e49fbb: vmovsd  xmm0,qword ptr [rdx+r9*8+28h]
  0.47%    0x000001eaf2e49fc2: mov     ecx,r9d
  0.28%    0x000001eaf2e49fc5: add     ecx,3h
  0.77%    0x000001eaf2e49fc8: and     ecx,3ffh          ;*iand {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@22 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  1.34%    0x000001eaf2e49fce: vaddsd  xmm0,xmm0,mmword ptr [r8+rcx*8+10h]
  0.93%    0x000001eaf2e49fd5: vmovsd  qword ptr [r8+rcx*8+10h],xmm0
                                                         ;*dastore {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@32 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  1.36%    0x000001eaf2e49fdc: mov     ecx,r9d
  0.75%    0x000001eaf2e49fdf: add     ecx,4h
  0.43%    0x000001eaf2e49fe2: and     ecx,3ffh          ;*iand {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@22 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  0.32%    0x000001eaf2e49fe8: vmovsd  xmm0,qword ptr [r8+rcx*8+10h]
  1.32%    0x000001eaf2e49fef: vaddsd  xmm0,xmm0,mmword ptr [rdx+r9*8+30h]
  1.32%    0x000001eaf2e49ff6: vmovsd  qword ptr [r8+rcx*8+10h],xmm0
                                                         ;*dastore {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@32 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  1.24%    0x000001eaf2e49ffd: mov     ecx,r9d
  0.40%    0x000001eaf2e4a000: add     ecx,5h
  0.79%    0x000001eaf2e4a003: and     ecx,3ffh          ;*iand {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@22 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  0.46%    0x000001eaf2e4a009: vmovsd  xmm0,qword ptr [r8+rcx*8+10h]
  1.22%    0x000001eaf2e4a010: vaddsd  xmm0,xmm0,mmword ptr [rdx+r9*8+38h]
  4.18%    0x000001eaf2e4a017: vmovsd  qword ptr [r8+rcx*8+10h],xmm0
                                                         ;*dastore {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@32 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  1.61%    0x000001eaf2e4a01e: mov     ecx,r9d
  0.24%    0x000001eaf2e4a021: add     ecx,6h
  0.34%    0x000001eaf2e4a024: and     ecx,3ffh          ;*iand {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@22 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  0.69%    0x000001eaf2e4a02a: vmovsd  xmm0,qword ptr [r8+rcx*8+10h]
  1.55%    0x000001eaf2e4a031: vaddsd  xmm0,xmm0,mmword ptr [rdx+r9*8+40h]
  0.95%    0x000001eaf2e4a038: vmovsd  qword ptr [r8+rcx*8+10h],xmm0
                                                         ;*dastore {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@32 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  1.97%    0x000001eaf2e4a03f: mov     ecx,r9d
  0.37%    0x000001eaf2e4a042: add     ecx,7h
  0.20%    0x000001eaf2e4a045: and     ecx,3ffh          ;*iand {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@22 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  0.32%    0x000001eaf2e4a04b: vmovsd  xmm0,qword ptr [r8+rcx*8+10h]
  1.95%    0x000001eaf2e4a052: vaddsd  xmm0,xmm0,mmword ptr [rdx+r9*8+48h]
  0.92%    0x000001eaf2e4a059: vmovsd  qword ptr [r8+rcx*8+10h],xmm0
                                                         ;*dastore {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@32 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  1.95%    0x000001eaf2e4a060: mov     ecx,r9d
  0.42%    0x000001eaf2e4a063: add     ecx,8h
  0.35%    0x000001eaf2e4a066: and     ecx,3ffh          ;*iand {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@22 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  0.20%    0x000001eaf2e4a06c: vmovsd  xmm0,qword ptr [r8+rcx*8+10h]
  1.97%    0x000001eaf2e4a073: vaddsd  xmm0,xmm0,mmword ptr [rdx+r9*8+50h]
  1.22%    0x000001eaf2e4a07a: vmovsd  qword ptr [r8+rcx*8+10h],xmm0
                                                         ;*dastore {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@32 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  1.67%    0x000001eaf2e4a081: mov     ecx,r9d
  0.48%    0x000001eaf2e4a084: add     ecx,9h
  0.39%    0x000001eaf2e4a087: and     ecx,3ffh          ;*iand {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@22 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  0.32%    0x000001eaf2e4a08d: vmovsd  xmm0,qword ptr [r8+rcx*8+10h]
  1.66%    0x000001eaf2e4a094: vaddsd  xmm0,xmm0,mmword ptr [rdx+r9*8+58h]
  1.14%    0x000001eaf2e4a09b: vmovsd  qword ptr [r8+rcx*8+10h],xmm0
                                                         ;*dastore {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@32 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  1.45%    0x000001eaf2e4a0a2: mov     ecx,r9d
  0.65%    0x000001eaf2e4a0a5: add     ecx,0ah
  0.49%    0x000001eaf2e4a0a8: and     ecx,3ffh          ;*iand {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@22 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  0.39%    0x000001eaf2e4a0ae: vmovsd  xmm0,qword ptr [r8+rcx*8+10h]
  1.45%    0x000001eaf2e4a0b5: vaddsd  xmm0,xmm0,mmword ptr [rdx+r9*8+60h]
  1.32%    0x000001eaf2e4a0bc: vmovsd  qword ptr [r8+rcx*8+10h],xmm0
                                                         ;*dastore {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@32 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  1.39%    0x000001eaf2e4a0c3: mov     ecx,r9d
  0.39%    0x000001eaf2e4a0c6: add     ecx,0bh
  0.65%    0x000001eaf2e4a0c9: and     ecx,3ffh          ;*iand {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@22 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  0.53%    0x000001eaf2e4a0cf: vmovsd  xmm0,qword ptr [r8+rcx*8+10h]
  1.37%    0x000001eaf2e4a0d6: vaddsd  xmm0,xmm0,mmword ptr [rdx+r9*8+68h]
  1.22%    0x000001eaf2e4a0dd: vmovsd  qword ptr [r8+rcx*8+10h],xmm0
                                                         ;*dastore {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@32 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  1.46%    0x000001eaf2e4a0e4: mov     ecx,r9d
  0.42%    0x000001eaf2e4a0e7: add     ecx,0ch
  0.40%    0x000001eaf2e4a0ea: and     ecx,3ffh          ;*iand {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@22 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  0.60%    0x000001eaf2e4a0f0: vmovsd  xmm0,qword ptr [r8+rcx*8+10h]
  1.47%    0x000001eaf2e4a0f7: vaddsd  xmm0,xmm0,mmword ptr [rdx+r9*8+70h]
  1.04%    0x000001eaf2e4a0fe: vmovsd  qword ptr [r8+rcx*8+10h],xmm0
                                                         ;*dastore {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@32 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  1.74%    0x000001eaf2e4a105: mov     ecx,r9d
  0.37%    0x000001eaf2e4a108: add     ecx,0dh
  0.43%    0x000001eaf2e4a10b: and     ecx,3ffh          ;*iand {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@22 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  0.36%    0x000001eaf2e4a111: vmovsd  xmm0,qword ptr [r8+rcx*8+10h]
  1.68%    0x000001eaf2e4a118: vaddsd  xmm0,xmm0,mmword ptr [rdx+r9*8+78h]
  2.82%    0x000001eaf2e4a11f: vmovsd  qword ptr [r8+rcx*8+10h],xmm0
                                                         ;*dastore {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@32 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  2.04%    0x000001eaf2e4a126: mov     ecx,r9d
  0.19%    0x000001eaf2e4a129: add     ecx,0eh
  0.29%    0x000001eaf2e4a12c: and     ecx,3ffh          ;*iand {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@22 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
  0.36%    0x000001eaf2e4a132: vmovsd  xmm0,qword ptr [r8+rcx*8+10h]
  2.02%    0x000001eaf2e4a139: vaddsd  xmm0,xmm0,mmword ptr [rdx+r9*8+80h]
  0.76%    0x000001eaf2e4a143: vmovsd  qword ptr [r8+rcx*8+10h],xmm0
  1.99%    0x000001eaf2e4a14a: vmovsd  xmm0,qword ptr [rdx+r9*8+88h]
  0.39%    0x000001eaf2e4a154: vaddsd  xmm0,xmm0,mmword ptr [r8+rbx*8+10h]
  0.56%    0x000001eaf2e4a15b: vmovsd  qword ptr [r8+rbx*8+10h],xmm0
                                                         ;*dastore {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.reduction.ReduceArray::reduceBuffered@32 (line 36)
                                                         ; - com.openkappa.simd.reduction.generated.ReduceArray_reduceBuffered_jmhTest::reduceBuffered_thrpt_jmhStub@17 (line 119)
```

Using the same idea, but employing a <a href="https://richardstartin.github.io/posts/multiplying-matrices-fast-and-slow/" rel="noopener" target="_blank">trick I've used before for matrix multiplication</a>, the code gets a lot faster!

```java
  @Benchmark
  public double reduceVectorised() {
    double[] buffer = new double[1024];
    double[] temp = new double[1024];
    for (int i = 0; i < data.length >>> 10; ++i) {
      System.arraycopy(data, i * 1024, temp, 0,  temp.length);
      for (int j = 0; j < 1024; ++j) {
        buffer[j] += temp[j];
      }
    }
    return reduce(buffer);
  }
```

This generates a vectorised main loop:

```asm
  0.05%    0x000001e3fc0d71e0: vmovdqu ymm0,ymmword ptr [r9+r10*8+10h]
  0.16%    0x000001e3fc0d71e7: vaddpd  ymm0,ymm0,ymmword ptr [r13+r10*8+10h]
  1.26%    0x000001e3fc0d71ee: vmovdqu ymmword ptr [r13+r10*8+10h],ymm0
  0.39%    0x000001e3fc0d71f5: vmovdqu ymm0,ymmword ptr [r9+r10*8+30h]
  0.18%    0x000001e3fc0d71fc: vaddpd  ymm0,ymm0,ymmword ptr [r13+r10*8+30h]
  0.93%    0x000001e3fc0d7203: vmovdqu ymmword ptr [r13+r10*8+30h],ymm0
  0.68%    0x000001e3fc0d720a: vmovdqu ymm0,ymmword ptr [r9+r10*8+50h]
  0.17%    0x000001e3fc0d7211: vaddpd  ymm0,ymm0,ymmword ptr [r13+r10*8+50h]
  0.86%    0x000001e3fc0d7218: vmovdqu ymmword ptr [r13+r10*8+50h],ymm0
  0.73%    0x000001e3fc0d721f: vmovdqu ymm0,ymmword ptr [r9+r10*8+70h]
  0.19%    0x000001e3fc0d7226: vaddpd  ymm0,ymm0,ymmword ptr [r13+r10*8+70h]
  0.86%    0x000001e3fc0d722d: vmovdqu ymmword ptr [r13+r10*8+70h],ymm0
  0.78%    0x000001e3fc0d7234: vmovdqu ymm0,ymmword ptr [r9+r10*8+90h]
  0.17%    0x000001e3fc0d723e: vaddpd  ymm0,ymm0,ymmword ptr [r13+r10*8+90h]
  0.75%    0x000001e3fc0d7248: vmovdqu ymmword ptr [r13+r10*8+90h],ymm0
  0.84%    0x000001e3fc0d7252: vmovdqu ymm0,ymmword ptr [r9+r10*8+0b0h]
  0.15%    0x000001e3fc0d725c: vaddpd  ymm0,ymm0,ymmword ptr [r13+r10*8+0b0h]
  0.64%    0x000001e3fc0d7266: vmovdqu ymmword ptr [r13+r10*8+0b0h],ymm0
  0.92%    0x000001e3fc0d7270: vmovdqu ymm0,ymmword ptr [r9+r10*8+0d0h]
  0.15%    0x000001e3fc0d727a: vaddpd  ymm0,ymm0,ymmword ptr [r13+r10*8+0d0h]
  0.71%    0x000001e3fc0d7284: vmovdqu ymmword ptr [r13+r10*8+0d0h],ymm0
  0.91%    0x000001e3fc0d728e: vmovdqu ymm0,ymmword ptr [r9+r10*8+0f0h]
  0.15%    0x000001e3fc0d7298: vaddpd  ymm0,ymm0,ymmword ptr [r13+r10*8+0f0h]
  0.74%    0x000001e3fc0d72a2: vmovdqu ymmword ptr [r13+r10*8+0f0h],ymm0
  0.96%    0x000001e3fc0d72ac: vmovdqu ymm0,ymmword ptr [r9+r10*8+110h]
  0.12%    0x000001e3fc0d72b6: vaddpd  ymm0,ymm0,ymmword ptr [r13+r10*8+110h]
  0.70%    0x000001e3fc0d72c0: vmovdqu ymmword ptr [r13+r10*8+110h],ymm0
  0.99%    0x000001e3fc0d72ca: vmovdqu ymm0,ymmword ptr [r9+r10*8+130h]
  0.13%    0x000001e3fc0d72d4: vaddpd  ymm0,ymm0,ymmword ptr [r13+r10*8+130h]
  0.71%    0x000001e3fc0d72de: vmovdqu ymmword ptr [r13+r10*8+130h],ymm0
  0.94%    0x000001e3fc0d72e8: vmovdqu ymm0,ymmword ptr [r9+r10*8+150h]
  0.12%    0x000001e3fc0d72f2: vaddpd  ymm0,ymm0,ymmword ptr [r13+r10*8+150h]
  0.70%    0x000001e3fc0d72fc: vmovdqu ymmword ptr [r13+r10*8+150h],ymm0
  1.01%    0x000001e3fc0d7306: vmovdqu ymm0,ymmword ptr [r9+r10*8+170h]
  0.14%    0x000001e3fc0d7310: vaddpd  ymm0,ymm0,ymmword ptr [r13+r10*8+170h]
  0.75%    0x000001e3fc0d731a: vmovdqu ymmword ptr [r13+r10*8+170h],ymm0
  1.00%    0x000001e3fc0d7324: vmovdqu ymm0,ymmword ptr [r9+r10*8+190h]
  0.13%    0x000001e3fc0d732e: vaddpd  ymm0,ymm0,ymmword ptr [r13+r10*8+190h]
  0.67%    0x000001e3fc0d7338: vmovdqu ymmword ptr [r13+r10*8+190h],ymm0
  0.97%    0x000001e3fc0d7342: vmovdqu ymm0,ymmword ptr [r9+r10*8+1b0h]
  0.14%    0x000001e3fc0d734c: vaddpd  ymm0,ymm0,ymmword ptr [r13+r10*8+1b0h]
  0.72%    0x000001e3fc0d7356: vmovdqu ymmword ptr [r13+r10*8+1b0h],ymm0
  0.99%    0x000001e3fc0d7360: vmovdqu ymm0,ymmword ptr [r9+r10*8+1d0h]
  0.12%    0x000001e3fc0d736a: vaddpd  ymm0,ymm0,ymmword ptr [r13+r10*8+1d0h]
  0.69%    0x000001e3fc0d7374: vmovdqu ymmword ptr [r13+r10*8+1d0h],ymm0
  0.96%    0x000001e3fc0d737e: vmovdqu ymm0,ymmword ptr [r9+r10*8+1f0h]
  0.14%    0x000001e3fc0d7388: vaddpd  ymm0,ymm0,ymmword ptr [r13+r10*8+1f0h]
  0.70%    0x000001e3fc0d7392: vmovdqu ymmword ptr [r13+r10*8+1f0h],ymm0
```

This implementation is more than 3x faster than the original code, which includes the fuss of the buffers and copies. Wouldn't it be nice to be able to opt in to fast floating point semantics somehow? Here are the final results (as usual, this is a throughput benchmark and higher is better):

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
<td>reduceBuffered</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">329.935462</td>
<td align="right">6.295871</td>
<td>ops/ms</td>
<td align="right">1024</td>
</tr>
<tr>
<td>reduceBuffered</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">18.380467</td>
<td align="right">0.455724</td>
<td>ops/ms</td>
<td align="right">65536</td>
</tr>
<tr>
<td>reduceBuffered</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">9.257122</td>
<td align="right">0.402876</td>
<td>ops/ms</td>
<td align="right">131072</td>
</tr>
<tr>
<td>reduceSimple</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">654.809021</td>
<td align="right">5.812795</td>
<td>ops/ms</td>
<td align="right">1024</td>
</tr>
<tr>
<td>reduceSimple</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">9.694730</td>
<td align="right">0.325011</td>
<td>ops/ms</td>
<td align="right">65536</td>
</tr>
<tr>
<td>reduceSimple</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">4.772520</td>
<td align="right">0.265691</td>
<td>ops/ms</td>
<td align="right">131072</td>
</tr>
<tr>
<td>reduceVectorised</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">287.712794</td>
<td align="right">27.492846</td>
<td>ops/ms</td>
<td align="right">1024</td>
</tr>
<tr>
<td>reduceVectorised</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">34.454235</td>
<td align="right">1.293985</td>
<td>ops/ms</td>
<td align="right">65536</td>
</tr>
<tr>
<td>reduceVectorised</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">17.867701</td>
<td align="right">0.813367</td>
<td>ops/ms</td>
<td align="right">131072</td>
</tr>
</tbody></table>
</div>

The benchmark is on <a href="https://github.com/richardstartin/simdbenchmarks/blob/master/src/main/java/com/openkappa/simd/reduction/ReduceArray.java" rel="noopener" target="_blank">github</a>.