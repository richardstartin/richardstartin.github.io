---
title: "How much Algebra does C2 Know? Part 1: Associativity"
layout: post

date: 2017-08-12
redirect_from:
  - /how-much-algebra-does-c2-know-part-1-associativity/
---

Making loops execute faster is firmly rooted in algebra, but how much does C2 know or care about? When building a highly optimised query engine, a critical concern is the quality of assembly code generated for loops. There is a lot more to JIT compilation than loop optimisation; inlining, class hierarchy analysis, escape analysis to name but a few. Moreover, everything it does has to be fast since it shares resources with the application itself; it can't spend time unless it brings a net benefit. Being such a generalist, does C2, the JIT compiler used in server applications, know high school algebra?

Specific knowledge of maths is not always worthwhile to program execution, even when it leads to high performance gains. As a motivating example, there is no way to refer directly to the natural numbers in any programming language I have ever used. For instance, the sum of the first `n` natural numbers is `((n+1) * n)/2`, and most high school students know it. This expression is intuitively much faster to evaluate than the equivalent algorithm:

```java
int sum(int n) {
    int total = 0;
    for (int i = 0; i <= n; ++i) {
        total += i;
    }
    return total;
}
```

But would this loop rewrite be a worthwhile optimisation? The expression takes about 3.5ns to compute the sum of the first million natural numbers, whereas the loop takes 350µs, so we can conclude that C2 does not know this formula and prefers brute force. I would be aghast if time had been spent on optimisations like this: unless your application spends a lot of time adding up contiguous ranges of natural numbers, the marginal benefit is negligible. If this is what your application does most, you should do it yourself. The possibility of an optimisation doesn't imply its viability: there needs to be a benefit when considering engineering effort, speed improvement, reliability and ubiquity. While this optimisation fails miserably on the grounds of ubiquity, there's <em>useful</em> schoolboy maths that C2 does seem to know.

<h3>Associativity and Dependencies</h3>

Each x86 instruction has a <strong>throughput</strong> - the number of cycles it takes to complete - and a <strong>latency</strong> - the number of cycles it takes before the result is available to the next instruction in a chain. These numbers are produced by processor vendors, but there are independent numbers like <a href="http://www.agner.org/optimize/instruction_tables.pdf" target="_blank">these from Agner Fog</a>, which also includes more detailed definitions of terms like latency. At first, the latency number feels a bit like a scam: what use is an advertised throughput if we can't use the result immediately? This is where <a href="https://en.wikipedia.org/wiki/Instruction_pipelining" target="_blank">pipelining</a> comes in: independent instructions can be interleaved. If a loop operation is <a href="https://en.wikipedia.org/wiki/Associative_property" target="_blank">associative</a> and there are no dependencies between iterations, then it can be unrolled, which enables pipelining. If a loop operation is also commutative, then <em>out of order execution</em> is permitted. Evidence of an unrolled loop suggests that the compiler has realised that an operation is at least associative.

To see this in action it's necessary to find an associative loop reduction that the compiler can't vectorise. I took an example from the <a href="http://roaringbitmap.org/" target="_blank">RoaringBitmap library</a> - computing the cardinality of a <a href="https://github.com/RoaringBitmap/RoaringBitmap/blob/master/src/main/java/org/roaringbitmap/BitmapContainer.java" target="_blank">bitmap container</a> - which is a perfect example to capture this behaviour, because <a href="https://richardstartin.com/2017/08/04/project-panama-and-population-count/" target="_blank">bit counts cannot be vectorised in Java</a>.

```java
  /**
   * Recomputes the cardinality of the bitmap.
   */
  protected void computeCardinality() {
    this.cardinality = 0;
    for (int k = 0; k < this.bitmap.length; k++) {
      this.cardinality += Long.bitCount(this.bitmap[k]);
    }
  }
  ```


we can see evidence of loop unrolling and out of order execution when looking at the assembly code emitted. The `popcnt` instructions are executed on the array out of order, and do not wait for the addition to the accumulator. 

```asm
popcnt  r9,qword ptr [rbx+r13*8+10h]

movsxd  r8,r13d

popcnt  r10,qword ptr [rbx+r8*8+28h]

popcnt  r11,qword ptr [rbx+r8*8+18h]

popcnt  rdx,qword ptr [rbx+r8*8+20h]
 
movsxd  r8,r9d

add     r8,rbp

movsxd  r9,edx
```

To generate this assembly code you can run the project at <a href="https://github.com/richardstartin/simdbenchmarks/blob/master/src/main/java/com/openkappa/simd/Launcher.java" target="_blank">github</a> with the arguments 

```
--include .*popcnt.* 
--print-assembly
```

The compiler does a very good job in this case: you can try unrolling the loop yourself, but you can only match performance if you guess the loop stride correctly. It's impossible to prove a negative proposition, but it's likely you'll only make it worse if you try. C2 graduates with flying colours here: it definitely understands associativity and dependence.

The catch with pipelining is that an instruction must always wait for its operands. While the operation is associative, there is no way to reorder the code below.

```java
    private int[] prefixSum(int[] data) {
        int[] result = new int[data.length];
        for (int i = 1; i < result.length; ++i) {
            result[i] = result[i - 1] + data[i];
        }
        return result;
    }
```

What happens with a prefix sum? There's no unrolling: you can see the loop control statements have not been removed (look for commands like <em>cmp ebx</em>, <em>inc ebx</em>). The loop is also executed in order because it is sequentially dependent.

```asm
  0x000001c21215bbc8: mov     r9d,dword ptr [r8+0ch]  
  0x000001c21215bbcc: mov     ebp,dword ptr [r13+rbx*4+0ch]
  0x000001c21215bbd1: cmp     ebx,r9d           
  0x000001c21215bbd4: jnb     1c21215bce1h      
  0x000001c21215bbda: add     ebp,dword ptr [r8+rbx*4+10h]
  0x000001c21215bbdf: cmp     ebx,edi          
```

Does this harm performance? `add` takes 0.33 cycles, whereas `popcnt` takes 1 cycle per instruction. Shouldn't a prefix sum be faster to calculate than a population count, on the same length of array and same width of integer? They can be compared head to head (implementing prefix sum for `long[]` to keep word width constant)

```
--include .*prefix.PrefixSum.PrefixSumLong|.*popcnt.PopCount.PopCount$
```

Far from having 3x throughput, the prefix sum is much worse. This is entirely because there is no loop unrolling and no pipelining. When possible, C2 applies aggressive unrolling optimisations unavailable to the programmer. For vectorisable operations (requiring linear independence and countability), loop unrolling further marks the loop as a candidate for auto-vectorisation.

<div class="table-holder" markdown="block">

|Benchmark|Mode|Threads|Samples|Score|Score Error (99.9%)|Unit|Param: size|
|--- |--- |--- |--- |--- |--- |--- |--- |
|PopCount|thrpt|1|10|9.174499|0.394487|ops/ms|100000|
|PopCount|thrpt|1|10|1.217521|0.513734|ops/ms|1000000|
|PrefixSumLong|thrpt|1|10|6.807279|0.925282|ops/ms|100000|
|PrefixSumLong|thrpt|1|10|0.443974|0.053544|ops/ms|1000000|

</div>

If the dependencies need to fetch data from RAM the latency can be much higher than loading from registers or from prefetched cache. Even when fetching from RAM, the worst case scenario, during this delay independent instructions can complete, unless they have a false dependency.
