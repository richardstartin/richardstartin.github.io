---
ID: 10750
title: Collecting Rocks and Benchmarks
author: Richard Startin
post_excerpt: ""
layout: post
theme: minima
published: true
date: 2018-03-29 18:44:59
---
As long as I can remember, I have been interested in rocks, I have hundreds of them in storage. Rocks are interesting because they hold little clues about processes nobody has ever seen happen. For instance, one of the first rocks I ever took an interest in was a smooth granite pebble, which I collected on a walk when I was six. Let's be honest, as a six year old, it was the pattern on the surface of the rock that caught my eye, but this truly was a fascinating rock because it shouldn't have been smooth and it shouldn't have been in England. It probably came from Norway, and while it's possible that a Norwegian brought the rock to England, it's highly unlikely. 

The best possible explanation of the rock's existence in that point in space and time was that there was once a glacier covering Norway, the North Sea, and Northern England, moving in that direction. The glacier carried the pebble, and many others like it, and dumped it as glacial outwash in the English Midlands. Nobody alive saw this happen, but if this happened, Scotland (relieved of the weight of an ice sheet) should still be rising in altitude, and there should be clay in the Midlands but not in the South. It's likely that there was an ice age, not just because I found a granite pebble, but because Scotland <em>is</em> rising, and the English Midlands <em>are</em> covered in clay. You may lack the tools, funds, or time to do so, but you can apply this process to virtually anything to figure out how something happened or works.

If you're an application developer, as I am, it's highly unlikely that you wrote the platform you use, so you probably don't really understand it. The vast majority of the platform you use was written by other people over what might as well be geological timescales. Benchmarks are a lot like rocks in that they can reveal implementation details you aren't otherwise party to, and, with the right trade offs, you may be able to harness these in your applications. Collecting rocks doesn't make a geologist, and I think you need to be quite inquisitive for benchmarking to work out, because you need to seek corroborating evidence: just as the presence of a pebble is scant support for an ice age, a single benchmark score doesn't say much about anything. 

If you're interested in the JVM, I think instruction profiling is essential because it gives so much away. For instance, you may not appreciate the significance of choice of garbage collector, but you'll see lots of strange instructions in some benchmarks if you profile them, and you may have the curiosity to ask what they do and what put them there. If you don't do it, you won't really know the boundaries of validity of whatever your observation is. You could find that changing your garbage collector invalidates your findings.

Partly because I want the information on this site to be basically correct, but also to illustrate how conclusions can be jumped to because a benchmark score confirms a personal bias, I'll look again at a couple of very <a href="https://richardstartin.github.io/posts/still-true-in-java-9-handwritten-hash-codes-are-faster/" rel="noopener noreferrer" target="_blank">superficial benchmarks</a> I wrote about last year, to do with polynomial hash codes. The measurements were probably fine, but I didn't really get to the bottom of the issue and I could easily have found a faster implementation if I had looked a bit harder.

<h3>Polynomial Hash Codes</h3>

The Java `String.hashCode` and `Arrays.hashCode` methods are implemented as the dot product of the data and a vector of powers of 31.

```java
    // Arrays.java
    public static int hashCode(int a[]) {
        if (a == null)
            return 0;

        int result = 1;
        for (int element : a)
            result = 31 * result + element;

        return result;
    }
```

Since `String` caches its hash code, you'd be hard pressed to make use of the following optimisations, but I found I learned something about what C2 does and doesn't do by attempting to optimise it. First of all, what does the built in hash code actually do? You can only really find out with instruction profiling, which you can enable in JMH with `-prof perfasm` on Linux or `-prof xperfasm` on Windows.

The bulk of the sampled instructions are in this block below:

```asm
           0x000002720f204af2: add     edi,dword ptr [rax+rbx*4+10h]
  2.37%    0x000002720f204af6: mov     r10d,edi
  1.72%    0x000002720f204af9: shl     r10d,5h
  2.06%    0x000002720f204afd: sub     r10d,edi
  3.77%    0x000002720f204b00: add     r10d,dword ptr [rax+rbx*4+14h]
  3.93%    0x000002720f204b05: mov     r8d,r10d
  0.01%    0x000002720f204b08: shl     r8d,5h
  3.80%    0x000002720f204b0c: sub     r8d,r10d
  3.98%    0x000002720f204b0f: add     r8d,dword ptr [rax+rbx*4+18h]
  4.12%    0x000002720f204b14: mov     r10d,r8d
           0x000002720f204b17: shl     r10d,5h
  3.78%    0x000002720f204b1b: sub     r10d,r8d
  3.75%    0x000002720f204b1e: add     r10d,dword ptr [rax+rbx*4+1ch]
  3.81%    0x000002720f204b23: mov     r8d,r10d
           0x000002720f204b26: shl     r8d,5h
  4.04%    0x000002720f204b2a: sub     r8d,r10d
  4.15%    0x000002720f204b2d: add     r8d,dword ptr [rax+rbx*4+20h]
  3.98%    0x000002720f204b32: mov     r10d,r8d
           0x000002720f204b35: shl     r10d,5h
  4.27%    0x000002720f204b39: sub     r10d,r8d
  3.95%    0x000002720f204b3c: add     r10d,dword ptr [rax+rbx*4+24h]
  3.77%    0x000002720f204b41: mov     r8d,r10d
           0x000002720f204b44: shl     r8d,5h
  4.01%    0x000002720f204b48: sub     r8d,r10d
  4.02%    0x000002720f204b4b: add     r8d,dword ptr [rax+rbx*4+28h]
  4.11%    0x000002720f204b50: mov     ecx,r8d
           0x000002720f204b53: shl     ecx,5h
  4.08%    0x000002720f204b56: sub     ecx,r8d
  4.31%    0x000002720f204b59: add     ecx,dword ptr [rax+rbx*4+2ch]
```

The first thing to ask is where is the multiplication? There is no multiplication, it's been replaced by a left shift and a subtraction. 

```java
    public int StrengthReduction() {
        int result = 1;
        for (int i = 0; i < data.length; ++i) {
            result = (result << 5) - result + data[i];
        }
        return result;
    }
```

This is the compiler trying to be helpful because shifts and subtractions are cheaper than multiplications, and for 31, this transformation is possible. The snippet is one long chain of instructions: notice the register dependencies in the assembly snippet: 

```asm
  4.15%    0x000002720f204b2d: add     r8d,dword ptr [rax+rbx*4+20h]
  3.98%    0x000002720f204b32: mov     r10d,r8d
           0x000002720f204b35: shl     r10d,5h
  4.27%    0x000002720f204b39: sub     r10d,r8d
```

The addition must complete before the contents of `r8d` are available for the move, the left shift waits for the move, and the subtraction waits for the shift. No two elements of the array are ever processed simultaneously. First suggested by <a href="http://mail.openjdk.java.net/pipermail/core-libs-dev/2014-September/028898.html" rel="noopener noreferrer" target="_blank">Peter Levart</a>, I came across it on <a href="https://lemire.me/blog/2015/10/22/faster-hashing-without-effort/" rel="noopener noreferrer" target="_blank">Daniel Lemire's blog</a>, the dependency can be broken by manually unrolling the loop:

```java
    @Benchmark
    public int Unrolled() {
        if (data == null)
            return 0;

        int result = 1;
        int i = 0;
        for (; i + 7 < data.length; i += 8) {
            result = 31 * 31 * 31 * 31 * 31 * 31 * 31 * 31 * result
                   + 31 * 31 * 31 * 31 * 31 * 31 * 31 * data[i]
                   + 31 * 31 * 31 * 31 * 31 * 31 * data[i + 1]
                   + 31 * 31 * 31 * 31 * 31 * data[i + 2]
                   + 31 * 31 * 31 * 31 * data[i + 3]
                   + 31 * 31 * 31 * data[i + 4]
                   + 31 * 31 * data[i + 5]
                   + 31 * data[i + 6]
                   + data[i + 7]
                    ;
        }
        for (; i < data.length; i++) {
            result = 31 * result + data[i];
        }
        return result;
    }
```

Weirdly, this implementation does very well (this isn't new: there has been a <a href="https://bugs.openjdk.java.net/browse/JDK-8059113" rel="noopener noreferrer" target="_blank">ticket</a> for it for several years). Without even bothering with a throughput score, the profiling output shows that this must be much better. The assembly is quite hard to read because it's full of tricks I didn't know existed, but look out for the hexadecimal constants and convince yourself that several are simply powers of 31. The multiplication by 31 is strength reduced to a left shift and a subtraction again.

```asm
  0.26%    0x000001d67bdd3c8e: mov     r8d,94446f01h
  0.01%    0x000001d67bdd3c94: jmp     1d67bdd3cb1h
           0x000001d67bdd3c96: nop     word ptr [rax+rax+0h]
           0x000001d67bdd3ca0: mov     edi,r11d
  0.03%    0x000001d67bdd3ca3: vmovq   r14,xmm0
  0.42%    0x000001d67bdd3ca8: mov     ebp,dword ptr [rsp+70h]
  7.14%    0x000001d67bdd3cac: vmovq   rbx,xmm1          
  0.01%    0x000001d67bdd3cb1: cmp     edi,r9d
           0x000001d67bdd3cb4: jnb     1d67bdd3d6ch
  0.04%    0x000001d67bdd3cba: imul    r10d,dword ptr [rcx+rdi*4+10h],67e12cdfh ; Another strength reduction trick
  7.74%    0x000001d67bdd3cc3: add     r10d,r8d                                 ; 1742810335 * x + 2487512833
  2.69%    0x000001d67bdd3cc6: mov     r11d,edi                                 
  0.09%    0x000001d67bdd3cc9: add     r11d,7h                                  
  0.46%    0x000001d67bdd3ccd: cmp     r11d,r9d                             
           0x000001d67bdd3cd0: jnb     1d67bdd3dbah
  6.82%    0x000001d67bdd3cd6: vmovq   xmm1,rbx
  0.61%    0x000001d67bdd3cdb: mov     dword ptr [rsp+70h],ebp
  0.06%    0x000001d67bdd3cdf: vmovq   xmm0,r14          
  0.46%    0x000001d67bdd3ce4: mov     r14,qword ptr [r15+70h]
  6.60%    0x000001d67bdd3ce8: mov     r11d,edi
  0.67%    0x000001d67bdd3ceb: add     r11d,8h 
  0.04%    0x000001d67bdd3cef: movsxd  rax,edi
  0.41%    0x000001d67bdd3cf2: add     edi,0fh
  6.87%    0x000001d67bdd3cf5: mov     edx,dword ptr [rcx+rax*4+28h]
  0.68%    0x000001d67bdd3cf9: imul    r8d,dword ptr [rcx+rax*4+14h],34e63b41h ; multiply by 887503681
  0.67%    0x000001d67bdd3d02: add     r8d,r10d   ; --------------------------
  7.30%    0x000001d67bdd3d05: mov     r10d,edx   ; Multiply by 31
  0.63%    0x000001d67bdd3d08: shl     r10d,5h    ;
  0.08%    0x000001d67bdd3d0c: sub     r10d,edx   ; --------------------------
  0.73%    0x000001d67bdd3d0f: imul    edx,dword ptr [rcx+rax*4+24h],3c1h     ; multiply by 961
  7.47%    0x000001d67bdd3d17: imul    ebp,dword ptr [rcx+rax*4+20h],745fh    ; multiply by 29791 
  0.56%    0x000001d67bdd3d1f: imul    esi,dword ptr [rcx+rax*4+1ch],0e1781h  ; multiply by 923521 
  7.02%    0x000001d67bdd3d27: imul    ebx,dword ptr [rcx+rax*4+18h],1b4d89fh ; multiply by 28629151 
  0.57%    0x000001d67bdd3d2f: add     r8d,ebx
  6.99%    0x000001d67bdd3d32: add     r8d,esi
  0.66%    0x000001d67bdd3d35: add     r8d,ebp
  0.14%    0x000001d67bdd3d38: add     r8d,edx
  0.91%    0x000001d67bdd3d3b: add     r8d,r10d
  7.04%    0x000001d67bdd3d3e: add     r8d,dword ptr [rcx+rax*4+2ch] ; add the data value at offset 7
  1.73%    0x000001d67bdd3d43: test    dword ptr [r14],eax  
  0.06%    0x000001d67bdd3d46: cmp     edi,r9d
           0x000001d67bdd3d49: jnl     1d67bdd3c15h      
  0.45%    0x000001d67bdd3d4f: imul    r8d,r8d,94446f01h ; multiply by 2487512833 (coprime to 31, follow r8d backwards)
 11.90%    0x000001d67bdd3d56: cmp     r11d,r9d
```

It's probably not worth deciphering all the tricks in the code above, but notice that there is a lot of parallelism: the chain of signed multiplications target different registers and are independent. This code is much faster.

I wrote the code below in July last year to try to parallelise this calculation. At the expense of precomputing the powers of 31 up to some fixed length, such as the maximum length of strings in your database, it's quite fast.

```java
    private final int[] coefficients;

    public FixedLengthHashCode(int maxLength) {
        this.coefficients = new int[maxLength + 1];
        coefficients[0] = 1;
        for (int i = 1; i <= maxLength; ++i) {
            coefficients[i] = 31 * coefficients[i - 1];
        }
    }

    public int hashCode(int[] value) {
        final int max = value.length;
        int result = coefficients[max];
        for (int i = 0; i < value.length && i < coefficients.length - 1; ++i) {
            result += coefficients[max - i - 1] * value[i];
        }
        return result;
    }
```

I was non-commital in the original post but I sort-of claimed this code was vectorised without even bothering to look at the disassembly. It's scalar, but it's much more parallel than the unrolled version, and all the clever strength reductions and dependencies are gone.

```asm
  0.15%    0x0000022d8e6825e0: movsxd  rbx,ecx
  0.07%    0x0000022d8e6825e3: mov     rdx,rsi
  3.57%    0x0000022d8e6825e6: sub     rdx,rbx
  0.08%    0x0000022d8e6825e9: mov     r10d,dword ptr [r9+rbx*4+10h]
  0.18%    0x0000022d8e6825ee: imul    r10d,dword ptr [rdi+rdx*4+0ch]
  0.15%    0x0000022d8e6825f4: add     r10d,r8d
  4.25%    0x0000022d8e6825f7: mov     r11d,dword ptr [r9+rbx*4+14h]
  0.14%    0x0000022d8e6825fc: imul    r11d,dword ptr [rdi+rdx*4+8h]
  0.19%    0x0000022d8e682602: add     r11d,r10d
  1.31%    0x0000022d8e682605: mov     r10d,dword ptr [r9+rbx*4+18h]
  3.93%    0x0000022d8e68260a: imul    r10d,dword ptr [rdi+rdx*4+4h]
  0.22%    0x0000022d8e682610: add     r10d,r11d
  0.94%    0x0000022d8e682613: mov     r8d,dword ptr [r9+rbx*4+1ch]
  0.05%    0x0000022d8e682618: imul    r8d,dword ptr [rdi+rdx*4]
  3.68%    0x0000022d8e68261d: add     r8d,r10d
  1.02%    0x0000022d8e682620: mov     r10d,dword ptr [r9+rbx*4+20h]
  0.19%    0x0000022d8e682625: imul    r10d,dword ptr [rdi+rdx*4+0fffffffffffffffch]
  0.61%    0x0000022d8e68262b: add     r10d,r8d
  4.71%    0x0000022d8e68262e: mov     r11d,dword ptr [r9+rbx*4+24h]
  0.08%    0x0000022d8e682633: imul    r11d,dword ptr [rdi+rdx*4+0fffffffffffffff8h]
  0.82%    0x0000022d8e682639: add     r11d,r10d
  5.57%    0x0000022d8e68263c: mov     r10d,dword ptr [r9+rbx*4+28h]
  0.04%    0x0000022d8e682641: imul    r10d,dword ptr [rdi+rdx*4+0fffffffffffffff4h]
  0.68%    0x0000022d8e682647: add     r10d,r11d
  4.67%    0x0000022d8e68264a: mov     r11d,dword ptr [r9+rbx*4+2ch]
  0.08%    0x0000022d8e68264f: imul    r11d,dword ptr [rdi+rdx*4+0fffffffffffffff0h]
  0.45%    0x0000022d8e682655: add     r11d,r10d
  4.50%    0x0000022d8e682658: mov     r10d,dword ptr [r9+rbx*4+30h]
  0.20%    0x0000022d8e68265d: imul    r10d,dword ptr [rdi+rdx*4+0ffffffffffffffech]
  0.37%    0x0000022d8e682663: add     r10d,r11d
  3.82%    0x0000022d8e682666: mov     r8d,dword ptr [r9+rbx*4+34h]
  0.05%    0x0000022d8e68266b: imul    r8d,dword ptr [rdi+rdx*4+0ffffffffffffffe8h]
  0.42%    0x0000022d8e682671: add     r8d,r10d
  4.18%    0x0000022d8e682674: mov     r10d,dword ptr [r9+rbx*4+38h]
  0.02%    0x0000022d8e682679: imul    r10d,dword ptr [rdi+rdx*4+0ffffffffffffffe4h]
  0.25%    0x0000022d8e68267f: add     r10d,r8d
  5.11%    0x0000022d8e682682: mov     r11d,dword ptr [r9+rbx*4+3ch]
  0.03%    0x0000022d8e682687: imul    r11d,dword ptr [rdi+rdx*4+0ffffffffffffffe0h]
  0.28%    0x0000022d8e68268d: add     r11d,r10d
  4.88%    0x0000022d8e682690: mov     r10d,dword ptr [r9+rbx*4+40h]
  0.09%    0x0000022d8e682695: imul    r10d,dword ptr [rdi+rdx*4+0ffffffffffffffdch]
  0.21%    0x0000022d8e68269b: add     r10d,r11d
  4.56%    0x0000022d8e68269e: mov     r8d,dword ptr [r9+rbx*4+44h]
  0.02%    0x0000022d8e6826a3: imul    r8d,dword ptr [rdi+rdx*4+0ffffffffffffffd8h]
  0.18%    0x0000022d8e6826a9: add     r8d,r10d
  4.73%    0x0000022d8e6826ac: mov     r10d,dword ptr [r9+rbx*4+48h]
  0.06%    0x0000022d8e6826b1: imul    r10d,dword ptr [rdi+rdx*4+0ffffffffffffffd4h]
  0.10%    0x0000022d8e6826b7: add     r10d,r8d
  4.12%    0x0000022d8e6826ba: mov     r8d,dword ptr [r9+rbx*4+4ch]
```

That <a href="https://richardstartin.github.io/posts/explicit-intent-and-even-faster-hash-codes/" rel="noopener noreferrer" target="_blank">blog post</a> really was lazy. There's a bit of a problem with the access pattern because the coefficients are accessed in reverse order, and at an offset: it's too complicated for the optimiser. The code below is just a dot product and it should come as no surprise that it's faster.

```java
    private int[] coefficients;
    private int seed;

    void init(int size) {
        coefficients = new int[size]; 
        coefficients[size - 1] = 1;
        for (int i = size - 2; i >= 0; --i) {
            coefficients[i] = 31 * coefficients[i + 1];
        }
        seed = 31 * coefficients[0];
    }

    @Benchmark
    public int Vectorised() {
        int result = seed;
        for (int i = 0; i < data.length && i < coefficients.length; ++i) {
            result += coefficients[i] * data[i];
        }
        return result;
    }
```

The code vectorises, but the reduction isn't as good as it could be with handwritten code.

```asm
  0.22%    0x000001d9c2e0f320: vmovdqu ymm0,ymmword ptr [rdi+rsi*4+70h]
  2.31%    0x000001d9c2e0f326: vpmulld ymm0,ymm0,ymmword ptr [r11+rsi*4+70h]
  0.61%    0x000001d9c2e0f32d: vmovdqu ymm1,ymmword ptr [rdi+rsi*4+50h]
  2.61%    0x000001d9c2e0f333: vpmulld ymm9,ymm1,ymmword ptr [r11+rsi*4+50h]
  0.53%    0x000001d9c2e0f33a: vmovdqu ymm1,ymmword ptr [rdi+rsi*4+30h]
  2.07%    0x000001d9c2e0f340: vpmulld ymm10,ymm1,ymmword ptr [r11+rsi*4+30h]
  0.60%    0x000001d9c2e0f347: vmovdqu ymm1,ymmword ptr [rdi+rsi*4+10h]
  2.33%    0x000001d9c2e0f34d: vpmulld ymm11,ymm1,ymmword ptr [r11+rsi*4+10h]
  0.61%    0x000001d9c2e0f354: vphaddd ymm7,ymm11,ymm11
  3.04%    0x000001d9c2e0f359: vphaddd ymm7,ymm7,ymm8
  3.56%    0x000001d9c2e0f35e: vextracti128 xmm8,ymm7,1h
  0.53%    0x000001d9c2e0f364: vpaddd  xmm7,xmm7,xmm8
  1.56%    0x000001d9c2e0f369: vmovd   xmm8,r8d
  1.77%    0x000001d9c2e0f36e: vpaddd  xmm8,xmm8,xmm7
  0.93%    0x000001d9c2e0f372: vmovd   edx,xmm8
  0.27%    0x000001d9c2e0f376: vphaddd ymm2,ymm10,ymm10
  2.75%    0x000001d9c2e0f37b: vphaddd ymm2,ymm2,ymm6
  2.32%    0x000001d9c2e0f380: vextracti128 xmm6,ymm2,1h
  1.95%    0x000001d9c2e0f386: vpaddd  xmm2,xmm2,xmm6
  0.63%    0x000001d9c2e0f38a: vmovd   xmm6,edx
  0.50%    0x000001d9c2e0f38e: vpaddd  xmm6,xmm6,xmm2
  7.76%    0x000001d9c2e0f392: vmovd   edx,xmm6
  0.22%    0x000001d9c2e0f396: vphaddd ymm5,ymm9,ymm9
  2.68%    0x000001d9c2e0f39b: vphaddd ymm5,ymm5,ymm1
  0.34%    0x000001d9c2e0f3a0: vextracti128 xmm1,ymm5,1h
  6.27%    0x000001d9c2e0f3a6: vpaddd  xmm5,xmm5,xmm1
  0.88%    0x000001d9c2e0f3aa: vmovd   xmm1,edx
  0.92%    0x000001d9c2e0f3ae: vpaddd  xmm1,xmm1,xmm5
  7.85%    0x000001d9c2e0f3b2: vmovd   edx,xmm1
  0.43%    0x000001d9c2e0f3b6: vphaddd ymm4,ymm0,ymm0
  2.59%    0x000001d9c2e0f3bb: vphaddd ymm4,ymm4,ymm3
  0.34%    0x000001d9c2e0f3c0: vextracti128 xmm3,ymm4,1h
  5.72%    0x000001d9c2e0f3c6: vpaddd  xmm4,xmm4,xmm3
  0.80%    0x000001d9c2e0f3ca: vmovd   xmm3,edx
  0.58%    0x000001d9c2e0f3ce: vpaddd  xmm3,xmm3,xmm4
  8.09%    0x000001d9c2e0f3d2: vmovd   r8d,xmm3
```

Using JDK9, this results in a 3x throughput gain over the built in `Arrays.hashCode`, and that includes the cost of doubling the number of bytes to process and a suboptimal reduction phase. This is going to be a prime candidate for the <a href="https://software.intel.com/en-us/articles/vector-api-developer-program-for-java" rel="noopener noreferrer" target="_blank">Vector API</a>, where a vector of powers of 31 could be multiplied by `31^8` on each iteration, before multiplying by a vector of the next 8 data elements.

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
<td>BuiltIn</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">3.439980</td>
<td align="right">0.024231</td>
<td>ops/us</td>
<td align="right">256</td>
</tr>
<tr>
<td>BuiltIn</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.842664</td>
<td align="right">0.009019</td>
<td>ops/us</td>
<td align="right">1024</td>
</tr>
<tr>
<td>BuiltIn</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.103638</td>
<td align="right">0.003070</td>
<td>ops/us</td>
<td align="right">8192</td>
</tr>
<tr>
<td>FixedLength</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">7.421648</td>
<td align="right">0.169558</td>
<td>ops/us</td>
<td align="right">256</td>
</tr>
<tr>
<td>FixedLength</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.966116</td>
<td align="right">0.044398</td>
<td>ops/us</td>
<td align="right">1024</td>
</tr>
<tr>
<td>FixedLength</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.249666</td>
<td align="right">0.009994</td>
<td>ops/us</td>
<td align="right">8192</td>
</tr>
<tr>
<td>StrengthReduction</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">3.417248</td>
<td align="right">0.045733</td>
<td>ops/us</td>
<td align="right">256</td>
</tr>
<tr>
<td>StrengthReduction</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.840830</td>
<td align="right">0.011091</td>
<td>ops/us</td>
<td align="right">1024</td>
</tr>
<tr>
<td>StrengthReduction</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.104265</td>
<td align="right">0.001537</td>
<td>ops/us</td>
<td align="right">8192</td>
</tr>
<tr>
<td>Unrolled</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">6.353271</td>
<td align="right">0.042330</td>
<td>ops/us</td>
<td align="right">256</td>
</tr>
<tr>
<td>Unrolled</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.672845</td>
<td align="right">0.035389</td>
<td>ops/us</td>
<td align="right">1024</td>
</tr>
<tr>
<td>Unrolled</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.205575</td>
<td align="right">0.009375</td>
<td>ops/us</td>
<td align="right">8192</td>
</tr>
<tr>
<td>Vectorised</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">10.958270</td>
<td align="right">0.109993</td>
<td>ops/us</td>
<td align="right">256</td>
</tr>
<tr>
<td>Vectorised</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">2.948918</td>
<td align="right">0.081830</td>
<td>ops/us</td>
<td align="right">1024</td>
</tr>
<tr>
<td>Vectorised</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.358819</td>
<td align="right">0.027316</td>
<td>ops/us</td>
<td align="right">8192</td>
</tr>
</tbody></table>
</div>