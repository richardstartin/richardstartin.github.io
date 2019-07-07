---
ID: 10571
post_title: Iterating Over a Bitset in Java
author: Richard Startin
post_excerpt: ""
layout: post
permalink: >
  http://richardstartin.uk/iterating-over-a-bitset-in-java/
published: true
post_date: 2018-02-23 21:24:44
---
How fast can you iterate over a bitset? Daniel Lemire published a <a href="https://lemire.me/blog/2018/02/21/iterating-over-set-bits-quickly/" rel="noopener" target="_blank">benchmark</a> recently in support of a strategy using the number of trailing zeroes to skip over empty bits. I have used the same technique in Java several times in my hobby project <a href="https://github.com/richardstartin/splitmap" rel="noopener" target="_blank">SplitMap</a> and this is something I am keen to optimise. I think that the best strategy depends on what you want to do <em>with</em> the set bits, and how sparse and uniformly distributed they are. I argue that the cost of iteration is less important than the constraints your API imposes on the caller, and whether the caller is free to exploit patterns in the data.

<h3>C2 Generates Good Code</h3>

If you think C++ is much faster than Java, you either don't know much about Java or do lots of floating point arithmetic. This isn't about benchmarking C++ against Java, but comparing the compilation outputs for a C++ implementation and a Java implementation shows that there won't be much difference if your Java method gets hot. Only the time to performance will differ, and this is amortised over the lifetime of an application. The trailing zeroes implementation is probably the fastest technique in Java as well as in C++, but that is to ignore the optimisations you <em>can't</em> apply to the callback if you use it too literally.

Compiling this C++ function with GCC yields the snippet of assembly taken from the loop kernel:

```cpp
template <typename CALLBACK>
static void for_each(const long* bitmap, const int size, const CALLBACK& callback) {
    for (size_t k = 0; k < size; ++k) {
        long bitset = bitmap[k];
        while (bitset != 0) {
            callback((k * 64) + __builtin_ctzl(bitset));
            bitset ^= (bitset & -bitset);
        }
    }
}
```

The instruction `tzcntl` calculates the next set bit and `blsr` switches it off.

```asm
.L99:
	movq	%rdi, %rcx
	blsr	%ebx, %ebx
	call	_ZNSo3putEc
	movq	%rax, %rcx
	call	_ZNSo5flushEv
	testl	%ebx, %ebx
	je	.L96
.L100:
	xorl	%edx, %edx
	movq	%r12, %rcx
	tzcntl	%ebx, %edx
	addl	%ebp, %edx
	call	_ZNSolsEi
	movq	%rax, %rdi
	movq	(%rax), %rax
	movq	-24(%rax), %rax
	movq	240(%rdi,%rax), %rsi
	testq	%rsi, %rsi
	je	.L108
	cmpb	$0, 56(%rsi)
	jne	.L109
	movq	%rsi, %rcx
	call	_ZNKSt5ctypeIcE13_M_widen_initEv
	movq	(%rsi), %rax
	movl	$10, %edx
	movq	48(%rax), %rax
	cmpq	%r14, %rax
	je	.L99
	movq	%rsi, %rcx
	call	*%rax
	movsbl	%al, %edx
	jmp	.L99
	.p2align 4,,10
```

In Java, almost identical code is generated.

```java
public void forEach(long[] bitmap, IntConsumer consumer) {
    for (int i = 0; i < bitmap.length; ++i) {
      long word = bitmap[i];
      while (word != 0) {
        consumer.accept(Long.SIZE * i + Long.numberOfTrailingZeros(word));
        word ^= Long.lowestOneBit(word);
      }
    }
  }
```

The key difference is that `xor` and `blsi` haven't been fused into `blsr`, so the C++ code is probably slightly faster. A lambda function accumulating the contents of an array is inlined into this loop (the `add` comes from an inlined lambda, but notice how little time is spent adding compared to computing the bit to switch off in this sample produced by perfasm).

```asm
   .83%    0x000002d79d366a19: tzcnt   r9,rcx
  8.53%    0x000002d79d366a1e: add     r9d,ebx
  0.42%    0x000002d79d366a21: cmp     r9d,r8d
  0.00%    0x000002d79d366a24: jnb     2d79d366a4dh
  0.62%    0x000002d79d366a26: add     r10d,dword ptr [rdi+r9*4+10h]
 16.22%    0x000002d79d366a2b: vmovq   r11,xmm4
  6.68%    0x000002d79d366a30: mov     dword ptr [r11+10h],r10d
 27.92%    0x000002d79d366a34: blsi    r10,rcx
  0.55%    0x000002d79d366a39: xor     rcx,r10         
  0.10%    0x000002d79d366a3c: mov     r11,qword ptr [r15+70h]  
```

It's this Java code, and its impact on which optimisations can be applied to the `IntConsumer` that this post focuses on. There are different principles, particularly related to inlining and vectorisation opportunities in C++, but this blog is about Java. Depending on what your callback does, you get different benchmark results and you should make different choices about how to do the iteration: you just can't assess this in isolation.

<h3>Special Casing -1</h3>

Imagine you have an `int[]` containing data, and you are iterating over a mask or materialised predicate over that data. For each set bit, you want to add the corresponding entry in the array to a sum. In Java, that looks like this (you've already seen the generated assembly above):

```java
  @Benchmark
  public int reduce() {
    int[] result = new int[1];
    forEach(bitmap, i -> result[0] += data[i]);
    return result[0];
  }
```

How fast can this get? It obviously depends on how full the bitset is. The worst case would be that it's completely full, and it couldn't get much better than if only one bit per word were set. The difference is noticeable, but scales by a factor less than the number of bits:

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th>Benchmark</th>
<th>Mode</th>
<th>Threads</th>
<th>Samples</th>
<th>Score</th>
<th>Score Error (99.9%)</th>
<th>Unit</th>
<th>Param: scenario</th>
</tr></thead>
<tbody><tr>
<td>reduce</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">7.435909</td>
<td align="right">0.017491</td>
<td>ops/ms</td>
<td>FULL</td>
</tr>
<tr>
<td>reduce</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">260.305307</td>
<td align="right">6.081961</td>
<td>ops/ms</td>
<td>ONE_BIT_PER_WORD</td>
</tr>
</tbody></table>
</div>

But the important code here, the callback itself, is stuck at entry level compilation. There is no unrolling, no vectorisation, the `add`s can't be pipelined because there is a data dependency on `blsi` and `xor`. We can do much better in some cases, and not much worse in others, just by treating -1 as a special case, profiting from optimisations that can now be applied inside the callback. Passing a different callback which consumes whole words costs a branch, but it's often worth it. Here's the iterator now:

```java
  interface WordConsumer {
    void acceptWord(int wordIndex, long word);
  }

  public void forEach(long[] bitmap, IntConsumer intConsumer, WordConsumer wordConsumer) {
    for (int i = 0; i < bitmap.length; ++i) {
      long word = bitmap[i];
      if (word == -1L) {
        wordConsumer.acceptWord(i, word);
      } else {
        while (word != 0) {
          intConsumer.accept(Long.SIZE * i + Long.numberOfTrailingZeros(word));
          word ^= Long.lowestOneBit(word);
        }
      }
    }
  }

  @Benchmark
  public int reduceWithWordConsumer() {
    int[] result = new int[1];
    forEach(bitmap, i -> result[0] += data[i], (index, word) -> {
      if (word != -1L) {
        throw new IllegalStateException();
      }
      int sum = 0;
      for (int i = index * Long.SIZE; i < (index + 1) * Long.SIZE; ++i) {
        sum += data[i];
      }
      result[0] += sum;
    });
    return result[0];
  }
```

This really pays off when the bitset is full, but having that extra branch does seem to cost something even though it is never taken, whereas the full case improves 6x. 

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th>Benchmark</th>
<th>Mode</th>
<th>Threads</th>
<th>Samples</th>
<th>Score</th>
<th>Score Error (99.9%)</th>
<th>Unit</th>
<th>Param: scenario</th>
</tr></thead>
<tbody><tr>
<td>reduce</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">7.401202</td>
<td align="right">0.118648</td>
<td>ops/ms</td>
<td>FULL</td>
</tr>
<tr>
<td>reduce</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">261.682016</td>
<td align="right">4.155856</td>
<td>ops/ms</td>
<td>ONE_BIT_PER_WORD</td>
</tr>
<tr>
<td>reduceWithWordConsumer</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">43.972759</td>
<td align="right">0.993264</td>
<td>ops/ms</td>
<td>FULL</td>
</tr>
<tr>
<td>reduceWithWordConsumer</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">222.824868</td>
<td align="right">4.877147</td>
<td>ops/ms</td>
<td>ONE_BIT_PER_WORD</td>
</tr>
</tbody></table>
</div>

We still don't actually know the cost of the branch when it's taken every now and then. To estimate it, we need a new scenario (or new scenarios) which mix full and sparse words. As you might expect, having the `WordConsumer` is great when one word in every few is full: the fast path is so much faster, it practically skips the word.

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th>Benchmark</th>
<th>Mode</th>
<th>Threads</th>
<th>Samples</th>
<th>Score</th>
<th>Score Error (99.9%)</th>
<th>Unit</th>
<th>Param: scenario</th>
</tr></thead>
<tbody><tr>
<td>reduce</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">157.358633</td>
<td align="right">4.538679</td>
<td>ops/ms</td>
<td>SPARSE_16_FULL_WORDS</td>
</tr>
<tr>
<td>reduceWithWordConsumer</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">257.041035</td>
<td align="right">7.446404</td>
<td>ops/ms</td>
<td>SPARSE_16_FULL_WORDS</td>
</tr>
</tbody></table>
</div>

So in this scenario, the branch has paid for itself. How? The data dependency has been removed with a countable loop. Here's the perfasm output. Notice two things: long runs of `add` instructions, and the vastly reduced percentage against `blsi`. The time is now spent adding numbers up, not switching off least significant bits. This feels like progress.


```asm
  0.05%    0x000001dd5b35af03: add     ebx,dword ptr [rdi+r9*4+10h]
  0.31%    0x000001dd5b35af08: add     ebx,dword ptr [rdi+r11*4+14h]
  0.32%    0x000001dd5b35af0d: add     ebx,dword ptr [rdi+r11*4+18h]
  0.33%    0x000001dd5b35af12: add     ebx,dword ptr [rdi+r11*4+1ch]
  0.37%    0x000001dd5b35af17: add     ebx,dword ptr [rdi+r11*4+20h]
  0.34%    0x000001dd5b35af1c: add     ebx,dword ptr [rdi+r11*4+24h]
  0.39%    0x000001dd5b35af21: add     ebx,dword ptr [rdi+r11*4+28h]
  0.36%    0x000001dd5b35af26: add     ebx,dword ptr [rdi+r11*4+2ch]
  0.34%    0x000001dd5b35af2b: add     ebx,dword ptr [rdi+r11*4+30h]
  0.35%    0x000001dd5b35af30: add     ebx,dword ptr [rdi+r11*4+34h]
  0.38%    0x000001dd5b35af35: add     ebx,dword ptr [rdi+r11*4+38h]
  0.36%    0x000001dd5b35af3a: add     ebx,dword ptr [rdi+r11*4+3ch]
  0.49%    0x000001dd5b35af3f: add     ebx,dword ptr [rdi+r11*4+40h]
  0.39%    0x000001dd5b35af44: add     ebx,dword ptr [rdi+r11*4+44h]
  0.42%    0x000001dd5b35af49: add     ebx,dword ptr [rdi+r11*4+48h]
  0.39%    0x000001dd5b35af4e: add     ebx,dword ptr [rdi+r11*4+4ch]
...
  2.39%    0x000001dd5b35afe9: tzcnt   r11,rbx
  2.65%    0x000001dd5b35afee: add     r11d,r10d         
  2.15%    0x000001dd5b35aff1: cmp     r11d,r9d
  0.00%    0x000001dd5b35aff4: jnb     1dd5b35b04dh
  2.29%    0x000001dd5b35aff6: add     r8d,dword ptr [rdi+r11*4+10h]
 11.03%    0x000001dd5b35affb: vmovq   r11,xmm0
  2.45%    0x000001dd5b35b000: mov     dword ptr [r11+10h],r8d  
  3.14%    0x000001dd5b35b004: mov     r11,qword ptr [r15+70h]
  2.18%    0x000001dd5b35b008: blsi    r8,rbx
  2.23%    0x000001dd5b35b00d: xor     rbx,r8
```

Heroically ploughing through the full words tells a different story: `blsi` is up at 11%. This indicates more time is spent iterating rather than evaluating the callback.

```asm
  6.98%    0x0000019f106c6799: tzcnt   r9,rdi
  3.47%    0x0000019f106c679e: add     r9d,ebx           
  1.65%    0x0000019f106c67a1: cmp     r9d,r10d
           0x0000019f106c67a4: jnb     19f106c67cdh
  1.67%    0x0000019f106c67a6: add     r11d,dword ptr [r8+r9*4+10h]
 11.45%    0x0000019f106c67ab: vmovq   r9,xmm2
  3.20%    0x0000019f106c67b0: mov     dword ptr [r9+10h],r11d  
 11.31%    0x0000019f106c67b4: blsi    r11,rdi
  1.71%    0x0000019f106c67b9: xor     rdi,r11           
```

This shows the cost of a data dependency in a loop. The operation we want to perform is associative, so we could even vectorise this. In C++ that might happen automatically, or could be ensured with intrinsics, but C2 has various heuristics: it won't try to vectorise a simple reduction, and 64 would probably be on the short side for most cases it would try to vectorise.

<h3>Acknowledging Runs</h3>

You might be tempted to transfer even more control to the callback, by accumulating runs and then calling the callback once per run. It simplifies the code to exclude incomplete start and end words from the run.


```java
private interface RunConsumer {
    void acceptRun(int start, int end);
  }

  public void forEach(long[] bitmap, IntConsumer intConsumer, RunConsumer runConsumer) {
    int runStart = -1;
    for (int i = 0; i < bitmap.length; ++i) {
      long word = bitmap[i];
      if (word == -1L) {
        if (runStart == -1) {
          runStart = i;
        }
      } else {
        if (runStart != -1) {
          runConsumer.acceptRun(runStart * Long.SIZE, i * Long.SIZE);
          runStart = -1;
        }
        while (word != 0) {
          intConsumer.accept(Long.SIZE * i + Long.numberOfTrailingZeros(word));
          word ^= Long.lowestOneBit(word);
        }
      }
    }
    if (runStart != -1) {
      runConsumer.acceptRun(runStart * Long.SIZE, bitmap.length * Long.SIZE);
    }
  }
```

For a simple reduction, the extra complexity isn't justified: you're better off with the `WordIterator`.

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th>Benchmark</th>
<th>Mode</th>
<th>Threads</th>
<th>Samples</th>
<th>Score</th>
<th>Score Error (99.9%)</th>
<th>Unit</th>
<th>Param: scenario</th>
</tr></thead>
<tbody><tr>
<td>reduce</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">160.502749</td>
<td align="right">2.960568</td>
<td>ops/ms</td>
<td>SPARSE_16_FULL_WORDS</td>
</tr>
<tr>
<td>reduce</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">7.294747</td>
<td align="right">0.186678</td>
<td>ops/ms</td>
<td>FULL</td>
</tr>
<tr>
<td>reduce</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">258.064511</td>
<td align="right">8.902233</td>
<td>ops/ms</td>
<td>ONE_BIT_PER_WORD</td>
</tr>
<tr>
<td>reduce</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">159.613877</td>
<td align="right">3.424432</td>
<td>ops/ms</td>
<td>SPARSE_1_16_WORD_RUN</td>
</tr>
<tr>
<td>reduceWithRunConsumer</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">251.683131</td>
<td align="right">6.799639</td>
<td>ops/ms</td>
<td>SPARSE_16_FULL_WORDS</td>
</tr>
<tr>
<td>reduceWithRunConsumer</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">37.809154</td>
<td align="right">0.723198</td>
<td>ops/ms</td>
<td>FULL</td>
</tr>
<tr>
<td>reduceWithRunConsumer</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">218.133560</td>
<td align="right">13.756779</td>
<td>ops/ms</td>
<td>ONE_BIT_PER_WORD</td>
</tr>
<tr>
<td>reduceWithRunConsumer</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">140.896826</td>
<td align="right">8.495777</td>
<td>ops/ms</td>
<td>SPARSE_1_16_WORD_RUN</td>
</tr>
<tr>
<td>reduceWithWordConsumer</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">257.961783</td>
<td align="right">5.892072</td>
<td>ops/ms</td>
<td>SPARSE_16_FULL_WORDS</td>
</tr>
<tr>
<td>reduceWithWordConsumer</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">43.909471</td>
<td align="right">0.601319</td>
<td>ops/ms</td>
<td>FULL</td>
</tr>
<tr>
<td>reduceWithWordConsumer</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">213.731758</td>
<td align="right">20.398077</td>
<td>ops/ms</td>
<td>ONE_BIT_PER_WORD</td>
</tr>
<tr>
<td>reduceWithWordConsumer</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">258.280428</td>
<td align="right">11.316647</td>
<td>ops/ms</td>
<td>SPARSE_1_16_WORD_RUN</td>
</tr>
</tbody></table>
</div>

It's simplistic to measure this and conclude that this is a bad approach though. There are several other dimensions to this problem:

<ol>
	<li>Vectorised callbacks</li>
	<li>Inlining failures preventing optimisations</li>
	<li>The number of runs and their lengths (i.e. your data and how you structure it)</li>
</ol>

<h3>Vectorisable Callbacks</h3>

There are real benefits to batching up callbacks if the workload in the callback can be vectorised. The code doesn't need to get much more complicated to start benefitting from larger iteration batches. Mapping each bit to a scaled and squared value from the data array and storing it into an output array illustrates this.

```java
  @Benchmark
  public void map(Blackhole bh) {
    forEach(bitmap, i -> output[i] = data[i] * data[i] * factor);
    bh.consume(output);
  }

  @Benchmark
  public void mapWithWordConsumer(Blackhole bh) {
    forEach(bitmap, i -> output[0] = data[i] * factor, (WordConsumer) (index, word) -> {
      if (word != -1L) {
        throw new IllegalStateException();
      }
      for (int i = index * Long.SIZE; i < (index + 1) * Long.SIZE; ++i) {
        output[i] = data[i] * data[i] * factor;
      }
    });
    bh.consume(output);
  }

  @Benchmark
  public void mapWithRunConsumer(Blackhole bh) {
    forEach(bitmap, i -> output[0] = data[i] * factor, (RunConsumer) (start, end) -> {
      for (int i = start; i < end; ++i) {
        output[i] = data[i] * data[i] * factor;
      }
    });
    bh.consume(output);
  }
```

The `RunConsumer` does much better in the full case, never much worse than the `WordConsumer` and always better than the basic strategy - even when there is only one run in the entire bitset, or when there are a few full words in an otherwise sparse bitset.

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th>Benchmark</th>
<th>Mode</th>
<th>Threads</th>
<th>Samples</th>
<th>Score</th>
<th>Score Error (99.9%)</th>
<th>Unit</th>
<th>Param: scenario</th>
</tr></thead>
<tbody><tr>
<td>map</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">127.876662</td>
<td align="right">3.411741</td>
<td>ops/ms</td>
<td>SPARSE_16_FULL_WORDS</td>
</tr>
<tr>
<td>map</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">10.598974</td>
<td align="right">0.022404</td>
<td>ops/ms</td>
<td>FULL</td>
</tr>
<tr>
<td>map</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">126.434666</td>
<td align="right">18.608547</td>
<td>ops/ms</td>
<td>ONE_BIT_PER_WORD</td>
</tr>
<tr>
<td>map</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">115.977840</td>
<td align="right">20.449258</td>
<td>ops/ms</td>
<td>SPARSE_1_16_WORD_RUN</td>
</tr>
<tr>
<td>mapWithRunConsumer</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">199.186167</td>
<td align="right">8.138446</td>
<td>ops/ms</td>
<td>SPARSE_16_FULL_WORDS</td>
</tr>
<tr>
<td>mapWithRunConsumer</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">64.230868</td>
<td align="right">2.871434</td>
<td>ops/ms</td>
<td>FULL</td>
</tr>
<tr>
<td>mapWithRunConsumer</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">219.963063</td>
<td align="right">4.257561</td>
<td>ops/ms</td>
<td>ONE_BIT_PER_WORD</td>
</tr>
<tr>
<td>mapWithRunConsumer</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">203.403804</td>
<td align="right">6.907366</td>
<td>ops/ms</td>
<td>SPARSE_1_16_WORD_RUN</td>
</tr>
<tr>
<td>mapWithWordConsumer</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">229.822235</td>
<td align="right">5.276084</td>
<td>ops/ms</td>
<td>SPARSE_16_FULL_WORDS</td>
</tr>
<tr>
<td>mapWithWordConsumer</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">48.381990</td>
<td align="right">3.845642</td>
<td>ops/ms</td>
<td>FULL</td>
</tr>
<tr>
<td>mapWithWordConsumer</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">218.907803</td>
<td align="right">5.331011</td>
<td>ops/ms</td>
<td>ONE_BIT_PER_WORD</td>
</tr>
<tr>
<td>mapWithWordConsumer</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">240.795280</td>
<td align="right">10.204818</td>
<td>ops/ms</td>
<td>SPARSE_1_16_WORD_RUN</td>
</tr>
</tbody></table>
</div>

This is simply because the callback was vectorised, and the style of the `RunConsumer` API allows this to be exploited. This can be seen with perfasm. Both the `WordConsumer` and `RunConsumer` are actually vectorised, but the thing to notice is that there are two hot regions in the WordConsumer benchmark: the iteration and the callback, this boundary is often crossed. On the other hand, the RunConsumer implementation spends most of its time in the callback.

<h5>WordConsumer</h5>
```asm
....[Hottest Region 1]..............................................................................
c2, com.openkappa.simd.iterate.generated.BitSetIterator_mapWithWordConsumer_jmhTest::mapWithWordConsumer_thrpt_jmhStub, version 172 (227 bytes) 
...
  1.55%    0x000001c2aa13c790: vmovdqu ymm1,ymmword ptr [r9+r10*4+10h]
  0.15%    0x000001c2aa13c797: vpmulld ymm1,ymm1,ymm1
  3.72%    0x000001c2aa13c79c: vpmulld ymm1,ymm1,ymm2
 16.02%    0x000001c2aa13c7a1: vmovdqu ymmword ptr [rdx+r10*4+10h],ymm1
  1.69%    0x000001c2aa13c7a8: movsxd  r8,r10d
  1.55%    0x000001c2aa13c7ab: vmovdqu ymm1,ymmword ptr [r9+r8*4+30h]
  1.46%    0x000001c2aa13c7b2: vpmulld ymm1,ymm1,ymm1
  1.71%    0x000001c2aa13c7b7: vpmulld ymm1,ymm1,ymm2
  3.20%    0x000001c2aa13c7bc: vmovdqu ymmword ptr [rdx+r8*4+30h],ymm1
  0.07%    0x000001c2aa13c7c3: add     r10d,10h          
  1.70%    0x000001c2aa13c7c7: cmp     r10d,r11d
           0x000001c2aa13c7ca: jl      1c2aa13c790h      
  0.02%    0x000001c2aa13c7cc: mov     r8,qword ptr [r15+70h]  
  1.50%    0x000001c2aa13c7d0: test    dword ptr [r8],eax  
  0.04%    0x000001c2aa13c7d3: cmp     r10d,r11d
           0x000001c2aa13c7d6: jl      1c2aa13c78ah
  0.05%    0x000001c2aa13c7d8: mov     r11d,dword ptr [rsp+5ch]
  0.02%    0x000001c2aa13c7dd: add     r11d,39h
  1.57%    0x000001c2aa13c7e1: mov     r8d,ecx
  0.02%    0x000001c2aa13c7e4: cmp     r8d,r11d
  0.06%    0x000001c2aa13c7e7: mov     ecx,80000000h
  0.02%    0x000001c2aa13c7ec: cmovl   r11d,ecx
  1.50%    0x000001c2aa13c7f0: cmp     r10d,r11d
           0x000001c2aa13c7f3: jnl     1c2aa13c819h
  0.02%    0x000001c2aa13c7f5: nop                       
  0.06%    0x000001c2aa13c7f8: vmovdqu ymm1,ymmword ptr [r9+r10*4+10h]
  0.21%    0x000001c2aa13c7ff: vpmulld ymm1,ymm1,ymm1
  2.16%    0x000001c2aa13c804: vpmulld ymm1,ymm1,ymm2
  1.80%    0x000001c2aa13c809: vmovdqu ymmword ptr [rdx+r10*4+10h],ymm1
...
 53.26%  <total for region 1>
```

<h5>RunConsumer</h5>
```asm
....[Hottest Region 1]..............................................................................
c2, com.openkappa.simd.iterate.BitSetIterator$$Lambda$44.1209658195::acceptRun, version 166 (816 bytes) 
...
  0.92%    0x0000016658954860: vmovdqu ymm0,ymmword ptr [rdx+r8*4+10h]
  1.31%    0x0000016658954867: vpmulld ymm0,ymm0,ymm0
  1.74%    0x000001665895486c: vpmulld ymm0,ymm0,ymm1
  4.55%    0x0000016658954871: vmovdqu ymmword ptr [rdi+r8*4+10h],ymm0
  0.69%    0x0000016658954878: movsxd  rcx,r8d
  0.01%    0x000001665895487b: vmovdqu ymm0,ymmword ptr [rdx+rcx*4+30h]
  0.41%    0x0000016658954881: vpmulld ymm0,ymm0,ymm0
  0.78%    0x0000016658954886: vpmulld ymm0,ymm0,ymm1
  0.83%    0x000001665895488b: vmovdqu ymmword ptr [rdi+rcx*4+30h],ymm0
  0.25%    0x0000016658954891: vmovdqu ymm0,ymmword ptr [rdx+rcx*4+50h]
  1.29%    0x0000016658954897: vpmulld ymm0,ymm0,ymm0
  1.51%    0x000001665895489c: vpmulld ymm0,ymm0,ymm1
  3.65%    0x00000166589548a1: vmovdqu ymmword ptr [rdi+rcx*4+50h],ymm0
  0.54%    0x00000166589548a7: vmovdqu ymm0,ymmword ptr [rdx+rcx*4+70h]
  0.31%    0x00000166589548ad: vpmulld ymm0,ymm0,ymm0
  0.47%    0x00000166589548b2: vpmulld ymm0,ymm0,ymm1
  1.11%    0x00000166589548b7: vmovdqu ymmword ptr [rdi+rcx*4+70h],ymm0
  0.28%    0x00000166589548bd: vmovdqu ymm0,ymmword ptr [rdx+rcx*4+90h]
  1.17%    0x00000166589548c6: vpmulld ymm0,ymm0,ymm0
  1.89%    0x00000166589548cb: vpmulld ymm0,ymm0,ymm1
  3.56%    0x00000166589548d0: vmovdqu ymmword ptr [rdi+rcx*4+90h],ymm0
  0.73%    0x00000166589548d9: vmovdqu ymm0,ymmword ptr [rdx+rcx*4+0b0h]
  0.21%    0x00000166589548e2: vpmulld ymm0,ymm0,ymm0
  0.34%    0x00000166589548e7: vpmulld ymm0,ymm0,ymm1
  1.29%    0x00000166589548ec: vmovdqu ymmword ptr [rdi+rcx*4+0b0h],ymm0
  0.33%    0x00000166589548f5: vmovdqu ymm0,ymmword ptr [rdx+rcx*4+0d0h]
  0.97%    0x00000166589548fe: vpmulld ymm0,ymm0,ymm0
  1.90%    0x0000016658954903: vpmulld ymm0,ymm0,ymm1
  3.59%    0x0000016658954908: vmovdqu ymmword ptr [rdi+rcx*4+0d0h],ymm0
  0.82%    0x0000016658954911: vmovdqu ymm0,ymmword ptr [rdx+rcx*4+0f0h]
  0.18%    0x000001665895491a: vpmulld ymm0,ymm0,ymm0
  0.29%    0x000001665895491f: vpmulld ymm0,ymm0,ymm1
  1.25%    0x0000016658954924: vmovdqu ymmword ptr [rdi+rcx*4+0f0h],ymm0
  0.33%    0x000001665895492d: vmovdqu ymm0,ymmword ptr [rdx+rcx*4+110h]
  1.10%    0x0000016658954936: vpmulld ymm0,ymm0,ymm0
  2.11%    0x000001665895493b: vpmulld ymm0,ymm0,ymm1
  3.67%    0x0000016658954940: vmovdqu ymmword ptr [rdi+rcx*4+110h],ymm0
  0.93%    0x0000016658954949: vmovdqu ymm0,ymmword ptr [rdx+rcx*4+130h]
  0.13%    0x0000016658954952: vpmulld ymm0,ymm0,ymm0
  0.25%    0x0000016658954957: vpmulld ymm0,ymm0,ymm1
  1.35%    0x000001665895495c: vmovdqu ymmword ptr [rdi+rcx*4+130h],ymm0
  0.32%    0x0000016658954965: vmovdqu ymm0,ymmword ptr [rdx+rcx*4+150h]
  0.93%    0x000001665895496e: vpmulld ymm0,ymm0,ymm0
  2.16%    0x0000016658954973: vpmulld ymm0,ymm0,ymm1
  3.73%    0x0000016658954978: vmovdqu ymmword ptr [rdi+rcx*4+150h],ymm0
  0.95%    0x0000016658954981: vmovdqu ymm0,ymmword ptr [rdx+rcx*4+170h]
  0.14%    0x000001665895498a: vpmulld ymm0,ymm0,ymm0
  0.21%    0x000001665895498f: vpmulld ymm0,ymm0,ymm1
  1.39%    0x0000016658954994: vmovdqu ymmword ptr [rdi+rcx*4+170h],ymm0
  0.29%    0x000001665895499d: vmovdqu ymm0,ymmword ptr [rdx+rcx*4+190h]
  1.42%    0x00000166589549a6: vpmulld ymm0,ymm0,ymm0
  2.61%    0x00000166589549ab: vpmulld ymm0,ymm0,ymm1
  4.42%    0x00000166589549b0: vmovdqu ymmword ptr [rdi+rcx*4+190h],ymm0
  1.01%    0x00000166589549b9: vmovdqu ymm0,ymmword ptr [rdx+rcx*4+1b0h]
  0.10%    0x00000166589549c2: vpmulld ymm0,ymm0,ymm0
  0.17%    0x00000166589549c7: vpmulld ymm0,ymm0,ymm1
  1.46%    0x00000166589549cc: vmovdqu ymmword ptr [rdi+rcx*4+1b0h],ymm0
  0.27%    0x00000166589549d5: vmovdqu ymm0,ymmword ptr [rdx+rcx*4+1d0h]
 13.60%    0x00000166589549de: vpmulld ymm0,ymm0,ymm0
  3.51%    0x00000166589549e3: vpmulld ymm0,ymm0,ymm1
  4.69%    0x00000166589549e8: vmovdqu ymmword ptr [rdi+rcx*4+1d0h],ymm0
  1.00%    0x00000166589549f1: vmovdqu ymm0,ymmword ptr [rdx+rcx*4+1f0h]
  0.11%    0x00000166589549fa: vpmulld ymm0,ymm0,ymm0
  0.15%    0x00000166589549ff: vpmulld ymm0,ymm0,ymm1
  1.46%    0x0000016658954a04: vmovdqu ymmword ptr [rdi+rcx*4+1f0h],ymm0
                                                         
  0.26%    0x0000016658954a0d: add     r8d,80h           
  0.01%    0x0000016658954a14: cmp     r8d,r10d
           0x0000016658954a17: jl      16658954860h      
  0.00%    0x0000016658954a1d: mov     r14,qword ptr [r15+70h]  
  0.06%    0x0000016658954a21: test    dword ptr [r14],eax  
  0.17%    0x0000016658954a24: cmp     r8d,r10d
           0x0000016658954a27: jl      16658954860h
           0x0000016658954a2d: mov     r10d,r9d
           0x0000016658954a30: add     r10d,0fffffff9h
           0x0000016658954a34: cmp     r9d,r10d
  0.00%    0x0000016658954a37: cmovl   r10d,ebx
           0x0000016658954a3b: cmp     r8d,r10d
           0x0000016658954a3e: jnl     16658954a61h      
           0x0000016658954a40: vmovdqu ymm0,ymmword ptr [rdx+r8*4+10h]
  0.14%    0x0000016658954a47: vpmulld ymm0,ymm0,ymm0
  0.05%    0x0000016658954a4c: vpmulld ymm0,ymm0,ymm1
  0.03%    0x0000016658954a51: vmovdqu ymmword ptr [rdi+r8*4+10h],ymm0
...
 96.10%  <total for region 1>
```

My benchmarks are available at <a href="https://github.com/richardstartin/simdbenchmarks/blob/master/src/main/java/com/openkappa/simd/iterate/BitSetIterator.java">github</a>.