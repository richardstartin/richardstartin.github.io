---
title: "Project Panama and Population Count"
layout: default

date: 2017-08-04
redirect_from:
  - /project-panama-and-population-count/
---

<a href="http://openjdk.java.net/projects/panama/" target="_blank" rel="noopener">Project Panama</a> introduces a new interface `Vector`, where the <a href="http://hg.openjdk.java.net/panama/panama/jdk/file/776788a90cf3/test/panama/vector-draft-spec/src/main/java/com/oracle/vector/Long256Vector.java" target="_blank" rel="noopener">specialisation</a> for `long` looks like a promising substrate for an explicitly vectorised bit set. Bit sets are useful for representing composable predicates over data sets. One obvious omission on this interface, required for an adequate implementation of a bit set, is a bit count, otherwise known as population count. Perhaps this is because the vector API aims to generalise across primitive types, whereas population count is only meaningful for integral types. Even so, if `Vector` can be interpreted as a wider integer, then it would be consistent to add this to the interface. If the method existed, what possible implementation could it have?

In x86, the population count of a 64 bit register is computed by the `POPCNT` instruction, which is exposed in Java as an intrinsic in `Long.bitCount`. There is no SIMD equivalent in any extension set until <a href="https://en.wikipedia.org/wiki/AVX-512#New_instructions_in_AVX-512_VPOPCNTDQ" target="_blank" rel="noopener">VPOPCNTD/VPOPCNTQ</a> in AVX-512. Very few processors (at the time of writing) support AVX-512, and only the Knights Mill processor supports this extension; there are not even <a href="https://software.intel.com/sites/landingpage/IntrinsicsGuide/#expand=3228&amp;techs=AVX_512" target="_blank" rel="noopener">Intel intrinsics</a> exposing these instructions yet.

The algorithm for vectorised population count adopted by the clang compiler is outlined in this <a href="https://arxiv.org/pdf/1611.07612.pdf" target="_blank" rel="noopener">paper</a>, which develops on an algorithm designed for 128 bit registers and SSE instructions, presented by Wojciech Muła on <a href="http://0x80.pl/articles/sse-popcount.html" target="_blank" rel="noopener">his blog</a> in 2008. This approach is shown in the paper to outperform scalar code using `POPCNT` and 64 bit registers, almost doubling throughput when 256 bit ymm registers are available. The core algorithm (taken from figure 10 in the paper) returns a vector of four 64 bit counts, which can then be added together in a variety of ways to form a population count, proceeds as follows:

```c
// The Muła Function
__m256i count(__m256i v) {
    __m256i lookup = _mm256_setr_epi8(
                 0, 1, 1, 2, 1, 2, 2, 3, 
                 1, 2, 2, 3, 2, 3, 3, 4,
                 0, 1, 1, 2, 1, 2, 2, 3,
                 1, 2, 2, 3, 2, 3, 3, 4);
    __m256i low_mask = _mm256_set1_epi8(0x0f);
    __m256i lo = _mm256_and_si256(v, low_mask);
    __m256i hi = _mm256_and_si256(_mm256_srli_epi32(v, 4), low_mask);
    __m256i popcnt1 = _mm256_shuffle_epi8(lookup, lo);
    __m256i popcnt2 = _mm256_shuffle_epi8(lookup, hi);
    __m256i total = _mm256_add_epi8(popcnt1, popcnt2);
    return _mm256_sad_epu8(total, _mm256_setzero_si256());
}
```

If you are struggling to read the code above, you are not alone. I haven't programmed in C++ for several years - it's amazing how nice the names in civilised languages like Java and python (and even bash) are compared to the black magic above. There is some logic to the naming though: read page 5 of <a href="https://software.intel.com/sites/default/files/a6/22/18072-347603.pdf" target="_blank" rel="noopener">the manual</a>. You can also read an accessible description of some of the functions used in this <a href="https://www.codeproject.com/Articles/874396/Crunching-Numbers-with-AVX-and-AVX" target="_blank" rel="noopener">blog post</a>.

The basic idea starts from storing the population counts for each possible byte value in a lookup table, which can be looked up using bit level parallelism and ultimately added up. For efficiency's sake, instead of bytes, 4 bit nibbles are used, which is why you only see numbers 0-4 in the lookup table. Various, occasionally obscure, optimisations are applied resulting in the magic numbers at the the top of the function. A large chunk of the paper is devoted to their derivation: if you are interested, go and read the paper - I could not understand the intent of the code at all until reading the paper twice, especially section 2.

The points I find interesting are:

* This algorithm exists.
* It uses instructions all modern commodity processors have.
* It is fast!
* It is in use.

Could this be implemented in the JVM as an intrinsic and exposed on `Vector`?
