---
ID: 11308
title: Mixing Vector and Scalar Instructions
author: Richard Startin
post_excerpt: ""
layout: post
redirect_from:
  - /mixing-vector-and-scalar-instructions/

published: true
date: 2018-09-23 16:32:22
tags: java vector vector-api
---
I saw an interesting <a href="https://twitter.com/mattjaffee/status/1041802406454067200" rel="noopener" target="_blank">tweet</a> from one of the developers of <a href="https://www.pilosa.com/" rel="noopener" target="_blank">Pilosa</a> this week, reporting performance improvements from unrolling a bitwise reduction in Go. This surprised me because Go seems to enjoy a reputation for being a high performance language, and it certainly has great support for concurrency, but compilers should unroll loops as standard so you don't have to. Having been written in Go doesn't seem to have hampered Pilosa, because they have some great benchmark numbers, and it certainly helps that they built their technology on top of a smart data structure: the roaring bitmap. You can read about their <a href="https://www.pilosa.com/docs/latest/data-model/" rel="noopener" target="_blank">data model</a> for yourself, but Pilosa is basically a large bit matrix which materialises relations between rows and columns by setting the bit at their intersection, for instance, <a href="https://www.pilosa.com/blog/processing-genomes/" rel="noopener" target="_blank">genomes on rows to k-mers</a> (sequences of bases like "GATTACA") on columns. To compute the Hamming similarity between the genomes of two people (i.e. how many k-mers they have in common), Pilosa just needs to intersect the bitmaps of rows representing each genome and count the number of bits in the result. The intersection doesn't even need to be materialised, and can be calculated on the fly as a dot product. What piqued my interest though was that the Pilosa developers had experimented with <a href="https://github.com/pilosa/pilosa/pull/1641/files" rel="noopener" target="_blank">combining vector and scalar instructions</a> and had found it unprofitable. Once there is a Vector API in Java, what will happen when there's a gap that can only be plugged with a scalar implementation? 

I don't know much about Go but I get the impression its compiler is a long way behind C2. The instruction POPCNTQ, the bottleneck in this tale, has only recently been available to Go programmers in <a href="https://golang.org/src/math/bits/bits.go" rel="noopener" target="_blank">math/bits/bits.go</a>, with <a href="https://github.com/golang/go/issues/10757" rel="noopener" target="_blank">demonstrable apathy</a> for its inclusion in the standard library. As a point of comparison, `Long.bitCount` has been translated to POPCNTQ by C2 for longer than I have been using Java. If you want to do bioinformatics in Java, whatever you do, don't unroll your loops! The unrolled version below will be slightly slower than the simple loop.

```java
  @Benchmark
  public int popcnt() {
    int cardinality = 0;
    for (int i = 0; i < size && i < left.length && i < right.length; ++i) {
      cardinality += Long.bitCount(left[i] & right[i]);
    }
    return cardinality;
  }

  @Benchmark
  public int unrolledPopcnt() {
    int cardinality1 = 0;
    int cardinality2 = 0;
    int cardinality3 = 0;
    int cardinality4 = 0;
    for (int i = 0; i < size && i < left.length && i < right.length; i += 4) {
      cardinality1 += Long.bitCount(left[i+0] & right[i+0]);
      cardinality2 += Long.bitCount(left[i+1] & right[i+1]);
      cardinality3 += Long.bitCount(left[i+2] & right[i+2]);
      cardinality4 += Long.bitCount(left[i+3] & right[i+3]);
    }
    return cardinality1 + cardinality2 + cardinality3 + cardinality4;
  }
```

Ignoring the unrolled version because it's a dead end, does C2 vectorise this reduction? No, because it can't vectorise the bit count, but notice the floating point spills at the start for better register placement. 

```asm
         ││ ↗          0x00007fe418240c4c: vmovq  %xmm0,%r9
         ││ │          0x00007fe418240c51: vmovq  %xmm1,%r8
  0.00%  ││ │      ↗   0x00007fe418240c56: vmovq  %r9,%xmm0
  0.04%  ││ │      │   0x00007fe418240c5b: vmovq  %r8,%xmm1                      
  1.71%  ││↗│      │   0x00007fe418240c60: movslq %ecx,%r9
  1.42%  ││││      │   0x00007fe418240c63: mov    0x10(%rbx,%rcx,8),%r10
  8.98%  ││││      │   0x00007fe418240c68: and    0x10(%rdi,%rcx,8),%r10
  3.51%  ││││      │   0x00007fe418240c6d: popcnt %r10,%r8
  3.21%  ││││      │   0x00007fe418240c72: add    %r8d,%edx
  2.48%  ││││      │   0x00007fe418240c75: mov    0x28(%rbx,%r9,8),%r10
  8.19%  ││││      │   0x00007fe418240c7a: and    0x28(%rdi,%r9,8),%r10
  3.59%  ││││      │   0x00007fe418240c7f: popcnt %r10,%r10
  3.73%  ││││      │   0x00007fe418240c84: mov    0x20(%rbx,%r9,8),%r8
  2.16%  ││││      │   0x00007fe418240c89: and    0x20(%rdi,%r9,8),%r8
  7.53%  ││││      │   0x00007fe418240c8e: popcnt %r8,%rsi
  6.21%  ││││      │   0x00007fe418240c93: mov    0x18(%rbx,%r9,8),%r8           
  2.30%  ││││      │   0x00007fe418240c98: and    0x18(%rdi,%r9,8),%r8
  2.07%  ││││      │   0x00007fe418240c9d: popcnt %r8,%r9
 12.75%  ││││      │   0x00007fe418240ca2: add    %r9d,%edx
  6.01%  ││││      │   0x00007fe418240ca5: add    %esi,%edx
  5.70%  ││││      │   0x00007fe418240ca7: add    %r10d,%edx                     
  8.60%  ││││      │   0x00007fe418240caa: add    $0x4,%ecx                      
  3.58%  ││││      │   0x00007fe418240cad: cmp    %r11d,%ecx
         ││╰│      │   0x00007fe418240cb0: jl     0x00007fe418240c60             
  0.04%  ││ │      │   0x00007fe418240cb2: mov    0x108(%r15),%r10               
  0.05%  ││ │      │   0x00007fe418240cb9: test   %eax,(%r10)                    
  0.29%  ││ │      │   0x00007fe418240cbc: cmp    %r11d,%ecx
         ││ ╰      │   0x00007fe418240cbf: jl     0x00007fe418240c4c
```

It's nice that very good scalar code gets generated for this loop from the simplest possible code, but what if you want to go faster with vectorisation? There is no vector bit count until the VPOPCNTD/VPOPCNTQ AVX512 extension, currently only available on the Knights Mill processor, which is tantamount to there being no vector bit count instruction. There is a vector bit count algorithm originally written by Wojciech Mula for <a href="http://0x80.pl/articles/sse-popcount.html" rel="noopener" target="_blank">SSE3</a>, and updated for <a href="https://arxiv.org/pdf/1611.07612.pdf" rel="noopener" target="_blank">AVX2</a> by Wojciech Mula and Daniel Lemire, which is used in clang. I made an attempt at implementing this using the Vector API a few months ago and found what felt were a <a href="http://mail.openjdk.java.net/pipermail/panama-dev/2018-May/001940.html" rel="noopener" target="_blank">few gaps</a> but may look at this again soon. 

I looked at a few ways of writing mixed loops, using the Vector API and `Long.bitCount` and found that there wasn't much to be gained from partial vectorisation. There is a method for extracting scalar values from vectors: `LongVector::get`, which is very interesting because it highlights the gaps the JIT compiler needs to fill in on the wrong hardware, and why you should read the assembly code emitted from a benchmark before jumping to conclusions. Here's the code and below it the hot part of the loop.

```java
  @Benchmark
  public int vpandExtractPopcnt() {
    int cardinality = 0;
    for (int i = 0; i < size && i < left.length && i < right.length; i += 4) {
      var intersection = YMM_LONG.fromArray(left, i).and(YMM_LONG.fromArray(right, i));
      cardinality += Long.bitCount(intersection.get(0));
      cardinality += Long.bitCount(intersection.get(1));
      cardinality += Long.bitCount(intersection.get(2));
      cardinality += Long.bitCount(intersection.get(3));
    }
    return cardinality;
  }
```

```asm
  0.43%  ││        ↗   0x00007fbfe024bb55: vmovdqu 0x10(%rax,%rcx,8),%ymm2
  2.58%  ││        │   0x00007fbfe024bb5b: vpand  0x10(%r13,%rcx,8),%ymm2,%ymm8 
  0.32%  ││        │   0x00007fbfe024bb62: movslq %ecx,%r10                     
  0.43%  ││        │   0x00007fbfe024bb65: vmovdqu 0x70(%rax,%r10,8),%ymm2       
  2.65%  ││        │   0x00007fbfe024bb6c: vpand  0x70(%r13,%r10,8),%ymm2,%ymm9  
  0.84%  ││        │   0x00007fbfe024bb73: vmovdqu 0x30(%rax,%r10,8),%ymm2
  0.46%  ││        │   0x00007fbfe024bb7a: vpand  0x30(%r13,%r10,8),%ymm2,%ymm10  
  3.06%  ││        │   0x00007fbfe024bb81: vmovdqu 0x50(%rax,%r10,8),%ymm6       
  0.03%  ││        │   0x00007fbfe024bb88: vmovq  %rax,%xmm2
  0.42%  ││        │   0x00007fbfe024bb8d: vpand  0x50(%r13,%r10,8),%ymm6,%ymm11
  2.60%  ││        │   0x00007fbfe024bb94: vmovq  %xmm8,%r10
  0.01%  ││        │   0x00007fbfe024bb99: popcnt %r10,%rbp
  0.51%  ││        │   0x00007fbfe024bb9e: add    %edx,%ebp
  3.86%  ││        │   0x00007fbfe024bba0: vmovq  %xmm10,%r10
  0.15%  ││        │   0x00007fbfe024bba5: popcnt %r10,%rax
  0.43%  ││        │   0x00007fbfe024bbaa: vmovq  %xmm11,%r10
  0.41%  ││        │   0x00007fbfe024bbaf: popcnt %r10,%r14
  2.84%  ││        │   0x00007fbfe024bbb4: vmovq  %xmm9,%r10
  0.18%  ││        │   0x00007fbfe024bbb9: popcnt %r10,%rdx
  0.35%  ││        │   0x00007fbfe024bbbe: vextracti128 $0x1,%ymm9,%xmm6
  0.41%  ││        │   0x00007fbfe024bbc4: vpextrq $0x0,%xmm6,%r10
  2.62%  ││        │   0x00007fbfe024bbca: popcnt %r10,%r10
  1.45%  ││        │   0x00007fbfe024bbcf: vextracti128 $0x1,%ymm9,%xmm6
  0.42%  ││        │   0x00007fbfe024bbd5: vpextrq $0x1,%xmm6,%r11
  2.20%  ││        │   0x00007fbfe024bbdb: popcnt %r11,%r8
  1.34%  ││        │   0x00007fbfe024bbe0: vpextrq $0x1,%xmm9,%r11
  2.44%  ││        │   0x00007fbfe024bbe6: popcnt %r11,%r11
  0.21%  ││        │   0x00007fbfe024bbeb: vpextrq $0x1,%xmm10,%r9
  0.97%  ││        │   0x00007fbfe024bbf1: popcnt %r9,%r9
  2.17%  ││        │   0x00007fbfe024bbf6: vextracti128 $0x1,%ymm8,%xmm6
  0.22%  ││        │   0x00007fbfe024bbfc: vpextrq $0x1,%xmm6,%rbx
  1.10%  ││        │   0x00007fbfe024bc02: popcnt %rbx,%rbx
  2.46%  ││        │   0x00007fbfe024bc07: vextracti128 $0x1,%ymm8,%xmm6
  0.22%  ││        │   0x00007fbfe024bc0d: vpextrq $0x0,%xmm6,%rdi
  1.00%  ││        │   0x00007fbfe024bc13: popcnt %rdi,%rsi
  2.64%  ││        │   0x00007fbfe024bc18: vpextrq $0x1,%xmm8,%rdi
  0.80%  ││        │   0x00007fbfe024bc1e: popcnt %rdi,%rdi
  0.35%  ││        │   0x00007fbfe024bc23: add    %edi,%ebp
  3.42%  ││        │   0x00007fbfe024bc25: add    %esi,%ebp
  0.38%  ││        │   0x00007fbfe024bc27: add    %ebx,%ebp
  0.70%  ││        │   0x00007fbfe024bc29: add    %ebp,%eax
  0.84%  ││        │   0x00007fbfe024bc2b: add    %r9d,%eax
  2.85%  ││        │   0x00007fbfe024bc2e: vpextrq $0x1,%xmm11,%r9
  0.35%  ││        │   0x00007fbfe024bc34: popcnt %r9,%rbx
  0.21%  ││        │   0x00007fbfe024bc39: vextracti128 $0x1,%ymm10,%xmm6
  2.82%  ││        │   0x00007fbfe024bc3f: vpextrq $0x1,%xmm6,%r9
  0.34%  ││        │   0x00007fbfe024bc45: popcnt %r9,%r9
  0.38%  ││        │   0x00007fbfe024bc4a: vextracti128 $0x1,%ymm10,%xmm6
  2.58%  ││        │   0x00007fbfe024bc50: vpextrq $0x0,%xmm6,%rdi
  0.42%  ││        │   0x00007fbfe024bc56: popcnt %rdi,%rsi
  0.56%  ││        │   0x00007fbfe024bc5b: add    %esi,%eax
  4.90%  ││        │   0x00007fbfe024bc5d: add    %r9d,%eax
  0.55%  ││        │   0x00007fbfe024bc60: add    %eax,%r14d
  0.87%  ││        │   0x00007fbfe024bc63: add    %ebx,%r14d
  1.46%  ││        │   0x00007fbfe024bc66: vextracti128 $0x1,%ymm11,%xmm6
  1.91%  ││        │   0x00007fbfe024bc6c: vpextrq $0x0,%xmm6,%r9
  0.12%  ││        │   0x00007fbfe024bc72: popcnt %r9,%r9
  1.33%  ││        │   0x00007fbfe024bc77: add    %r9d,%r14d
  2.20%  ││        │   0x00007fbfe024bc7a: vextracti128 $0x1,%ymm11,%xmm6
  0.08%  ││        │   0x00007fbfe024bc80: vpextrq $0x1,%xmm6,%r9
  2.51%  ││        │   0x00007fbfe024bc86: popcnt %r9,%rbx
  3.68%  ││        │   0x00007fbfe024bc8b: add    %ebx,%r14d
  0.45%  ││        │   0x00007fbfe024bc8e: add    %r14d,%edx
  1.69%  ││        │   0x00007fbfe024bc91: add    %r11d,%edx
  1.34%  ││        │   0x00007fbfe024bc94: add    %r10d,%edx
  3.71%  ││        │   0x00007fbfe024bc97: add    %r8d,%edx
  4.53%  ││        │   0x00007fbfe024bc9a: add    $0x10,%ecx
```

What's going on here is that each 256 bit vector is first extracted to a 128 bit register, so a 64 bit word can be moved to a 64 bit register upon which POPCNTQ can operate. This doesn't benchmark very well at all on my AVX2 capable laptop, but my laptop is a poor proxy for the kind of AVX512 capable processor bioinformatics workloads would expect to run on. 

I found a slight improvement on the scalar loop by dumping the intersected vectors to a pre-allocated array, and manually unrolling the bit counts with three accumulators, because the latency of POPCNTQ is three times that of ADD. The unrolled version is roughly 20% faster than the scalar loop, but this isn't the kind of gain usually expected from vectorisation.

```java
  @Benchmark
  public int vpandStorePopcnt() {
    long[] intersections = buffer;
    int cardinality = 0;
    for (int i = 0; i < size && i < left.length && i < right.length; i += 4) {
      YMM_LONG.fromArray(left, i).and(YMM_LONG.fromArray(right, i)).intoArray(intersections, 0);
      cardinality += Long.bitCount(intersections[0]);
      cardinality += Long.bitCount(intersections[1]);
      cardinality += Long.bitCount(intersections[2]);
      cardinality += Long.bitCount(intersections[3]);
    }
    return cardinality;
  }

  @Benchmark
  public int vpandStorePopcntUnrolled() {
    long[] intersections = buffer;
    int cardinality1 = 0;
    int cardinality2 = 0;
    int cardinality3 = 0;
    for (int i = 0; i < size && i < left.length && i < right.length; i += 8) {
      YMM_LONG.fromArray(left, i).and(YMM_LONG.fromArray(right, i)).intoArray(intersections, 0);
      YMM_LONG.fromArray(left, i + 4).and(YMM_LONG.fromArray(right, i + 4)).intoArray(intersections, 4);
      cardinality1 += Long.bitCount(intersections[0]);
      cardinality2 += Long.bitCount(intersections[1]);
      cardinality3 += Long.bitCount(intersections[2]);
      cardinality1 += Long.bitCount(intersections[3]);
      cardinality2 += Long.bitCount(intersections[4]);
      cardinality3 += Long.bitCount(intersections[5]);
      cardinality1 += Long.bitCount(intersections[6]);
      cardinality2 += Long.bitCount(intersections[7]);
    }
    return cardinality1 + cardinality2 + cardinality3;
  }
```

Here the pairs of extracts are replaced with a store to the buffer.

```asm
  0.03%        ││ ││││  0x00007f6d50031358: vmovdqu 0x10(%rax,%r9,8),%ymm2
  0.02%        ││ ││││  0x00007f6d5003135f: vpand  0x10(%r13,%r9,8),%ymm2,%ymm2   
  0.06%        ││ ││││  0x00007f6d50031366: vmovdqu %ymm2,0x10(%r12,%rcx,8)      
  0.03%        ││ ││││  0x00007f6d5003136d: mov    %r9d,%edi
  0.00%        ││ ││││  0x00007f6d50031370: add    $0x4,%edi                      
  0.00%        ││ ││││  0x00007f6d50031373: movslq %edi,%rbx                      
  0.03%        ││ ││││  0x00007f6d50031376: vmovdqu 0x10(%rax,%rbx,8),%ymm2
  0.00%        ││ ││││  0x00007f6d5003137c: vpand  0x10(%r13,%rbx,8),%ymm2,%ymm2  
  0.10%        ││ ││││  0x00007f6d50031383: vmovdqu %ymm2,0x30(%r12,%rcx,8)      
  0.02%        ││ ││││  0x00007f6d5003138a: popcnt 0x28(%r12,%rcx,8),%rdi
  0.03%        ││ ││││  0x00007f6d50031391: popcnt 0x20(%r12,%rcx,8),%rdx
  0.04%        ││ ││││  0x00007f6d50031398: add    %r8d,%edx
  0.02%        ││ ││││  0x00007f6d5003139b: popcnt 0x38(%r12,%rcx,8),%r8
  0.22%        ││ ││││  0x00007f6d500313a2: add    %edx,%r8d
  0.08%        ││ ││││  0x00007f6d500313a5: popcnt 0x30(%r12,%rcx,8),%rdx
  0.03%        ││ ││││  0x00007f6d500313ac: popcnt 0x18(%r12,%rcx,8),%rbx
               ││ ││││  0x00007f6d500313b3: add    %r11d,%ebx
  0.04%        ││ ││││  0x00007f6d500313b6: add    %edx,%ebx
  0.15%        ││ ││││  0x00007f6d500313b8: popcnt 0x48(%r12,%rcx,8),%r11
               ││ ││││  0x00007f6d500313bf: add    %ebx,%r11d
  0.04%        ││ ││││  0x00007f6d500313c2: popcnt 0x40(%r12,%rcx,8),%rdx
  0.03%        ││ ││││  0x00007f6d500313c9: popcnt 0x10(%r12,%rcx,8),%rbx
  0.10%        ││ ││││  0x00007f6d500313d0: add    %esi,%ebx
  0.06%        ││ ││││  0x00007f6d500313d2: add    %ebx,%edi
  0.03%        ││ ││││  0x00007f6d500313d4: add    %edx,%edi
```

Here are all the results in summary:

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<tbody><tr>
<th>Benchmark</th>
<th>Mode</th>
<th>Threads</th>
<th>Samples</th>
<th>Score</th>
<th>Score Error (99.9%)</th>
<th>Unit</th>
<th>Param: size</th>
</tr>
<tr>
<td>popcnt</td>
<td>thrpt</td>
<td>1</td>
<td>20</td>
<td>2098.750355</td>
<td>12.877810</td>
<td>ops/ms</td>
<td>1024</td>
</tr>
<tr>
<td>unrolledPopcnt</td>
<td>thrpt</td>
<td>1</td>
<td>20</td>
<td>2077.227092</td>
<td>29.230757</td>
<td>ops/ms</td>
<td>1024</td>
</tr>
<tr>
<td>vpandExtractPopcnt</td>
<td>thrpt</td>
<td>1</td>
<td>20</td>
<td>1819.027524</td>
<td>12.728300</td>
<td>ops/ms</td>
<td>1024</td>
</tr>
<tr>
<td>vpandStorePopcnt</td>
<td>thrpt</td>
<td>1</td>
<td>20</td>
<td>2372.775743</td>
<td>10.315422</td>
<td>ops/ms</td>
<td>1024</td>
</tr>
<tr>
<td>vpandStorePopcntUnrolled</td>
<td>thrpt</td>
<td>1</td>
<td>20</td>
<td>2626.761626</td>
<td>26.099143</td>
<td>ops/ms</td>
<td>1024</td>
</tr>
</tbody></table>
</div>

The difference is probably attributable to a smaller number of instructions:

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<tbody><tr>
<th>Benchmark</th>
<th>Mode</th>
<th>Threads</th>
<th>Samples</th>
<th>Score</th>
<th>Score Error (99.9%)</th>
<th>Unit</th>
<th>Param: size</th>
</tr>
<tr>
<td>popcnt:instructions</td>
<td>thrpt</td>
<td>1</td>
<td>1</td>
<td>5241.243387</td>
<td>NaN</td>
<td>#/op</td>
<td>1024</td>
</tr>
<tr>
<td>unrolledPopcnt:instructions</td>
<td>thrpt</td>
<td>1</td>
<td>1</td>
<td>5203.655274</td>
<td>NaN</td>
<td>#/op</td>
<td>1024</td>
</tr>
<tr>
<td>vpandExtractPopcnt:instructions</td>
<td>thrpt</td>
<td>1</td>
<td>1</td>
<td>4579.851499</td>
<td>NaN</td>
<td>#/op</td>
<td>1024</td>
</tr>
<tr>
<td>vpandStorePopcnt:instructions</td>
<td>thrpt</td>
<td>1</td>
<td>1</td>
<td>3170.924853</td>
<td>NaN</td>
<td>#/op</td>
<td>1024</td>
</tr>
<tr>
<td>vpandStorePopcntUnrolled:instructions</td>
<td>thrpt</td>
<td>1</td>
<td>1</td>
<td>3528.127055</td>
<td>NaN</td>
<td>#/op</td>
<td>1024</td>
</tr>
</tbody></table>
</div>

In total, the gains aren't great, but the baseline is strong. There's more to counting bits than computing the Hamming similarity between two bitmaps; various useful similarity metrics, such as Jaccard and Tanimoto, can be calculated in the same way by replacing intersection with other set relations already implemented in the Vector API. 


<blockquote><a href="https://github.com/richardstartin/vectorbenchmarks/blob/master/src/main/java/com/openkappa/panama/vectorbenchmarks/IntersectionCardinality.java" rel="noopener" target="_blank">Benchmarks</a></blockquote>
