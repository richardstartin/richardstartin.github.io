---
title: Performance Myths and Continuous Profiling
layout: post
tags: java
date: 2021-12-27
image: /assets/2021/12/perf-myths-and-continuous-profiling/Ardre_Odin_Sleipnir.png
---

My [last post](/posts/5-java-mundane-performance-tricks) was about five very simple things you can do to avoid Java programs from being slower than they need to be.
The reception to this post was mixed.
Some readers agreed that the problems mentioned in the post were indeed very common, while others suggested more common inefficient patterns to avoid.
For example, I could have suggested to precompile regular expressions, or not to program by exception, or to avoid `String.format`, but I felt this was all well covered already.
The aim of the post was to help Java programmers to program defensively for efficiency - just as many do for correctness - by giving an idea of what some common things cost.
However, several readers dismissed the content of the post as premature optimisation.

It's interesting how negative responses to posts about minor software efficiencies can be.
There will be various causes for this reaction, but a common theme is the existence of performance myths perpetuated by bad blog posts.
I certainly hope that I'm not perpetuating performance myths but this position is understandable.

Performance myths can be split into two categories, and I'll give an example of each:

* Those that were never true
* Those that used to be true 

I think it's the second category which cause the strongest reactions because they counteract future improvements.
In this post I take a look at examples of both before discussing continuous profiling since the items I chose were based on things I've seen show up in profiles a lot.

1. TOC
{:toc}

### Never true: prefer pre-increment to post-increment for loop induction variables 

I have encountered claims that loops which use pre-increment for loop induction variables are faster than those which use post-increment.
So:

```java
for (int i = 0; i < size; i++) {
   doIt();  
}
```

would be slightly slower than:

```java
for (int i = 0; i < size; ++i) {
   doIt();  
}
```

Even if this were true, the loop body would dominate the cost of control flow in most cases.
It's worth looking at the origin of the myth and the reasoning behind it though.
The myth comes from C++, where it's possible to overload increment operators.
As you are probably aware, post-increment yields the value before performing the increment.
This may lead to copying the value, so unless the compiler eliminates the copy because it's not observable, pre-increment would have an advantage.
I'm not going to dig in to how often or when this is true in C++ because it has no relevance to programs written in Java.

Since the JIT compiler optimises loops, it's very unlikely that it will generate code corresponding to either  `i++` or `++i`.
This can be seen by analysing a simple benchmark:

```java
@State(Scope.Benchmark)
public class Increments {

  @Param("1024")
  int size;

  private int[] input;
  private int[] output;

  @Setup(Level.Trial)
  public void setup() {
    input = ThreadLocalRandom.current().ints(size).toArray();
    output = new int[size];
  }

  @Benchmark
  public void autovecPre(Blackhole bh) {
    for (int i = 0; i < input.length; ++i) {
      output[i] += input[i];
    }
    bh.consume(output);
  }

  @Benchmark
  public void autovecPost(Blackhole bh) {
    for (int i = 0; i < input.length; i++) {
      output[i] += input[i];
    }
    bh.consume(output);
  }

  @Benchmark
  public int reducePre(Blackhole bh) {
    int sum = 0;
    for (int i = 0; i < input.length; ++i) {
      sum += Integer.bitCount(input[i]);
    }
    return sum;
  }

  @Benchmark
  public int reducePost(Blackhole bh) {
    int sum = 0;
    for (int i = 0; i < input.length; i++) {
      sum += Integer.bitCount(input[i]);
    }
    return sum;
  }

  @Benchmark
  public void blackholedPre(Blackhole bh) {
    for (int i = 0; i < input.length; ++i) {
      bh.consume(i);
    }
  }

  @Benchmark
  public void blackholedPost(Blackhole bh) {
    for (int i = 0; i < input.length; i++) {
      bh.consume(i);
    }
  }
}
```

The benchmark consists of a pre- and post-increment version of three loops selected carefully.
Loops `autovecPre` and `autovecPost` can be autovectorised. 
Loops `reducePre` and `reducePost` can't be autovectorised (because the operation in the loop body can't, but fortunately this will no longer be the case on some hardware, see [JDK-8278868](https://github.com/openjdk/jdk/pull/6857)) but can be unrolled.
Using `Blackhold::consume` prevents loop unrolling, so different code will be generated in `blackholedPre` and `blackholedPost` than in the other loops.

Firstly, there is no difference in the scores for these benchmarks (`pre` is _slower_ once but it's just noise):

``` 
Benchmark                  (size)  Mode  Cnt     Score   Error  Units
Increments.autovecPost       1024  avgt    5   156.744 ± 0.416  ns/op
Increments.autovecPre        1024  avgt    5   158.390 ± 0.096  ns/op
Increments.blackholedPost    1024  avgt    5  2798.470 ± 2.657  ns/op
Increments.blackholedPre     1024  avgt    5  2798.259 ± 2.553  ns/op
Increments.reducePost        1024  avgt    5   456.012 ± 0.267  ns/op
Increments.reducePre         1024  avgt    5   455.922 ± 0.299  ns/op
```

This is because the loops are JIT-compiled exactly the same way.

Here's `autovecPre` and `autovecPost`, where `i` is incremented by 64 at a time: `add $0x40,%edx`.

```asm
....[Hottest Region 1]..............................................................................
c2, level 4, inc.generated.Increments_autovecPost_jmhTest::autovecPost_avgt_jmhStub, version 472 (464 bytes) 

                       0x00007fd6f435aff4: vzeroupper 
                       0x00007fd6f435aff7: add    $0x30,%rsp
                       0x00007fd6f435affb: pop    %rbp
                       0x00007fd6f435affc: mov    0x108(%r15),%r10
                       0x00007fd6f435b003: test   %eax,(%r10)        
                       0x00007fd6f435b006: retq   
                       0x00007fd6f435b007: nop                       
                                                                     
                                                                     
         ↗         ↗   0x00007fd6f435b008: vmovdqu 0x10(%r8,%rdx,4),%ymm0
  0.73%  │         │   0x00007fd6f435b00f: vpaddd 0x10(%r10,%rdx,4),%ymm0,%ymm0
  0.75%  │         │   0x00007fd6f435b016: vmovdqu %ymm0,0x10(%r8,%rdx,4)
         │         │                                                 
         │         │                                                 
         │         │   0x00007fd6f435b01d: add    $0x8,%edx          
         │         │                                                 
         │         │                                                 
  0.66%  │         │   0x00007fd6f435b020: cmp    %r9d,%edx
         ╰         │   0x00007fd6f435b023: jl     0x00007fd6f435b008 
                   │                                                 
                   │                                                 
                 ↗ │↗  0x00007fd6f435b025: cmp    %r11d,%edx
          ╭      │ ││  0x00007fd6f435b028: jge    0x00007fd6f435b03d
  0.02%   │      │ ││  0x00007fd6f435b02a: xchg   %ax,%ax            
          │      │ ││                                                
          │      │ ││                                                
          │↗     │ ││  0x00007fd6f435b02c: mov    0x10(%r10,%rdx,4),%ebx
  0.54%   ││     │ ││  0x00007fd6f435b031: add    %ebx,0x10(%r8,%rdx,4)
          ││     │ ││                                                
          ││     │ ││                                                
  0.58%   ││     │ ││  0x00007fd6f435b036: inc    %edx               
          ││     │ ││                                                
          ││     │ ││                                                
  0.54%   ││     │ ││  0x00007fd6f435b038: cmp    %r11d,%edx
          │╰     │ ││  0x00007fd6f435b03b: jl     0x00007fd6f435b02c 
          │      │ ││                                                
          │      │ ││                                                
          ↘ ↗    │ ││  0x00007fd6f435b03d: mov    %rcx,%rdx
  0.23%     │    │ ││  0x00007fd6f435b040: shl    $0x3,%rdx          
            │    │ ││                                                
            │    │ ││                                                
            │    │ ││  0x00007fd6f435b044: mov    0x10(%rsp),%rsi
  0.10%     │    │ ││  0x00007fd6f435b049: data16 xchg %ax,%ax
            │    │ ││  0x00007fd6f435b04c: vzeroupper 
  0.29%     │    │ ││  0x00007fd6f435b04f: callq  0x00007fd6ec89cb00 
            │    │ ││                                                
            │    │ ││                                                
            │    │ ││                                                
            │    │ ││                                                
            │    │ ││  0x00007fd6f435b054: mov    0x40(%rsp),%r10
  0.17%     │    │ ││  0x00007fd6f435b059: movzbl 0x94(%r10),%r10d   
            │    │ ││                                                
            │    │ ││                                                
  0.10%     │    │ ││  0x00007fd6f435b061: mov    0x108(%r15),%r11
            │    │ ││  0x00007fd6f435b068: add    $0x1,%rbp          
            │    │ ││                                                
            │    │ ││                                                
  0.08%     │    │ ││  0x00007fd6f435b06c: test   %eax,(%r11)        
            │    │ ││  0x00007fd6f435b06f: test   %r10d,%r10d
            │    │ ││  0x00007fd6f435b072: jne    0x00007fd6f435afcf 
            │    │ ││                                                
  0.02%     │    │ ││  0x00007fd6f435b078: mov    0x50(%rsp),%r10
            │    │ ││  0x00007fd6f435b07d: mov    0x10(%r10),%r10d   
            │    │ ││                                                
            │    │ ││                                                
  0.12%     │    │ ││  0x00007fd6f435b081: mov    0xc(%r12,%r10,8),%r11d  
            │    │ ││                                                
            │    │ ││                                                
            │    │ ││                                                
            │    │ ││  0x00007fd6f435b086: mov    0x50(%rsp),%r8
  0.06%     │    │ ││  0x00007fd6f435b08b: mov    0x14(%r8),%ecx     
            │    │ ││                                                
            │    │ ││                                                
            │    │ ││  0x00007fd6f435b08f: test   %r11d,%r11d
            ╰    │ ││  0x00007fd6f435b092: jbe    0x00007fd6f435b03d  
                 │ ││                                                
                 │ ││                                                
  0.23%          │ ││  0x00007fd6f435b094: mov    0xc(%r12,%rcx,8),%r8d  
                 │ ││                                                
                 │ ││                                                
                 │ ││                                                
                 │ ││  0x00007fd6f435b099: test   %r8d,%r8d
             ╭   │ ││  0x00007fd6f435b09c: jbe    0x00007fd6f435b1ed
  0.08%      │   │ ││  0x00007fd6f435b0a2: mov    %r11d,%r9d
             │   │ ││  0x00007fd6f435b0a5: dec    %r9d
  0.17%      │   │ ││  0x00007fd6f435b0a8: cmp    %r8d,%r9d
             │╭  │ ││  0x00007fd6f435b0ab: jae    0x00007fd6f435b1ed
             ││  │ ││  0x00007fd6f435b0b1: cmp    %r11d,%r9d
             ││╭ │ ││  0x00007fd6f435b0b4: jae    0x00007fd6f435b1ed
  0.08%      │││ │ ││  0x00007fd6f435b0ba: shl    $0x3,%r10
             │││ │ ││  0x00007fd6f435b0be: lea    (%r12,%rcx,8),%r8
  0.19%      │││ │ ││  0x00007fd6f435b0c2: mov    %r8d,%r9d
             │││ │ ││  0x00007fd6f435b0c5: shr    $0x2,%r9d
  0.06%      │││ │ ││  0x00007fd6f435b0c9: and    $0x7,%r9d
             │││ │ ││  0x00007fd6f435b0cd: mov    $0x3,%ebx
  0.19%      │││ │ ││  0x00007fd6f435b0d2: sub    %r9d,%ebx
             │││ │ ││  0x00007fd6f435b0d5: and    $0x7,%ebx
  0.06%      │││ │ ││  0x00007fd6f435b0d8: inc    %ebx
             │││ │ ││  0x00007fd6f435b0da: cmp    %r11d,%ebx
  0.08%      │││ │ ││  0x00007fd6f435b0dd: cmovg  %r11d,%ebx
             │││ │ ││  0x00007fd6f435b0e1: xor    %edx,%edx          
             │││ │ ││                                                
             │││ │ ││                                                
  0.48%      │││↗│ ││  0x00007fd6f435b0e3: mov    0x10(%r10,%rdx,4),%edi
             │││││ ││  0x00007fd6f435b0e8: add    %edi,0x10(%r8,%rdx,4)  
             │││││ ││                                                
             │││││ ││                                                
  0.95%      │││││ ││  0x00007fd6f435b0ed: inc    %edx               
             │││││ ││                                                
             │││││ ││                                                
             │││││ ││  0x00007fd6f435b0ef: cmp    %ebx,%edx
             │││╰│ ││  0x00007fd6f435b0f1: jl     0x00007fd6f435b0e3  
             │││ │ ││                                                
             │││ │ ││                                                
  0.02%      │││ │ ││  0x00007fd6f435b0f3: mov    %r11d,%ebx
             │││ │ ││  0x00007fd6f435b0f6: add    $0xffffffc1,%ebx
  0.21%      │││ │ ││  0x00007fd6f435b0f9: cmp    %ebx,%edx
             │││ ╰ ││  0x00007fd6f435b0fb: jge    0x00007fd6f435b025  
             │││   ││                                                
             │││   ││                                                
  2.90%      │││  ↗││  0x00007fd6f435b101: vmovdqu 0x10(%r8,%rdx,4),%ymm0
  0.04%      │││  │││  0x00007fd6f435b108: vpaddd 0x10(%r10,%rdx,4),%ymm0,%ymm0
 10.08%      │││  │││  0x00007fd6f435b10f: vmovdqu %ymm0,0x10(%r8,%rdx,4)
  1.00%      │││  │││  0x00007fd6f435b116: vmovdqu 0x30(%r8,%rdx,4),%ymm0
             │││  │││  0x00007fd6f435b11d: vpaddd 0x30(%r10,%rdx,4),%ymm0,%ymm0
  9.27%      │││  │││  0x00007fd6f435b124: vmovdqu %ymm0,0x30(%r8,%rdx,4)
  0.79%      │││  │││  0x00007fd6f435b12b: vmovdqu 0x50(%r8,%rdx,4),%ymm0
             │││  │││  0x00007fd6f435b132: vpaddd 0x50(%r10,%rdx,4),%ymm0,%ymm0
  8.07%      │││  │││  0x00007fd6f435b139: vmovdqu %ymm0,0x50(%r8,%rdx,4)
  0.89%      │││  │││  0x00007fd6f435b140: vmovdqu 0x70(%r8,%rdx,4),%ymm0
             │││  │││  0x00007fd6f435b147: vpaddd 0x70(%r10,%rdx,4),%ymm0,%ymm0
  9.58%      │││  │││  0x00007fd6f435b14e: vmovdqu %ymm0,0x70(%r8,%rdx,4)
  0.52%      │││  │││  0x00007fd6f435b155: vmovdqu 0x90(%r8,%rdx,4),%ymm0
             │││  │││  0x00007fd6f435b15f: vpaddd 0x90(%r10,%rdx,4),%ymm0,%ymm0
  8.34%      │││  │││  0x00007fd6f435b169: vmovdqu %ymm0,0x90(%r8,%rdx,4)
  0.64%      │││  │││  0x00007fd6f435b173: vmovdqu 0xb0(%r8,%rdx,4),%ymm0
             │││  │││  0x00007fd6f435b17d: vpaddd 0xb0(%r10,%rdx,4),%ymm0,%ymm0
  9.71%      │││  │││  0x00007fd6f435b187: vmovdqu %ymm0,0xb0(%r8,%rdx,4)
  0.58%      │││  │││  0x00007fd6f435b191: vmovdqu 0xd0(%r8,%rdx,4),%ymm0
             │││  │││  0x00007fd6f435b19b: vpaddd 0xd0(%r10,%rdx,4),%ymm0,%ymm0
 14.68%      │││  │││  0x00007fd6f435b1a5: vmovdqu %ymm0,0xd0(%r8,%rdx,4)
  0.54%      │││  │││  0x00007fd6f435b1af: vmovdqu 0xf0(%r8,%rdx,4),%ymm0
             │││  │││  0x00007fd6f435b1b9: vpaddd 0xf0(%r10,%rdx,4),%ymm0,%ymm0
  9.46%      │││  │││  0x00007fd6f435b1c3: vmovdqu %ymm0,0xf0(%r8,%rdx,4)  
             │││  │││                                                
             │││  │││                                                
  0.52%      │││  │││  0x00007fd6f435b1cd: add    $0x40,%edx         
             │││  │││                                                
             │││  │││                                                
             │││  │││  0x00007fd6f435b1d0: cmp    %ebx,%edx
             │││  ╰││  0x00007fd6f435b1d2: jl     0x00007fd6f435b101
  0.23%      │││   ││  0x00007fd6f435b1d8: mov    %r11d,%r9d
             │││   ││  0x00007fd6f435b1db: add    $0xfffffff9,%r9d
  0.10%      │││   ││  0x00007fd6f435b1df: cmp    %r9d,%edx
             │││   ╰│  0x00007fd6f435b1e2: jl     0x00007fd6f435b008
             │││    ╰  0x00007fd6f435b1e8: jmpq   0x00007fd6f435b025 
             │││                                                     
             │││                                                     
             ↘↘↘       0x00007fd6f435b1ed: mov    $0xffffff7e,%esi
                       0x00007fd6f435b1f2: mov    %r11d,0x18(%rsp)
                       0x00007fd6f435b1f7: nop
                       0x00007fd6f435b1f8: vzeroupper 
                       0x00007fd6f435b1fb: callq  0x00007fd6ec89d280  
                                                                     
....................................................................................................
 95.73%  <total for region 1>
```

```asm
....[Hottest Region 1]..............................................................................
c2, level 4, inc.generated.Increments_autovecPre_jmhTest::autovecPre_avgt_jmhStub, version 460 (464 bytes) 
             
                       0x00007f44cc35d2f4: vzeroupper 
                       0x00007f44cc35d2f7: add    $0x30,%rsp
                       0x00007f44cc35d2fb: pop    %rbp
                       0x00007f44cc35d2fc: mov    0x108(%r15),%r10
                       0x00007f44cc35d303: test   %eax,(%r10)        
                       0x00007f44cc35d306: retq   
                       0x00007f44cc35d307: nop                       
                                                                     
                                                                     
  0.77%  ↗         ↗   0x00007f44cc35d308: vmovdqu 0x10(%r8,%rdx,4),%ymm0
  0.25%  │         │   0x00007f44cc35d30f: vpaddd 0x10(%r10,%rdx,4),%ymm0,%ymm0
  3.27%  │         │   0x00007f44cc35d316: vmovdqu %ymm0,0x10(%r8,%rdx,4)
         │         │                                                 
         │         │                                                 
  0.29%  │         │   0x00007f44cc35d31d: add    $0x8,%edx          
         │         │                                                 
         │         │                                                 
  0.10%  │         │   0x00007f44cc35d320: cmp    %r9d,%edx
         ╰         │   0x00007f44cc35d323: jl     0x00007f44cc35d308  
                   │                                                 
                   │                                                 
  0.19%          ↗ │↗  0x00007f44cc35d325: cmp    %r11d,%edx
          ╭      │ ││  0x00007f44cc35d328: jge    0x00007f44cc35d33d
          │      │ ││  0x00007f44cc35d32a: xchg   %ax,%ax            
          │      │ ││                                                
          │      │ ││                                                
  0.50%   │↗     │ ││  0x00007f44cc35d32c: mov    0x10(%r10,%rdx,4),%ebx
          ││     │ ││  0x00007f44cc35d331: add    %ebx,0x10(%r8,%rdx,4)
          ││     │ ││                                                
          ││     │ ││                                                
  1.06%   ││     │ ││  0x00007f44cc35d336: inc    %edx               
          ││     │ ││                                                
          ││     │ ││                                                
          ││     │ ││  0x00007f44cc35d338: cmp    %r11d,%edx
          │╰     │ ││  0x00007f44cc35d33b: jl     0x00007f44cc35d32c 
          │      │ ││                                                
          │      │ ││                                                
  0.10%   ↘ ↗    │ ││  0x00007f44cc35d33d: mov    %rcx,%rdx
            │    │ ││  0x00007f44cc35d340: shl    $0x3,%rdx          
            │    │ ││                                                
            │    │ ││                                                
  0.17%     │    │ ││  0x00007f44cc35d344: mov    0x10(%rsp),%rsi
            │    │ ││  0x00007f44cc35d349: data16 xchg %ax,%ax
  0.10%     │    │ ││  0x00007f44cc35d34c: vzeroupper 
  0.10%     │    │ ││  0x00007f44cc35d34f: callq  0x00007f44c489cb00 
            │    │ ││                                                
            │    │ ││                                               
            │    │ ││                                               
            │    │ ││                                               
  0.02%     │    │ ││  0x00007f44cc35d354: mov    0x40(%rsp),%r10
  0.08%     │    │ ││  0x00007f44cc35d359: movzbl 0x94(%r10),%r10d   
            │    │ ││                                                
            │    │ ││                                                
            │    │ ││  0x00007f44cc35d361: mov    0x108(%r15),%r11
  0.04%     │    │ ││  0x00007f44cc35d368: add    $0x1,%rbp          
            │    │ ││                                                
            │    │ ││                                                
            │    │ ││  0x00007f44cc35d36c: test   %eax,(%r11)        
  0.25%     │    │ ││  0x00007f44cc35d36f: test   %r10d,%r10d
            │    │ ││  0x00007f44cc35d372: jne    0x00007f44cc35d2cf 
            │    │ ││                                                
            │    │ ││  0x00007f44cc35d378: mov    0x50(%rsp),%r10
  0.04%     │    │ ││  0x00007f44cc35d37d: mov    0x10(%r10),%r10d   
            │    │ ││                                                
            │    │ ││                                                
            │    │ ││  0x00007f44cc35d381: mov    0xc(%r12,%r10,8),%r11d
            │    │ ││                                                
            │    │ ││                                                
            │    │ ││                                                
  0.15%     │    │ ││  0x00007f44cc35d386: mov    0x50(%rsp),%r8
            │    │ ││  0x00007f44cc35d38b: mov    0x14(%r8),%ecx     
            │    │ ││                                                
            │    │ ││                                                
  0.04%     │    │ ││  0x00007f44cc35d38f: test   %r11d,%r11d
            ╰    │ ││  0x00007f44cc35d392: jbe    0x00007f44cc35d33d 
                 │ ││                                                
                 │ ││                                                
  0.06%          │ ││  0x00007f44cc35d394: mov    0xc(%r12,%rcx,8),%r8d
                 │ ││                                                
                 │ ││                                                
                 │ ││                                                
  0.27%          │ ││  0x00007f44cc35d399: test   %r8d,%r8d
             ╭   │ ││  0x00007f44cc35d39c: jbe    0x00007f44cc35d4ed
  0.15%      │   │ ││  0x00007f44cc35d3a2: mov    %r11d,%r9d
             │   │ ││  0x00007f44cc35d3a5: dec    %r9d
  0.17%      │   │ ││  0x00007f44cc35d3a8: cmp    %r8d,%r9d
             │╭  │ ││  0x00007f44cc35d3ab: jae    0x00007f44cc35d4ed
  0.08%      ││  │ ││  0x00007f44cc35d3b1: cmp    %r11d,%r9d
             ││╭ │ ││  0x00007f44cc35d3b4: jae    0x00007f44cc35d4ed
  0.19%      │││ │ ││  0x00007f44cc35d3ba: shl    $0x3,%r10
             │││ │ ││  0x00007f44cc35d3be: lea    (%r12,%rcx,8),%r8
             │││ │ ││  0x00007f44cc35d3c2: mov    %r8d,%r9d
  0.12%      │││ │ ││  0x00007f44cc35d3c5: shr    $0x2,%r9d
  0.04%      │││ │ ││  0x00007f44cc35d3c9: and    $0x7,%r9d
             │││ │ ││  0x00007f44cc35d3cd: mov    $0x3,%ebx
             │││ │ ││  0x00007f44cc35d3d2: sub    %r9d,%ebx
  0.10%      │││ │ ││  0x00007f44cc35d3d5: and    $0x7,%ebx
  0.17%      │││ │ ││  0x00007f44cc35d3d8: inc    %ebx
             │││ │ ││  0x00007f44cc35d3da: cmp    %r11d,%ebx
             │││ │ ││  0x00007f44cc35d3dd: cmovg  %r11d,%ebx
  0.06%      │││ │ ││  0x00007f44cc35d3e1: xor    %edx,%edx          
             │││ │ ││                                                
             │││ │ ││                                                
  0.19%      │││↗│ ││  0x00007f44cc35d3e3: mov    0x10(%r10,%rdx,4),%edi
  0.21%      │││││ ││  0x00007f44cc35d3e8: add    %edi,0x10(%r8,%rdx,4)
             │││││ ││                                                
             │││││ ││                                                
  0.50%      │││││ ││  0x00007f44cc35d3ed: inc    %edx               
             │││││ ││                                                
             │││││ ││                                                
  0.21%      │││││ ││  0x00007f44cc35d3ef: cmp    %ebx,%edx
             │││╰│ ││  0x00007f44cc35d3f1: jl     0x00007f44cc35d3e3 
             │││ │ ││                                                
             │││ │ ││                                                
  0.08%      │││ │ ││  0x00007f44cc35d3f3: mov    %r11d,%ebx
             │││ │ ││  0x00007f44cc35d3f6: add    $0xffffffc1,%ebx
             │││ │ ││  0x00007f44cc35d3f9: cmp    %ebx,%edx
             │││ ╰ ││  0x00007f44cc35d3fb: jge    0x00007f44cc35d325  
             │││   ││                                                
             │││   ││                                                
  3.25%      │││  ↗││  0x00007f44cc35d401: vmovdqu 0x10(%r8,%rdx,4),%ymm0
  0.42%      │││  │││  0x00007f44cc35d408: vpaddd 0x10(%r10,%rdx,4),%ymm0,%ymm0
  9.16%      │││  │││  0x00007f44cc35d40f: vmovdqu %ymm0,0x10(%r8,%rdx,4)
  1.29%      │││  │││  0x00007f44cc35d416: vmovdqu 0x30(%r8,%rdx,4),%ymm0
             │││  │││  0x00007f44cc35d41d: vpaddd 0x30(%r10,%rdx,4),%ymm0,%ymm0
  8.47%      │││  │││  0x00007f44cc35d424: vmovdqu %ymm0,0x30(%r8,%rdx,4)
  0.60%      │││  │││  0x00007f44cc35d42b: vmovdqu 0x50(%r8,%rdx,4),%ymm0
             │││  │││  0x00007f44cc35d432: vpaddd 0x50(%r10,%rdx,4),%ymm0,%ymm0
 13.43%      │││  │││  0x00007f44cc35d439: vmovdqu %ymm0,0x50(%r8,%rdx,4)
  1.04%      │││  │││  0x00007f44cc35d440: vmovdqu 0x70(%r8,%rdx,4),%ymm0
             │││  │││  0x00007f44cc35d447: vpaddd 0x70(%r10,%rdx,4),%ymm0,%ymm0
  7.91%      │││  │││  0x00007f44cc35d44e: vmovdqu %ymm0,0x70(%r8,%rdx,4)
  0.58%      │││  │││  0x00007f44cc35d455: vmovdqu 0x90(%r8,%rdx,4),%ymm0
             │││  │││  0x00007f44cc35d45f: vpaddd 0x90(%r10,%rdx,4),%ymm0,%ymm0
  9.66%      │││  │││  0x00007f44cc35d469: vmovdqu %ymm0,0x90(%r8,%rdx,4)
  0.58%      │││  │││  0x00007f44cc35d473: vmovdqu 0xb0(%r8,%rdx,4),%ymm0
             │││  │││  0x00007f44cc35d47d: vpaddd 0xb0(%r10,%rdx,4),%ymm0,%ymm0
  9.14%      │││  │││  0x00007f44cc35d487: vmovdqu %ymm0,0xb0(%r8,%rdx,4)
  0.50%      │││  │││  0x00007f44cc35d491: vmovdqu 0xd0(%r8,%rdx,4),%ymm0
             │││  │││  0x00007f44cc35d49b: vpaddd 0xd0(%r10,%rdx,4),%ymm0,%ymm0
  9.08%      │││  │││  0x00007f44cc35d4a5: vmovdqu %ymm0,0xd0(%r8,%rdx,4)
  0.83%      │││  │││  0x00007f44cc35d4af: vmovdqu 0xf0(%r8,%rdx,4),%ymm0
             │││  │││  0x00007f44cc35d4b9: vpaddd 0xf0(%r10,%rdx,4),%ymm0,%ymm0
  8.52%      │││  │││  0x00007f44cc35d4c3: vmovdqu %ymm0,0xf0(%r8,%rdx,4)
             │││  │││                                                
             │││  │││                                                
  0.37%      │││  │││  0x00007f44cc35d4cd: add    $0x40,%edx         
             │││  │││                                                
             │││  │││                                                
             │││  │││  0x00007f44cc35d4d0: cmp    %ebx,%edx
             │││  ╰││  0x00007f44cc35d4d2: jl     0x00007f44cc35d401
  0.15%      │││   ││  0x00007f44cc35d4d8: mov    %r11d,%r9d
             │││   ││  0x00007f44cc35d4db: add    $0xfffffff9,%r9d
             │││   ││  0x00007f44cc35d4df: cmp    %r9d,%edx
             │││   ╰│  0x00007f44cc35d4e2: jl     0x00007f44cc35d308
             │││    ╰  0x00007f44cc35d4e8: jmpq   0x00007f44cc35d325 
             │││                                                     
             │││                                                     
             ↘↘↘       0x00007f44cc35d4ed: mov    $0xffffff7e,%esi
                       0x00007f44cc35d4f2: mov    %r11d,0x18(%rsp)
                       0x00007f44cc35d4f7: nop
                       0x00007f44cc35d4f8: vzeroupper 
....................................................................................................
 95.13%  <total for region 1>
```

I haven't included the perfasm output for the other loops, but the compiled code is also identical.
In `reducePre` and `reducePost` the loop is unrolled so `i` is incremented 8 at a time (`add $0x8,%esi`).
In the loops contrived not to be unrolled, the increments are performed one at a time using `inc %ebp`, but the code is still identical.

Even though this is a myth, does it actually cause any harm? 
Of course not, loops optimised under this delusion are compiled the same way. 
The only negative scenario would be if a misguided team member were to insist on this practice being followed.    

### True once: prefer StringBuilder to string concatenation

A very long time ago, in JDK1.4, when concatenating `String`s, a `StringBuffer` was used.

```java
public class StringExample {
  
  public static String concatenate(String left, String right) {
    return left + right;
  }

  public static String concatenateStringBuilder(String left, String right) {
    return new StringBuilder(left.length() + right.length())
            .append(left).append(right).toString();
  }
}
```

The top method above would use `StringBuffer`, which has `synchronized` methods:

```
  public static java.lang.String concatenate(java.lang.String, java.lang.String);
    Code:
       0: new           #2                  // class java/lang/StringBuffer
       3: dup
       4: invokespecial #3                  // Method java/lang/StringBuffer."<init>":()V
       7: aload_0
       8: invokevirtual #4                  // Method java/lang/StringBuffer.append:(Ljava/lang/String;)Ljava/lang/StringBuffer;
      11: aload_1
      12: invokevirtual #4                  // Method java/lang/StringBuffer.append:(Ljava/lang/String;)Ljava/lang/StringBuffer;
      15: invokevirtual #5                  // Method java/lang/StringBuffer.toString:()Ljava/lang/String;
      18: areturn

  public static java.lang.String concatenateStringBuilder(java.lang.String, java.lang.String);
    Code:
       0: new           #6                  // class java/lang/StringBuilder
       3: dup
       4: aload_0
       5: invokevirtual #7                  // Method java/lang/String.length:()I
       8: aload_1
       9: invokevirtual #7                  // Method java/lang/String.length:()I
      12: iadd
      13: invokespecial #8                  // Method java/lang/StringBuilder."<init>":(I)V
      16: aload_0
      17: invokevirtual #9                  // Method java/lang/StringBuilder.append:(Ljava/lang/String;)Ljava/lang/StringBuilder;
      20: aload_1
      21: invokevirtual #9                  // Method java/lang/StringBuilder.append:(Ljava/lang/String;)Ljava/lang/StringBuilder;
      24: invokevirtual #10                 // Method java/lang/StringBuilder.toString:()Ljava/lang/String;
```
This meant that using a `StringBuilder` at language level 1.4 would be beneficial.
If you learnt Java when 1.4 was commonly used, you might think this is an essential optimisation.

Later, the generated bytecode was improved, so that `StringBuilder` would be used instead.
In JDK1.8 (and earlier) the bytecode looks like this:

```
  public static java.lang.String concatenate(java.lang.String, java.lang.String);
    Code:
       0: new           #2                  // class java/lang/StringBuilder
       3: dup
       4: invokespecial #3                  // Method java/lang/StringBuilder."<init>":()V
       7: aload_0
       8: invokevirtual #4                  // Method java/lang/StringBuilder.append:(Ljava/lang/String;)Ljava/lang/StringBuilder;
      11: aload_1
      12: invokevirtual #4                  // Method java/lang/StringBuilder.append:(Ljava/lang/String;)Ljava/lang/StringBuilder;
      15: invokevirtual #5                  // Method java/lang/StringBuilder.toString:()Ljava/lang/String;
      18: areturn

  public static java.lang.String concatenateStringBuilder(java.lang.String, java.lang.String);
    Code:
       0: new           #2                  // class java/lang/StringBuilder
       3: dup
       4: aload_0
       5: invokevirtual #6                  // Method java/lang/String.length:()I
       8: aload_1
       9: invokevirtual #6                  // Method java/lang/String.length:()I
      12: iadd
      13: invokespecial #7                  // Method java/lang/StringBuilder."<init>":(I)V
      16: aload_0
      17: invokevirtual #4                  // Method java/lang/StringBuilder.append:(Ljava/lang/String;)Ljava/lang/StringBuilder;
      20: aload_1
      21: invokevirtual #4                  // Method java/lang/StringBuilder.append:(Ljava/lang/String;)Ljava/lang/StringBuilder;
      24: invokevirtual #5                  // Method java/lang/StringBuilder.toString:()Ljava/lang/String;
```
Maybe there's a tiny benefit in sizing the `StringBuilder`, but now the code is harder to read for marginal gain.
In JDK9, `String` concatenation was reworked, so the `StringBuilder` code is at a disadvantage to the more readable concatenation code:

```
  public static java.lang.String concatenate(java.lang.String, java.lang.String);
    Code:
       0: aload_0
       1: aload_1
       2: invokedynamic #2,  0              // InvokeDynamic #0:makeConcatWithConstants:(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;
       7: areturn

  public static java.lang.String concatenateStringBuilder(java.lang.String, java.lang.String);
    Code:
       0: new           #3                  // class java/lang/StringBuilder
       3: dup
       4: aload_0
       5: invokevirtual #4                  // Method java/lang/String.length:()I
       8: aload_1
       9: invokevirtual #4                  // Method java/lang/String.length:()I
      12: iadd
      13: invokespecial #5                  // Method java/lang/StringBuilder."<init>":(I)V
      16: aload_0
      17: invokevirtual #6                  // Method java/lang/StringBuilder.append:(Ljava/lang/String;)Ljava/lang/StringBuilder;
      20: aload_1
      21: invokevirtual #6                  // Method java/lang/StringBuilder.append:(Ljava/lang/String;)Ljava/lang/StringBuilder;
      24: invokevirtual #7                  // Method java/lang/StringBuilder.toString:()Ljava/lang/String;
```

The `invokedynamic` bytecode instruction, which can be used to drive better optimisations, is used instead of the `StringBuilder`.
The confusing thing is this only applies when the number of strings is known, so not in loops, but in most cases it's now better just to use `+`.
I won't bother to measure this progress because the people who made these changes to javac did that at the time, but the point is that even the bytecode can change in such a way to render old optimisations neutral or negative. 

In my last post, I tried to avoid putting forward items which might become untrue in the future, but didn't quite manage this.
I predict that four of the five items will stand the test of time, but item three (avoid iterating over `Enum.values()`) may eventually become a myth if [frozen arrays](https://openjdk.java.net/jeps/8261007) become a reality in the future.

### Continuous profiling

There are more important factors to system efficiency than low-level programming details.
For instance, being required by specification to do something wasteful by an external system is a problem which should be solved architecturally.
If architectural blunders create bottlenecks, it's very costly to fix.

Assuming a sensible architecture, the causes of many costs are neither dictated by nor are observable to external systems, so can be changed easily. 
Efficiency at this level depends on choices of algorithm, data structure, and level of mechanical sympathy.
These kinds of problems can be surfaced by using continuous profiling, and are often surprising.
Continuous profiling, by its nature, tends to highlight what's important to reducing overall cost, and filters out distracting and obvious fixed costs in favour of unexpected unit costs.
My impression is that many engineers believe profiling to be too expensive to run in production, but I think these engineers' minds would be blown by how much CPU time is spent collecting logs, metrics, and traces if they tried it.
The reality is that it costs about 3% CPU utilisation and will lead to double-digit savings which translate to significantly reduced running costs for all but the leanest applications.  

I think a diagram, drawn by Aleksey Shipilёv several years ago, explains where continuous profiling is useful:

<blockquote class="twitter-tweet"><p lang="en" dir="ltr">I relax by drawing stuff on my large whiteboard. Here&#39;s &quot;Perf Work Phase Diagram&quot; for you. <a href="http://t.co/RnITiLoNFH">pic.twitter.com/RnITiLoNFH</a></p>&mdash; Aleksey Shipilëv (@shipilev) <a href="https://twitter.com/shipilev/status/578193813946134529?ref_src=twsrc%5Etfw">March 18, 2015</a></blockquote> <script async src="https://platform.twitter.com/widgets.js" charset="utf-8"></script>

Essentially, continuous profiling will help you get from an _Amazingly stupid program_ to _Beauty Peak_ by making it obvious where the costs are; the majority of programs needn't go beyond _Beauty Peak_.
This process doesn't consist entirely of making the kinds of mundane point substitutions in my last post.
It's often necessary to take a step back and ask why something costly is happening at all, and rework the algorithm, rather than think about cost reduction.

Despite all this, once you have data about what your program spends its time doing, many of the culprits will be completely mundane unless you have a very interesting program.
When there's no complexity cost in using a more efficient idiom, there's no need to wait for its necessity to be proven by a profiler.
In any case, continuous profiling should help calibrate your sense of which idioms are costly, and avoid the myths. 

