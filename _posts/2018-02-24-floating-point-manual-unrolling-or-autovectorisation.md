---
ID: 10606
title: 'Floating Point: Manual Unrolling or Autovectorisation?'
author: Richard Startin
post_excerpt: ""
layout: default

published: true
date: 2018-02-24 22:03:51
---
Java is very strict about floating point arithmetic. There's even a keyword, `strictfp`, which allows you to make it stricter, ensuring you'll get a potentially less precise but identical result wherever you run your program. There's actually a <a href="http://openjdk.java.net/jeps/306">JEP</a> to make this the <em>only</em> behaviour. <a href="https://docs.oracle.com/javase/specs/jls/se7/html/jls-15.html#jls-15.18.2" rel="noopener" target="_blank">JLS 15.18.2</a> states clearly that floating point addition is not associative in Java, which means that JIT compilers have to respect the order of `double[]`s and `float[]`s when compiling code, even if it turns out the order is actually arbitrary to the application. This means they can't vectorise or even pipeline loops containing interdependent floating point addition, can't distribute multiplications over additions, can't telescopically collapse multiplications: the list goes on. If you want this code to go faster you must work around the JIT compiler somehow. In C++, it's possible to choose to treat floating point numbers as if they had the algebraic properties of the Reals. Using this option is often maligned, perhaps because it assumes much more than associativity, and applies to entire compilation units. A <a href="https://jcp.org/en/jsr/detail?id=84" rel="noopener" target="_blank">proposal</a> for `fastfp` semantics at a class and method scope was withdrawn a long time ago.

Prior to the arrival of the <a href="https://software.intel.com/en-us/articles/vector-api-developer-program-for-java" rel="noopener" target="_blank">Vector API</a>, I'm interested in which vectorisation transformations are possible automatically. This is because I've found that many bottlenecks in applications are related to low single threaded performance, and others come from the premature usage of threads to solve these performance problems. Imagine how powerful multithreading could be if used only <em>after</em> saturating the intensity available on each core? 

There are certain things you just can't do in Java because of the language specification, and one of these is getting C2 to pipeline two or more dependent `vpaddd` instructions, so the maximum achievable floating point intensity is quite low. In fact, you can be better off giving up on autovectorisation and unrolling the loop yourself, allowing the pipelining of scalar additions. This depends intimately on your microarchitecture.

<h3>Double Precision Sum Product</h3>

C2 can automatically vectorise a sum product between two `double[]`s. It does this by issuing eight `vmovdqu` loads at once, then four `vpmulpd` multiplications at once, and then a long in-order scalar reduction. It does this with the simplest possible code, potentially rewarding simplicity with decent performance:

```java
  @Benchmark
  public double vectorisedDoubleSumProduct() {
    double sp = 0D;
    for (int i = 0; i < xd.length && i < yd.length; ++i) {
      sp += xd[i] * yd[i];
    }
    return sp;
  }
```

Perfasm shows the problematic scalar reduction quite clearly:

```asm
....[Hottest Region 1]..............................................................................
c2, com.openkappa.simd.sumproduct.generated.SumProduct_vectorisedDoubleSumProduct_jmhTest::vectorisedDoubleSumProduct_thrpt_jmhStub, version 164 (238 bytes) 

           0x00000144f724f8e9: mov     r8d,r9d
           0x00000144f724f8ec: add     r8d,0fffffff1h
           0x00000144f724f8f0: cmp     r9d,r8d
           0x00000144f724f8f3: mov     edx,80000000h
           0x00000144f724f8f8: cmovl   r8d,edx
           0x00000144f724f8fc: cmp     r11d,r8d
           0x00000144f724f8ff: jnl     144f724f7dfh
           0x00000144f724f905: nop     word ptr [rax+rax+0h]  ;*iload_3 {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.sumproduct.SumProduct::vectorisedDoubleSumProduct@13 (line 43)
                                                         ; - com.openkappa.simd.sumproduct.generated.SumProduct_vectorisedDoubleSumProduct_jmhTest::vectorisedDoubleSumProduct_thrpt_jmhStub@17 (line 119)
  0.00%    0x00000144f724f910: vmovdqu ymm1,ymmword ptr [rsi+r11*8+70h]
  1.07%    0x00000144f724f917: vmovdqu ymm2,ymmword ptr [rax+r11*8+70h]
  2.49%    0x00000144f724f91e: vmovdqu ymm3,ymmword ptr [rsi+r11*8+50h]
  0.67%    0x00000144f724f925: vmovdqu ymm4,ymmword ptr [rax+r11*8+50h]
  0.75%    0x00000144f724f92c: vmovdqu ymm5,ymmword ptr [rsi+r11*8+30h]
  0.01%    0x00000144f724f933: vmovdqu ymm6,ymmword ptr [rax+r11*8+30h]
  1.52%    0x00000144f724f93a: vmovdqu ymm7,ymmword ptr [rsi+r11*8+10h]
                                                         ;*daload {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.sumproduct.SumProduct::vectorisedDoubleSumProduct@34 (line 44)
                                                         ; - com.openkappa.simd.sumproduct.generated.SumProduct_vectorisedDoubleSumProduct_jmhTest::vectorisedDoubleSumProduct_thrpt_jmhStub@17 (line 119)
  0.01%    0x00000144f724f941: vmovdqu ymm8,ymmword ptr [rax+r11*8+10h]
           0x00000144f724f948: vmulpd  ymm9,ymm2,ymm1
  0.02%    0x00000144f724f94c: vmulpd  ymm7,ymm8,ymm7
  1.50%    0x00000144f724f950: vmulpd  ymm8,ymm4,ymm3
  0.02%    0x00000144f724f954: vmulpd  ymm10,ymm6,ymm5
  0.00%    0x00000144f724f958: vaddsd  xmm0,xmm0,xmm7
  1.51%    0x00000144f724f95c: vpshufd xmm1,xmm7,0eh
  0.00%    0x00000144f724f961: vaddsd  xmm0,xmm0,xmm1
  5.91%    0x00000144f724f965: vextractf128 xmm4,ymm7,1h
  0.01%    0x00000144f724f96b: vaddsd  xmm0,xmm0,xmm4
  6.56%    0x00000144f724f96f: vpshufd xmm1,xmm4,0eh
  0.01%    0x00000144f724f974: vaddsd  xmm0,xmm0,xmm1
  5.75%    0x00000144f724f978: vaddsd  xmm0,xmm0,xmm10
  5.71%    0x00000144f724f97d: vpshufd xmm4,xmm10,0eh
  0.00%    0x00000144f724f983: vaddsd  xmm0,xmm0,xmm4
  5.89%    0x00000144f724f987: vextractf128 xmm6,ymm10,1h
  0.01%    0x00000144f724f98d: vaddsd  xmm0,xmm0,xmm6
  6.01%    0x00000144f724f991: vpshufd xmm4,xmm6,0eh
  0.01%    0x00000144f724f996: vaddsd  xmm0,xmm0,xmm4
  5.95%    0x00000144f724f99a: vaddsd  xmm0,xmm0,xmm8
  5.98%    0x00000144f724f99f: vpshufd xmm1,xmm8,0eh
  0.01%    0x00000144f724f9a5: vaddsd  xmm0,xmm0,xmm1
  5.99%    0x00000144f724f9a9: vextractf128 xmm5,ymm8,1h
  0.00%    0x00000144f724f9af: vaddsd  xmm0,xmm0,xmm5
  5.93%    0x00000144f724f9b3: vpshufd xmm1,xmm5,0eh
  0.00%    0x00000144f724f9b8: vaddsd  xmm0,xmm0,xmm1
  6.05%    0x00000144f724f9bc: vaddsd  xmm0,xmm0,xmm9
  5.92%    0x00000144f724f9c1: vpshufd xmm3,xmm9,0eh
  0.00%    0x00000144f724f9c7: vaddsd  xmm0,xmm0,xmm3
  6.05%    0x00000144f724f9cb: vextractf128 xmm2,ymm9,1h
  0.00%    0x00000144f724f9d1: vaddsd  xmm0,xmm0,xmm2
  6.05%    0x00000144f724f9d5: vpshufd xmm3,xmm2,0eh
  0.00%    0x00000144f724f9da: vaddsd  xmm0,xmm0,xmm3    ;*dadd {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.sumproduct.SumProduct::vectorisedDoubleSumProduct@36 (line 44)
                                                         ; - com.openkappa.simd.sumproduct.generated.SumProduct_vectorisedDoubleSumProduct_jmhTest::vectorisedDoubleSumProduct_thrpt_jmhStub@17 (line 119)
  6.05%    0x00000144f724f9de: add     r11d,10h          ;*iinc {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.sumproduct.SumProduct::vectorisedDoubleSumProduct@38 (line 43)
                                                         ; - com.openkappa.simd.sumproduct.generated.SumProduct_vectorisedDoubleSumProduct_jmhTest::vectorisedDoubleSumProduct_thrpt_jmhStub@17 (line 119)
  0.00%    0x00000144f724f9e2: cmp     r11d,r8d
           0x00000144f724f9e5: jl      144f724f910h      ;*if_icmpge {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.sumproduct.SumProduct::vectorisedDoubleSumProduct@10 (line 43)
                                                         ; - com.openkappa.simd.sumproduct.generated.SumProduct_vectorisedDoubleSumProduct_jmhTest::vectorisedDoubleSumProduct_thrpt_jmhStub@17 (line 119)
           0x00000144f724f9eb: mov     edx,r9d
           0x00000144f724f9ee: add     edx,0fffffffdh
           0x00000144f724f9f1: cmp     r9d,edx
           0x00000144f724f9f4: mov     r9d,80000000h
           0x00000144f724f9fa: cmovl   edx,r9d
  0.00%    0x00000144f724f9fe: cmp     r11d,edx
           0x00000144f724fa01: jl      144f724f7a4h
           0x00000144f724fa07: jmp     144f724f7dfh
           0x00000144f724fa0c: vxorpd  xmm0,xmm0,xmm0
           0x00000144f724fa10: jmp     144f724f807h
           0x00000144f724fa15: mov     edx,0ffffff86h
           0x00000144f724fa1a: mov     qword ptr [rsp+70h],rcx
           0x00000144f724fa1f: push    qword ptr [rsp+80h]
           0x00000144f724fa27: pop     qword ptr [rsp+78h]
           0x00000144f724fa2c: push    qword ptr [rsp+30h]
           0x00000144f724fa31: pop     qword ptr [rsp+28h]
....................................................................................................
 99.44%  <total for region 1>
```

Unrolling this <em>will</em> disable autovectorisation, but my Skylake chip can do 8 scalar floating point operations at once. 

```java
  @Benchmark
  public double unrolledDoubleSumProduct() {
    double sp1 = 0D;
    double sp2 = 0D;
    double sp3 = 0D;
    double sp4 = 0D;
    for (int i = 0; i < xd.length && i < yd.length; i += 4) {
      sp1 += xd[i] * yd[i];
      sp2 += xd[i + 1] * yd[i + 1];
      sp3 += xd[i + 2] * yd[i + 2];
      sp4 += xd[i + 3] * yd[i + 3];
    }
    return sp1 + sp2 + sp3 + sp4;
  }
```

Looking at the perfasm output, you can see this code is scalar but the additions are interleaved without interdependencies. This is enough to take down a crippled target. 

```asm
....[Hottest Region 1]..............................................................................
c2, com.openkappa.simd.sumproduct.generated.SumProduct_unrolledDoubleSumProduct_jmhTest::unrolledDoubleSumProduct_thrpt_jmhStub, version 162 (79 bytes) 

                                                         ;   {section_word}
           0x0000024719311ddb: lea     r9,[r12+rcx*8]
           0x0000024719311ddf: lea     rcx,[r12+rbx*8]
           0x0000024719311de3: cmp     r11d,4h
           0x0000024719311de7: jle     24719311ee1h
           0x0000024719311ded: mov     r8d,4h
           0x0000024719311df3: nop     word ptr [rax+rax+0h]
           0x0000024719311dfc: nop                       ;*iload {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.sumproduct.SumProduct::unrolledDoubleSumProduct@23 (line 55)
                                                         ; - com.openkappa.simd.sumproduct.generated.SumProduct_unrolledDoubleSumProduct_jmhTest::unrolledDoubleSumProduct_thrpt_jmhStub@17 (line 119)
  4.20%    0x0000024719311e00: vmovsd  xmm0,qword ptr [rcx+r8*8+28h]
                                                         ;*daload {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.sumproduct.SumProduct::unrolledDoubleSumProduct@116 (line 59)
                                                         ; - com.openkappa.simd.sumproduct.generated.SumProduct_unrolledDoubleSumProduct_jmhTest::unrolledDoubleSumProduct_thrpt_jmhStub@17 (line 119)
  8.93%    0x0000024719311e07: vmulsd  xmm0,xmm0,mmword ptr [r9+r8*8+28h]
 15.10%    0x0000024719311e0e: vmovsd  xmm1,qword ptr [rcx+r8*8+18h]
                                                         ;*daload {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.sumproduct.SumProduct::unrolledDoubleSumProduct@69 (line 57)
                                                         ; - com.openkappa.simd.sumproduct.generated.SumProduct_unrolledDoubleSumProduct_jmhTest::unrolledDoubleSumProduct_thrpt_jmhStub@17 (line 119)
  3.95%    0x0000024719311e15: vmulsd  xmm1,xmm1,mmword ptr [r9+r8*8+18h]
  9.91%    0x0000024719311e1c: vmovsd  xmm2,qword ptr [rcx+r8*8+20h]
                                                         ;*daload {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.sumproduct.SumProduct::unrolledDoubleSumProduct@92 (line 58)
                                                         ; - com.openkappa.simd.sumproduct.generated.SumProduct_unrolledDoubleSumProduct_jmhTest::unrolledDoubleSumProduct_thrpt_jmhStub@17 (line 119)
  3.97%    0x0000024719311e23: vmulsd  xmm2,xmm2,mmword ptr [r9+r8*8+20h]
 11.04%    0x0000024719311e2a: vmovsd  xmm3,qword ptr [rcx+r8*8+10h]
                                                         ;*daload {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.sumproduct.SumProduct::unrolledDoubleSumProduct@47 (line 56)
                                                         ; - com.openkappa.simd.sumproduct.generated.SumProduct_unrolledDoubleSumProduct_jmhTest::unrolledDoubleSumProduct_thrpt_jmhStub@17 (line 119)
  3.86%    0x0000024719311e31: vmulsd  xmm3,xmm3,mmword ptr [r9+r8*8+10h]
  9.04%    0x0000024719311e38: vaddsd  xmm4,xmm4,xmm0    ;*dadd {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.sumproduct.SumProduct::unrolledDoubleSumProduct@118 (line 59)
                                                         ; - com.openkappa.simd.sumproduct.generated.SumProduct_unrolledDoubleSumProduct_jmhTest::unrolledDoubleSumProduct_thrpt_jmhStub@17 (line 119)
  7.11%    0x0000024719311e3c: vaddsd  xmm7,xmm7,xmm3    ;*dadd {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.sumproduct.SumProduct::unrolledDoubleSumProduct@49 (line 56)
                                                         ; - com.openkappa.simd.sumproduct.generated.SumProduct_unrolledDoubleSumProduct_jmhTest::unrolledDoubleSumProduct_thrpt_jmhStub@17 (line 119)
  7.03%    0x0000024719311e40: vaddsd  xmm5,xmm5,xmm2    ;*dadd {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.sumproduct.SumProduct::unrolledDoubleSumProduct@94 (line 58)
                                                         ; - com.openkappa.simd.sumproduct.generated.SumProduct_unrolledDoubleSumProduct_jmhTest::unrolledDoubleSumProduct_thrpt_jmhStub@17 (line 119)
  7.29%    0x0000024719311e44: vaddsd  xmm6,xmm6,xmm1    ;*dadd {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.sumproduct.SumProduct::unrolledDoubleSumProduct@71 (line 57)
                                                         ; - com.openkappa.simd.sumproduct.generated.SumProduct_unrolledDoubleSumProduct_jmhTest::unrolledDoubleSumProduct_thrpt_jmhStub@17 (line 119)
  3.58%    0x0000024719311e48: add     r8d,4h            ;*iinc {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.sumproduct.SumProduct::unrolledDoubleSumProduct@121 (line 55)
                                                         ; - com.openkappa.simd.sumproduct.generated.SumProduct_unrolledDoubleSumProduct_jmhTest::unrolledDoubleSumProduct_thrpt_jmhStub@17 (line 119)
  4.39%    0x0000024719311e4c: cmp     r8d,r11d
  0.00%    0x0000024719311e4f: jl      24719311e00h      ;*if_icmpge {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.sumproduct.SumProduct::unrolledDoubleSumProduct@20 (line 55)
                                                         ; - com.openkappa.simd.sumproduct.generated.SumProduct_unrolledDoubleSumProduct_jmhTest::unrolledDoubleSumProduct_thrpt_jmhStub@17 (line 119)
           0x0000024719311e51: cmp     r8d,edi
           0x0000024719311e54: jnl     24719311c92h
           0x0000024719311e5a: nop                       ;*iload {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.sumproduct.SumProduct::unrolledDoubleSumProduct@23 (line 55)
                                                         ; - com.openkappa.simd.sumproduct.generated.SumProduct_unrolledDoubleSumProduct_jmhTest::unrolledDoubleSumProduct_thrpt_jmhStub@17 (line 119)
           0x0000024719311e5c: cmp     r8d,r10d
           0x0000024719311e5f: jnl     24719311f15h      ;*if_icmpge {reexecute=0 rethrow=0 return_oop=0}
                                                         ; - com.openkappa.simd.sumproduct.SumProduct::unrolledDoubleSumProduct@30 (line 55)
....................................................................................................
 99.39%  <total for region 1>
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
<td>unrolledDoubleSumProduct</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1912.140438</td>
<td align="right">48.445308</td>
<td>ops/ms</td>
<td align="right">1024</td>
</tr>
<tr>
<td>unrolledDoubleSumProduct</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">24.677122</td>
<td align="right">0.510459</td>
<td>ops/ms</td>
<td align="right">65536</td>
</tr>
<tr>
<td>vectorisedDoubleSumProduct</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">647.848021</td>
<td align="right">10.508824</td>
<td>ops/ms</td>
<td align="right">1024</td>
</tr>
<tr>
<td>vectorisedDoubleSumProduct</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">9.474097</td>
<td align="right">0.479281</td>
<td>ops/ms</td>
<td align="right">65536</td>
</tr>
</tbody></table>
</div>

So, if you realise that in <em>your</em> application the order of your array is irrelevant, you can write a tiny bit of extra code and get multiplicatively better performance. These results were produced with JDK9. When I tried with JDK10, the sum product was not vectorised, presumably because it has been noticed that it is unprofitable (edit: I ended up reporting this as a <a href="https://bugs.openjdk.java.net/browse/JDK-8200477" rel="noopener" target="_blank">bug</a>, which was caused by loop strip mining). This benchmark can be seen in full context at <a href="https://github.com/richardstartin/simdbenchmarks/blob/master/src/main/java/com/openkappa/simd/sumproduct/SumProduct.java" rel="noopener" target="_blank">github</a>.

<h3>Vertical Sum</h3>

I was motivated to write this post after <a href="https://twitter.com/iotsakp" rel="noopener" target="_blank">Ioannis Tsakpinis</a> shared a <a href="https://gist.github.com/Spasi/025febb7325b7b73ab2b90f0280796ce" rel="noopener" target="_blank">gist of a benchmark</a> after reading <a href="https://richardstartin.github.io/posts/faster-floating-point-reductions/" rel="noopener" target="_blank">a recent post</a> about coaxing vectorisation into action for a simple floating point sum. The post was intended to be a prelude to a post about the wonders of paginated arrays. With a paginated array, autovectorisation pays off and is preferable to a manual unroll. The non-associativity of the operation is of course still violated, but I am working on the premise that this virtually never matters. I revisited this <a href="https://github.com/richardstartin/simdbenchmarks/blob/master/src/main/java/com/openkappa/simd/reduction/ReduceArray.java" rel="noopener" target="_blank">benchmark</a>, with a paginated array this time.

```java
  @Benchmark // inspired by Ioannis' code
  public double reduceUnrolledPaginated() {
    double a0 = 0.0;
    double a1 = 0.0;
    double a2 = 0.0;
    double a3 = 0.0;
    for (int i = 0; i < paginated.length; ++i) {
      double[] page = paginated[i];
      for (int j = 0; j < paginated[0].length; j += 4) {
        a0 += page[j + 0];
        a1 += page[j + 1];
        a2 += page[j + 2];
        a3 += page[j + 3];
      }
    }
    return a0 + a1 + a2 + a3;
  }

  @Benchmark
  public double reducePaginated() {
    double[] buffer = Arrays.copyOf(paginated[0], paginated[0].length);
    for (int i = 1; i < paginated.length; ++i) {
      double[] page = paginated[i];
      for (int j = 0; j < page.length && j < buffer.length; ++j) {
        buffer[j] += page[j];
      }
    }
    return reduceUnrolled(buffer);
  }
```

The array being paginated, requiring no offset calculations, is the perfect case for a vectorised loop here. Which is one reason why Java arrays should be paginated in application code. 

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
<td>reducePaginated</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">597.046492</td>
<td align="right">23.080803</td>
<td>ops/ms</td>
<td align="right">1024</td>
</tr>
<tr>
<td>reducePaginated</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">42.801021</td>
<td align="right">0.831318</td>
<td>ops/ms</td>
<td align="right">65536</td>
</tr>
<tr>
<td>reducePaginated</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.503510</td>
<td align="right">0.187167</td>
<td>ops/ms</td>
<td align="right">1048576</td>
</tr>
<tr>
<td>reduceUnrolledPaginated</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1311.433592</td>
<td align="right">9.063721</td>
<td>ops/ms</td>
<td align="right">1024</td>
</tr>
<tr>
<td>reduceUnrolledPaginated</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">19.448202</td>
<td align="right">0.503753</td>
<td>ops/ms</td>
<td align="right">65536</td>
</tr>
<tr>
<td>reduceUnrolledPaginated</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.052183</td>
<td align="right">0.086555</td>
<td>ops/ms</td>
<td align="right">1048576</td>
</tr>
</tbody></table>
</div>

Nevertheless, loop unrolling can be a significant boon for floating point arithmetic in Java. It feels dirty to me - it's one of those things that people did before my time. Compilers know how to do it, if they are allowed to do so. If there is no place for `fastfp` in Java, I imagine the practice is here to stay.