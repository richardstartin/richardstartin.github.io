---
ID: 10927
title: Vectorised Algorithms in Java
author: Richard Startin
post_excerpt: ""
layout: post
redirect_from:
  - /vectorised-algorithms-in-java/
published: true
date: 2018-05-12 23:04:25
---
There has been a Cambrian explosion of JVM data technologies in recent years. It's all very exciting, but is the JVM really competitive with C in this area? I would argue that there is a reason Apache Arrow is polyglot, and it's not just interoperability with Python. To pick on one project impressive enough to be thriving after seven years, if you've actually used Apache Spark you will be aware that it looks fastest next to its predecessor, MapReduce. Big data is a lot like teenage sex: everybody talks about it, nobody really knows how to do it, and everyone keeps their embarrassing stories to themselves. In games of incomplete information, it's possible to overestimate the competence of others: nobody opens up about how slow their Spark jobs really are because there's a risk of looking stupid. 

If it can be accepted that Spark is inefficient, the question becomes is Spark <em>fundamentally</em> inefficient? <a href="https://arxiv.org/pdf/1703.08219.pdf" rel="noopener" target="_blank">Flare</a> provides a drop-in replacement for Spark's backend, but replaces JIT compiled code with highly efficient native code, yielding order of magnitude improvements in job throughput. Some of Flare's gains come from generating specialised code, but the rest comes from just generating better native code than C2 does. If Flare validates Spark's execution model, perhaps it raises questions about the suitability of the JVM for high throughput data processing. 

I think this will change radically in the coming years. I think the most important reason is the advent of explicit support for SIMD provided by the vector API, which is currently incubating in <a href="http://openjdk.java.net/projects/panama/" rel="noopener" target="_blank">Project Panama</a>. Once the vector API is complete, I conjecture that projects like Spark will be able to profit enormously from it. This post takes a look at the API in its current state and ignores performance.

<h3>Why Vectorisation?</h3>

Assuming a flat processor frequency, throughput is improved by a combination of executing many instructions per cycle (pipelining) and processing multiple data items per instruction (<em>SIMD</em>). SIMD instruction sets are provided by Intel as the various generations of <em>SSE</em> and <em>AVX</em>. If throughput is the only goal, maximising SIMD may even be worth reducing the frequency, which can happen on Intel chips when using AVX. <em>Vectorisation</em> allows throughput to be increased by the use of SIMD instructions. 

Analytical workloads are particularly suitable for vectorisation, especially over columnar data, because they typically involve operations consuming the entire range of a few numerical attributes of a data set. Vectorised analytical processing with filters is explicitly supported by vector masks, and vectorisation is also profitable for operations on indices typically performed for filtering prior to calculations. I don't actually need to make a strong case for the impact of vectorisation on analytical workloads: just read the work of top researchers like Daniel Abadi and Daniel Lemire. 

<h3>Vectorisation in the JVM</h3>

C2 provides quite a lot of <em>auto</em>vectorisation, which works very well sometimes, but the support is limited and brittle. I have written about this <a href="https://richardstartin.github.io/posts/tag/avx2" rel="noopener" target="_blank">several times</a>. Because AVX can reduce the processor frequency, it's not always profitable to vectorise, so compilers employ cost models to decide when they should do so. Such cost models require platform specific calibration, and sometimes <a href="https://bugs.openjdk.java.net/browse/JDK-8188313" rel="noopener" target="_blank">C2 can get it wrong</a>. Sometimes, specifically in the case of floating point operations, using SIMD conflicts with the JLS, and the code C2 generates can be quite inefficient. In general, data parallel code can be better optimised by C compilers, such as GCC, than C2 because there are fewer constraints, and there is a larger budget for analysis at compile time. This all makes having intrinsics very appealing, and as a user <em>I</em> would like to be able to:

<ol>
	<li>Bypass JLS floating point constraints.</li>
        <li>Bypass cost model based decisions.</li>
	<li>Avoid JNI at all costs.</li>
	<li>Use a modern "object-functional" style. SIMD intrinsics in C are painful.</li>
</ol>

There is another attempt to provide SIMD intrinsics to JVM users via LMS, a framework for writing programs which write programs, designed by <a href="https://twitter.com/tiarkrompf" rel="noopener" target="_blank">Tiark Rompf</a> (who is also behind Flare). This work is very promising (<a href="https://richardstartin.github.io/posts/multiplying-matrices-fast-and-slow/" rel="noopener" target="_blank">I have written about it before</a>), <strong>but it uses JNI</strong>. It's only at the prototype stage, but currently the intrinsics are auto-generated from XML definitions, which leads to a one-to-one mapping to the intrinsics in <em>immintrin.h</em>, yielding a similar programming experience. This could likely be improved a lot, but the reliance on JNI is fundamental, albeit with minimal boundary crossing.

I am quite excited by the vector API in Project Panama because it looks like it will meet all of these requirements, at least to some extent. It remains to be seen quite how far the implementors will go in the direction of associative floating point arithmetic, but it has to opt out of JLS floating point semantics to some extent, which I think is progressive. 

<h3>The Vector API</h3>

<blockquote>Disclaimer: Everything below is based on my experience with a recent build of the experimental code in the Project Panama fork of OpenJDK. I am not affiliated with the design or implementation of this API, may not be using it properly, and it may change according to its designers' will before it is released!</blockquote>

To understand the vector API you need to know that there are different register widths and different SIMD instruction sets. Because of my area of work, and 99% of the server market is Intel, I am only interested in AVX, but ARM have their own implementations with different maximum register sizes, which presumably need to be handled by a JVM vector API. On Intel CPUs, SSE instruction sets use up to 128 bit registers (<em>xmm</em>, four `int`s), AVX and AVX2 use up to 256 bit registers (<em>ymm</em>, eight `int`s), and AVX512 use up to 512 bit registers (<em>zmm</em>, sixteen `int`s).

The instruction sets are typed, and instructions designed to operate on packed `double`s can't operate on packed `int`s without explicit casting. This is modeled by the interface `Vector<Shape>`, parametrised by the `Shape` interface which models the register width.

The types of the vector elements is modeled by abstract element type specific classes such as `IntVector`. At the leaves of the hierarchy are the concrete classes specialised both to element type and register width, such as `IntVector256` which extends `IntVector<Shapes.S256Bit>`.

Since EJB, the word <em>factory</em> has been a dirty word, which might be why the word <em>species</em> is used in this API. To create a `IntVector<Shapes.S256Bit>`, you can create the factory/species as follows:

```java
public static final IntVector.IntSpecies<Shapes.S256Bit> YMM_INT =
          (IntVector.IntSpecies<Shapes.S256Bit>) Vector.species(int.class, Shapes.S_256_BIT);
```

There are now various ways to create a vector from the species, which all have their use cases. First, you can load vectors from arrays: imagine you want to calculate the bitwise intersection of two `int[]`s. This can be written quite cleanly, without any shape/register information.

```java
public static int[] intersect(int[] left, int[] right) {
    assert left.length == right.length;
    int[] result = new int[left.length];
    for (int i = 0; i < left.length; i += YMM_INT.length()) {
      YMM_INT.fromArray(left, i)
             .and(YMM_INT.fromArray(right, i))
             .intoArray(result, i);
    }
}
```

A common pattern in vectorised code is to <em>broadcast</em> a variable into a vector, for instance, to facilitate the multiplication of a vector by a scalar.

```java
IntVector<Shapes.S256Bit> multiplier = YMM_INT.broadcast(x);
```

Or to create a vector from some scalars, for instance in a lookup table.

```java
IntVector<Shapes.S256Bit> vector = YMM_INT.scalars(0, 1, 2, 3, 4, 5, 6, 7);
```

A zero vector can be created from a species: 
```java
IntVector<Shapes.S256Bit> zero = YMM_INT.zero();
```

The big split in the class hierarchy is between integral and floating point types. Integral types have meaningful bitwise operations (I am looking forward to trying to write a vectorised population count algorithm), which are absent from `FloatVector` and `DoubleVector`, and there is no concept of fused-multiply-add for integral types, so there is obviously no `IntVector.fma`. The common subset of operations is arithmetic, casting and loading/storing operations.

I generally like the API a lot: it feels familiar to programming with streams, but on the other hand, it isn't too far removed from traditional intrinsics. Below is an implementation of a fast matrix multiplication written in C, and below it is the same code written with the vector API:

```cpp
static void mmul_tiled_avx_unrolled(const int n, const float *left, const float *right, float *result) {
    const int block_width = n >= 256 ? 512 : 256;
    const int block_height = n >= 512 ? 8 : n >= 256 ? 16 : 32;
    for (int column_offset = 0; column_offset < n; column_offset += block_width) {
        for (int row_offset = 0; row_offset < n; row_offset += block_height) {
            for (int i = 0; i < n; ++i) {
                for (int j = column_offset; j < column_offset + block_width && j < n; j += 64) {
                    __m256 sum1 = _mm256_load_ps(result + i * n + j);
                    __m256 sum2 = _mm256_load_ps(result + i * n + j + 8);
                    __m256 sum3 = _mm256_load_ps(result + i * n + j + 16);
                    __m256 sum4 = _mm256_load_ps(result + i * n + j + 24);
                    __m256 sum5 = _mm256_load_ps(result + i * n + j + 32);
                    __m256 sum6 = _mm256_load_ps(result + i * n + j + 40);
                    __m256 sum7 = _mm256_load_ps(result + i * n + j + 48);
                    __m256 sum8 = _mm256_load_ps(result + i * n + j + 56);
                    for (int k = row_offset; k < row_offset + block_height && k < n; ++k) {
                        __m256 multiplier = _mm256_set1_ps(left[i * n + k]);
                        sum1 = _mm256_fmadd_ps(multiplier, _mm256_load_ps(right + k * n + j), sum1);
                        sum2 = _mm256_fmadd_ps(multiplier, _mm256_load_ps(right + k * n + j + 8), sum2);
                        sum3 = _mm256_fmadd_ps(multiplier, _mm256_load_ps(right + k * n + j + 16), sum3);
                        sum4 = _mm256_fmadd_ps(multiplier, _mm256_load_ps(right + k * n + j + 24), sum4);
                        sum5 = _mm256_fmadd_ps(multiplier, _mm256_load_ps(right + k * n + j + 32), sum5);
                        sum6 = _mm256_fmadd_ps(multiplier, _mm256_load_ps(right + k * n + j + 40), sum6);
                        sum7 = _mm256_fmadd_ps(multiplier, _mm256_load_ps(right + k * n + j + 48), sum7);
                        sum8 = _mm256_fmadd_ps(multiplier, _mm256_load_ps(right + k * n + j + 56), sum8);
                    }
                    _mm256_store_ps(result + i * n + j, sum1);
                    _mm256_store_ps(result + i * n + j + 8, sum2);
                    _mm256_store_ps(result + i * n + j + 16, sum3);
                    _mm256_store_ps(result + i * n + j + 24, sum4);
                    _mm256_store_ps(result + i * n + j + 32, sum5);
                    _mm256_store_ps(result + i * n + j + 40, sum6);
                    _mm256_store_ps(result + i * n + j + 48, sum7);
                    _mm256_store_ps(result + i * n + j + 56, sum8);
                }
            }
        }
    }
}
```

```java
  private static void mmul(int n, float[] left, float[] right, float[] result) {
    int blockWidth = n >= 256 ? 512 : 256;
    int blockHeight = n >= 512 ? 8 : n >= 256 ? 16 : 32;
    for (int columnOffset = 0; columnOffset < n; columnOffset += blockWidth) {
      for (int rowOffset = 0; rowOffset < n; rowOffset += blockHeight) {
        for (int i = 0; i < n; ++i) {
          for (int j = columnOffset; j < columnOffset + blockWidth && j < n; j += 64) {
            var sum1 = YMM_FLOAT.fromArray(result, i * n + j);
            var sum2 = YMM_FLOAT.fromArray(result, i * n + j + 8);
            var sum3 = YMM_FLOAT.fromArray(result, i * n + j + 16);
            var sum4 = YMM_FLOAT.fromArray(result, i * n + j + 24);
            var sum5 = YMM_FLOAT.fromArray(result, i * n + j + 32);
            var sum6 = YMM_FLOAT.fromArray(result, i * n + j + 40);
            var sum7 = YMM_FLOAT.fromArray(result, i * n + j + 48);
            var sum8 = YMM_FLOAT.fromArray(result, i * n + j + 56);
            for (int k = rowOffset; k < rowOffset + blockHeight && k < n; ++k) {
              var multiplier = YMM_FLOAT.broadcast(left[i * n + k]);
              sum1 = multiplier.fma(YMM_FLOAT.fromArray(right, k * n + j), sum1);
              sum2 = multiplier.fma(YMM_FLOAT.fromArray(right, k * n + j + 8), sum2);
              sum3 = multiplier.fma(YMM_FLOAT.fromArray(right, k * n + j + 16), sum3);
              sum4 = multiplier.fma(YMM_FLOAT.fromArray(right, k * n + j + 24), sum4);
              sum5 = multiplier.fma(YMM_FLOAT.fromArray(right, k * n + j + 32), sum5);
              sum6 = multiplier.fma(YMM_FLOAT.fromArray(right, k * n + j + 40), sum6);
              sum7 = multiplier.fma(YMM_FLOAT.fromArray(right, k * n + j + 48), sum7);
              sum8 = multiplier.fma(YMM_FLOAT.fromArray(right, k * n + j + 56), sum8);
            }
            sum1.intoArray(result, i * n + j);
            sum2.intoArray(result, i * n + j + 8);
            sum3.intoArray(result, i * n + j + 16);
            sum4.intoArray(result, i * n + j + 24);
            sum5.intoArray(result, i * n + j + 32);
            sum6.intoArray(result, i * n + j + 40);
            sum7.intoArray(result, i * n + j + 48);
            sum8.intoArray(result, i * n + j + 56);
          }
        }
      }
    }
  }
```

They just aren't that different, and it's easy to translate between the two. I wouldn't expect it to be fast yet though. I have no idea what the scope of work involved in implementing all of the C2 intrinsics to make this possible is, but I assume it's vast. The class `jdk.incubator.vector.VectorIntrinsics` seems to contain all of the intrinsics implemented so far, and it doesn't contain every operation used in my array multiplication code. There is also the question of value types and vector box elimination. I will probably look at this again in the future when more of the JIT compiler work has been done, but I'm starting to get very excited about the possibility of much faster JVM based data processing.

<blockquote>
I have written various benchmarks for useful analytical subroutines using the Vector API at <a href="https://github.com/richardstartin/vectorbenchmarks/tree/master/src/main/java/com/openkappa/panama/vectorbenchmarks" rel="noopener" target="_blank">github</a>.
</blockquote>