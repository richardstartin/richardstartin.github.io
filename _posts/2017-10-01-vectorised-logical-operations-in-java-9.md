---
ID: 9821
title: Vectorised Logical Operations in Java 9
author: Richard Startin
post_excerpt: ""
layout: post
theme: minimal
published: true
date: 2017-10-01 14:31:55
---
This is a short post for my own reference, since I feel I have already done the topic of <em>does Java 9 use AVX for this?</em> to death. Cutting to the chase, Java 9 autovectorises loops to compute logical ANDs, XORs, ORs and ANDNOTs between arrays, making use of the instructions `VPXOR`, `VPOR` and `VPAND`. You can replicate this by running the code at <a href="https://github.com/richardstartin/simdbenchmarks/blob/master/src/main/java/com/openkappa/simd/logical/Logicals.java" rel="noopener" target="_blank">github</a>.

<h3>XOR</h3>

```java
    @Benchmark
    public long[] xor(LongData state) {
        long[] result = new long[state.data1.length];
        long[] data1 = state.data1;
        long[] data2 = state.data2;
        for (int i = 0; i < data1.length && i < data2.length; ++i) {
            result[i] = data1[i] ^ data2[i];
        }
        return result;
    }
```

<pre>
vmovdqu ymm0,ymmword ptr [r10+r13*8+10h]

vpxor   ymm0,ymm0,ymmword ptr [rbx+r13*8+10h]

vmovdqu ymmword ptr [rax+r13*8+10h],ymm0
</pre>

<h3>OR</h3>

```java
    @Benchmark
    public long[] or(LongData state) {
        long[] result = new long[state.data1.length];
        long[] data1 = state.data1;
        long[] data2 = state.data2;
        for (int i = 0; i < data1.length && i < data2.length; ++i) {
            result[i] = data1[i] | data2[i];
        }
        return result;
    }
```

<pre>
vmovdqu ymm0,ymmword ptr [r10+rsi*8+30h]
 
vpor    ymm0,ymm0,ymmword ptr [rbx+rsi*8+30h]

vmovdqu ymmword ptr [rax+rsi*8+30h],ymm0
</pre>

<h3>AND</h3>

```java
    @Benchmark
    public long[] and(LongData state) {
        long[] result = new long[state.data1.length];
        long[] data1 = state.data1;
        long[] data2 = state.data2;
        for (int i = 0; i < data1.length && i < data2.length; ++i) {
            result[i] = data1[i] & data2[i];
        }
        return result;
    }
```

<pre>
vmovdqu ymm0,ymmword ptr [r10+r13*8+10h]

vpand   ymm0,ymm0,ymmword ptr [rbx+r13*8+10h]

vmovdqu ymmword ptr [rax+r13*8+10h],ymm0
</pre>

<h3>ANDNOT</h3>

```java
    @Benchmark
    public long[] andNot(LongData state) {
        long[] result = new long[state.data1.length];
        long[] data1 = state.data1;
        long[] data2 = state.data2;
        for (int i = 0; i < data1.length && i < data2.length; ++i) {
            result[i] = data1[i] & ~data2[i];
        }
        return result;
    }
```

<pre>
vpunpcklqdq xmm0,xmm0,xmm0

vinserti128 ymm0,ymm0,xmm0,1h

vmovdqu ymm1,ymmword ptr [rbx+r13*8+10h]

vpxor   ymm1,ymm1,ymm0

vpand   ymm1,ymm1,ymmword ptr [r10+r13*8+10h]

vmovdqu ymmword ptr [rax+r13*8+10h],ymm1
</pre>