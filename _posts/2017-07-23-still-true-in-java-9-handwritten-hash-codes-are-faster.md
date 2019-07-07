---
title: "Still True in Java 9: Handwritten Hash Codes are Faster"
layout: post
theme: minimal
date: 2017-07-23
---

One of the things to keep in mind with Java is that the best performance advice for one version may not apply to the next. The JVM has an optimiser which works by detecting intent in byte-code; it does a better job when the programmer is skilled enough to make that intent clear. There have been times when the optimiser has done a bad job, either through bugs or feature gaps, and compensatory idioms emerge. The value of these idioms degrades over time as the optimiser improves; a stroke of ingenuity in one version can become ritualistic nonsense in the next. It's important not to be <em>that guy</em> who fears adding strings together because it was costly a decade ago, but does it always get better, even with low hanging fruit?

I reproduced the results of an [extremely astute optimisation](http://lemire.me/blog/2015/10/22/faster-hashing-without-effort/) presented in 2015 by Daniel Lemire. I was hoping to see that an improved optimiser in Java 9, having observed several cases of automatic vectorisation, would render this optimisation null. 

#### Hash Codes for Arrays

I encourage you to read the [original blog post](http://lemire.me/blog/2015/10/22/faster-hashing-without-effort) because it is informative, but for the sake of coherence I will summarise the key point here. `Arrays.hashCode` implements the following hash code:

```java
    public static int hashCode(int[] a) {
        if (a == null)
            return 0;

        int result = 1;
        for (int element : a)
            result = 31 * result + element;

        return result;
    }
```

This results in a good hash code, but a scalar internal representation of this code has a problem: a data dependency on the multiplication, which is slower than moving data into registers. A significant and reproducible speed up can be observed when unrolling the loop, which allows prefetching 128 bits of the array into registers before doing the slower multiplications:

```java
    public static int hashCode(int[] a) {
        if (a == null)
            return 0;

        int result = 1;
        int i = 0;
        for (; i + 3 < a.length; i += 4) {
            result = 31 * 31 * 31 * 31 * result
                   + 31 * 31 * 31 * a[i]
                   + 31 * 31 * a[i + 1]
                   + 31 * a[i + 2]
                   + a[i + 3];
        }
        for (; i < a.length; i++) {
            result = 31 * result + a[i];
        }
        return result;
    }
```

The improvement in performance from this simple change can be confirmed with Java 8 by running a simple benchmark. 

|Benchmark|Mode|Threads|Samples|Score|Score Error (99.9%)|Unit|Param: size|
|--- |--- |--- |--- |--- |--- |--- |--- |
|BuiltIn|thrpt|1|10|9.537736|0.382617|ops/us|100|
|BuiltIn|thrpt|1|10|0.804620|0.103037|ops/us|1000|
|BuiltIn|thrpt|1|10|0.092297|0.003947|ops/us|10000|
|Unrolled|thrpt|1|10|14.974398|0.628522|ops/us|100|
|Unrolled|thrpt|1|10|1.514986|0.035759|ops/us|1000|
|Unrolled|thrpt|1|10|0.137408|0.010200|ops/us|10000|


The performance improvement is so obvious, and the change so easy to make, that one wonders why JVM vendors didn't make the change themselves.

#### Java 9: Universally Better Automatic Optimisations?

As the comments on the blog post suggest, this is a prime candidate for vectorisation. Auto-vectorisation is a _thing_ in Java 9. Using intrinsics or code clean enough to express intent clearly, you can really expect to see good usage of SIMD in Java 9. I was really expecting the situation to reverse in Java 9; but it doesn't.

|Benchmark|Mode|Threads|Samples|Score|Score Error (99.9%)|Unit|Param: size|
|--- |--- |--- |--- |--- |--- |--- |--- |
|BuiltIn|thrpt|1|10|9.822568|0.381087|ops/us|100|
|BuiltIn|thrpt|1|10|0.949273|0.024021|ops/us|1000|
|BuiltIn|thrpt|1|10|0.093171|0.004502|ops/us|10000|
|Unrolled|thrpt|1|10|13.762617|0.440135|ops/us|100|
|Unrolled|thrpt|1|10|1.501106|0.094897|ops/us|1000|
|Unrolled|thrpt|1|10|0.139963|0.011487|ops/us|10000|

This is a still a smart optimisation two years later, but it offends my sensibilities in the same way hints do in SQL - a layer of abstraction has been punctured. I will have to try again in Java 10.

> Better gains are available when [precomputing the coefficients is possible](https://richardstartin.github.io/posts/explicit-intent-and-even-faster-hash-codes/).
