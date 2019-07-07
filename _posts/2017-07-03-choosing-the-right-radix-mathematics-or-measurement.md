---
title: "Choosing the Right Radix: Measurement or Mathematics?"
layout: post
date: 2017-07-03
---

I recently wrote a [post](https://richardstartin.github.io/posts/sorting-unsigned-integers-faster-in-java/) about radix sorting, and found that for large arrays of unsigned integers a handwritten implementation beats `Arrays.sort`. However, I paid no attention to the choice of radix and used a default of eight bits. It turns out this was a lucky choice: modifying my benchmark to parametrise the radix, I observed a maximum at one byte, regardless of the size of array.

Is this an algorithmic or technical phenomenon? Is this something that could have been predicted on the back of an envelope without running a benchmark? 

#### Extended Benchmark Results

Here are some benchmark results for various radices.

|Size|Radix|Score|Score Error (99.9%)|Unit|
|--- |--- |--- |--- |--- |
|100|2|135.559923|7.72397|ops/ms|
|100|4|262.854579|37.372678|ops/ms|
|100|8|345.038234|30.954927|ops/ms|
|100|16|7.717496|1.144967|ops/ms|
|1000|2|13.892142|1.522749|ops/ms|
|1000|4|27.712719|4.057162|ops/ms|
|1000|8|52.253497|4.761172|ops/ms|
|1000|16|7.656033|0.499627|ops/ms|
|10000|2|1.627354|0.186948|ops/ms|
|10000|4|3.620869|0.029128|ops/ms|
|10000|8|6.435789|0.610848|ops/ms|
|10000|16|3.703248|0.45177|ops/ms|
|100000|2|0.144575|0.014348|ops/ms|
|100000|4|0.281837|0.025707|ops/ms|
|100000|8|0.543274|0.031553|ops/ms|
|100000|16|0.533998|0.126949|ops/ms|
|1000000|2|0.011293|0.001429|ops/ms|
|1000000|4|0.021128|0.003137|ops/ms|
|1000000|8|0.037376|0.005783|ops/ms|
|1000000|16|0.031053|0.007987|ops/ms|

#### Modeling

To model the execution time of the algorithm, we can write $latex t = f(r, n)$, where $latex n \in \mathbb{N}$ is the length of the input array, and `r ∈ [1, 32)` is the size in bits of the radix. We can inspect if the model predicts non-monotonic execution time with a minimum (corresponding to maximal throughput), or if `t` increases indefinitely as a function of `r`. If we find a plausible model predicting a minimum, temporarily treating $latex r$ as continuous, we can solve `df/dr|{n=N, r ∈ [1,32)} = 0` to find the theoretically optimal radix. This pre-supposes we derive a non-monotonic model.

#### Constructing a Model

We need to write down an equation before we can do any calculus, which requires two dangerous assumptions.


1. Each operation has the same cost, making the execution time proportional to the number of operation.
2. The costs of operations do not vary as a function of `n` or `r`.


This means all we need to do is find a formula for the number of operations, and then vary $latex n$ and $latex r$. The usual pitfall in this approach relates to the first assumption, in that memory accesses are modelled as uniform cost; memory access can vary widely in cost ranging from registers to RAM on another socket. We are about to fall foul of both assumptions constructing an intuitive model of the algorithm's loop.

```java
        while (shift < Integer.SIZE) {
            Arrays.fill(histogram, 0);
            for (int i = 0; i < data.length; ++i) {
                ++histogram[((data[i] & mask) >> shift) + 1];
            }
            for (int i = 0; i < 1 << radix; ++i) {
                histogram[i + 1] += histogram[i];
            }
            for (int i = 0; i < data.length; ++i) {
                copy[histogram[(data[i] & mask) >> shift]++] = data[i];
            }
            for (int i = 0; i < data.length; ++i) {
                data[i] = copy[i];
            }
            shift += radix;
            mask <<= radix;
        }
```

The outer loop depends on the choice of radix while the inner loops depend on the size of the array and the choice of radix. There are five obvious aspects to capture:


* The first inner loop takes time proportional to `n`
* The third and fourth inner loops take time proportional to `n`
* We can factor the per-element costs of loops 1, 3 and 4 into a constant `a`
* The second inner loop takes time proportional to `2^r`, modeled with by the term `b2^r`
* The body of the loop executes `32/r` times


This can be summarised as the formula: 

`f(r, n) = 32(3an + b2^r)/r`

It was claimed the algorithm had linear complexity in `n` and it only has a linear term in `n`. Good. However, the exponential `r` term in the numerator dominates the linear term in the denominator, making the function monotonic in `r`. The model fails to predict the observed throughput maximising radix. <em>There are clearly much more complicated mechanisms at play than can be captured counting operations.</em>
