---
title: "New Methods in Java 9: Math.fma and Arrays.mismatch"
layout: post
theme: minimal
date: 2017-07-16
---

There are two noteworthy new methods in Java 9: `Arrays.mismatch` and `Math.fma`. 

#### Arrays.mismatch

This method takes two primitive arrays, and returns the index of the first differing values. This effectively computes the longest common prefix of the two arrays. This is really quite useful, mostly for text processing but also for Bioinformatics (protein sequencing and so on, much more interesting than the sort of thing I work on). Having worked extensively with Apache HBase (where a vast majority of the API involves manipulating byte arrays) I can think of lots of less interesting use cases for this method.

Looking carefully, you can see that the method calls into the internal `ArraysSupport` utility class, which will try to perform a vectorised mismatch (an intrinsic candidate). Since this will use AVX instructions, this is very fast; much faster than a handwritten loop.

Let's measure the boost versus a handwritten loop, testing across a range of common prefices and array lengths of `byte[]`.

```java
    @Benchmark
    @CompilerControl(CompilerControl.Mode.DONT_INLINE)
    public void Mismatch_Intrinsic(BytePrefixData data, Blackhole bh) {
        bh.consume(Arrays.mismatch(data.data1, data.data2));
    }


    @Benchmark
    @CompilerControl(CompilerControl.Mode.DONT_INLINE)
    public void Mismatch_Handwritten(BytePrefixData data, Blackhole bh) {
        byte[] data1 = data.data1;
        byte[] data2 = data.data2;
        int length = Math.min(data1.length, data2.length);
        int mismatch = -1;
        for (int i = 0; i < length; ++i) {
            if (data1[i] != data2[i]) {
                mismatch = i;
                break;
            }
        }
        bh.consume(mismatch);
    }
```

The results speak for themselves. 

|Benchmark|(prefix)|(size)|Mode|Cnt|Score|Error|Units|
|--- |--- |--- |--- |--- |--- |--- |--- |
|Mismatch_Handwritten|0.1|100|thrpt|5|26.830|4.025|ops/us|
|Mismatch_Handwritten|0.1|1000|thrpt|5|3.006|0.150|ops/us|
|Mismatch_Handwritten|0.1|10000|thrpt|5|0.314|0.029|ops/us|
|Mismatch_Handwritten|0.5|100|thrpt|5|24.521|2.980|ops/us|
|Mismatch_Handwritten|0.5|1000|thrpt|5|2.748|0.269|ops/us|
|Mismatch_Handwritten|0.5|10000|thrpt|5|0.306|0.021|ops/us|
|Mismatch_Handwritten|1.0|100|thrpt|5|25.345|2.377|ops/us|
|Mismatch_Handwritten|1.0|1000|thrpt|5|2.715|0.342|ops/us|
|Mismatch_Handwritten|1.0|10000|thrpt|5|0.319|0.012|ops/us|
|Mismatch_Intrinsic|0.1|100|thrpt|5|87.855|3.404|ops/us|
|Mismatch_Intrinsic|0.1|1000|thrpt|5|28.985|5.876|ops/us|
|Mismatch_Intrinsic|0.1|10000|thrpt|5|3.630|0.481|ops/us|
|Mismatch_Intrinsic|0.5|100|thrpt|5|81.303|9.710|ops/us|
|Mismatch_Intrinsic|0.5|1000|thrpt|5|32.967|5.315|ops/us|
|Mismatch_Intrinsic|0.5|10000|thrpt|5|3.896|0.450|ops/us|
|Mismatch_Intrinsic|1.0|100|thrpt|5|90.818|5.211|ops/us|
|Mismatch_Intrinsic|1.0|1000|thrpt|5|30.828|5.991|ops/us|
|Mismatch_Intrinsic|1.0|10000|thrpt|5|3.602|0.494|ops/us|

Why is there such a big difference? The handwritten loop compares one byte at a time, whereas `Arrays.mismatch` works 256 bits at a time.

```asm
  3.02%    1.83%        0x00007fea85ba50a0: push   %rbp
  0.14%    0.15%        0x00007fea85ba50a1: mov    %rsp,%rbp
  2.84%    4.70%        0x00007fea85ba50a4: shl    %cl,%rdx
  0.41%    0.38%        0x00007fea85ba50a7: xor    %rax,%rax
  2.72%    4.49%        0x00007fea85ba50aa: cmp    $0x8,%rdx
                        0x00007fea85ba50ae: je     Stub::vectorizedMismatch+148 0x00007fea85ba5134
  0.19%    0.17%        0x00007fea85ba50b4: jl     Stub::vectorizedMismatch+182 0x00007fea85ba5156
  0.18%    0.16%        0x00007fea85ba50ba: cmp    $0x10,%rdx
  0.00%           ╭     0x00007fea85ba50be: je     Stub::vectorizedMismatch+103 0x00007fea85ba5107
  0.12%    0.10%  │     0x00007fea85ba50c4: jl     Stub::vectorizedMismatch+148 0x00007fea85ba5134
  2.80%    1.69%  │     0x00007fea85ba50ca: cmp    $0x20,%rdx
                  │╭    0x00007fea85ba50ce: jl     Stub::vectorizedMismatch+97 0x00007fea85ba5101
  0.09%    0.08%  ││    0x00007fea85ba50d0: sub    $0x20,%rdx
  0.18%    0.18%  ││↗   0x00007fea85ba50d4: vmovdqu (%rdi,%rax,1),%ymm0
  0.15%    0.15%  │││   0x00007fea85ba50d9: vmovdqu (%rsi,%rax,1),%ymm1
  8.63%    9.44%  │││   0x00007fea85ba50de: vpxor  %ymm1,%ymm0,%ymm2
  2.63%    2.96%  │││   0x00007fea85ba50e2: vptest %ymm2,%ymm2
  3.49%    3.84%  │││   0x00007fea85ba50e7: jne    Stub::vectorizedMismatch+291 0x00007fea85ba51c3
 12.19%   14.10%  │││   0x00007fea85ba50ed: add    $0x20,%rax
  0.30%    0.32%  │││   0x00007fea85ba50f1: sub    $0x20,%rdx
                  ││╰   0x00007fea85ba50f5: jge    Stub::vectorizedMismatch+52 0x00007fea85ba50d4
  0.00%    0.00%  ││    0x00007fea85ba50f7: add    $0x20,%rdx
                  ││    0x00007fea85ba50fb: je     Stub::vectorizedMismatch+363 0x00007fea85ba520b
  0.00%    0.00%  │↘    0x00007fea85ba5101: cmp    $0x10,%rdx
  0.00%           │  ╭  0x00007fea85ba5105: jl     Stub::vectorizedMismatch+142 0x00007fea85ba512e
                  ↘  │  0x00007fea85ba5107: vmovdqu (%rdi,%rax,1),%xmm0
                     │  0x00007fea85ba510c: vmovdqu (%rsi,%rax,1),%xmm1
                     │  0x00007fea85ba5111: vpxor  %xmm1,%xmm0,%xmm2
                     │  0x00007fea85ba5115: vptest %xmm2,%xmm2
                     │  0x00007fea85ba511a: jne    Stub::vectorizedMismatch+319 0x00007fea85ba51df
                     │  0x00007fea85ba5120: add    $0x10,%rax
                     │  0x00007fea85ba5124: sub    $0x10,%rdx
                     │  0x00007fea85ba5128: je     Stub::vectorizedMismatch+363 0x00007fea85ba520b
  2.91%    2.96%     ↘  0x00007fea85ba512e: cmp    $0x8,%rdx
                        0x00007fea85ba5132: jl     Stub::vectorizedMismatch+182 0x00007fea85ba5156
```

The code for this benchmark is at [github](https://github.com/richardstartin/simdbenchmarks).

#### Math.fma

In comparison to users of some languages, Java programmers are lackadaisical about floating point errors. It's a good job that historically Java hasn't been considered suitable for the implementation of numerical algorithms. But all of a sudden there is a revolution of data science on the JVM, albeit mostly driven by the Scala community, with JVM implementations of structures like recurrent neural networks abounding. It matters less for machine learning than root finding, but how accurate can these implementations be without JVM level support for minimising the propagation floating point errors? With `Math.fma` this is improving, by allowing two common operations to be performed before rounding.

`Math.fma` fuses a multiplication and an addition into a single floating point operation to compute expressions like `ab + c`. This has two key benefits:



1. There's only one operation, and only one rounding error.
2. This is supported in AVX2 by the VFMADD* instructions.

#### Newton's Method

To investigate any superior suppression of floating point errors, I use a toy implementation of Newton's method to compute the root of a quadratic equation, which any teenager could calculate analytically (the error is easy to quantify).

I compare these two implementations for `4x^2 - 12x + 9` (there is a repeated root at 1.5) to get an idea for the error (defined by `latex |1.5 - x_n|`) after a large number of iterations.

I implemented this using FMA:

```java
public class NewtonsMethodFMA {

    private final double[] coefficients;

    public NewtonsMethodFMA(double[] coefficients) {
        this.coefficients = coefficients;
    }


    public double evaluateF(double x) {
        double f = 0D;
        int power = coefficients.length - 1;
        for (int i = 0; i < coefficients.length; ++i) {
            f = Math.fma(coefficients[i], Math.pow(x, power--), f);
        }
        return f;
    }

    public double evaluateDF(double x) {
        double df = 0D;
        int power = coefficients.length - 2;
        for (int i = 0; i < coefficients.length - 1; ++i) {
            df = Math.fma((power + 1) * coefficients[i],  Math.pow(x, power--), df);
        }
        return df;
    }

    public double solve(double initialEstimate, int maxIterations) {
        double result = initialEstimate;
        for (int i = 0; i < maxIterations; ++i) {
            result -= evaluateF(result)/evaluateDF(result);
        }
        return result;
    }
}
```

And an implementation with normal operations:

```java

public class NewtonsMethod {

    private final double[] coefficients;

    public NewtonsMethod(double[] coefficients) {
        this.coefficients = coefficients;
    }


    public double evaluateF(double x) {
        double f = 0D;
        int power = coefficients.length - 1;
        for (int i = 0; i < coefficients.length; ++i) {
            f += coefficients[i] * Math.pow(x, power--);
        }
        return f;
    }

    public double evaluateDF(double x) {
        double df = 0D;
        int power = coefficients.length - 2;
        for (int i = 0; i < coefficients.length - 1; ++i) {
            df += (power + 1) * coefficients[i] * Math.pow(x, power--);
        }
        return df;
    }

    public double solve(double initialEstimate, int maxIterations) {
        double result = initialEstimate;
        for (int i = 0; i < maxIterations; ++i) {
            result -= evaluateF(result)/evaluateDF(result);
        }
        return result;
    }
}
```

When I run this code for 1000 iterations, the FMA version results in 1.5000000083575202, whereas the vanilla version results in 1.500000017233207. It's completely unscientific, but seems plausible and confirms my prejudice so... In fact, it's not that simple, and over a range of initial values, there is only a very small difference in FMA's favour. There's not even a performance improvement - clearly this method wasn't added so you can start implementing numerical root finding algorithms - the key takeaway is that the results are slightly different because a different rounding strategy has been used.

|Benchmark|(maxIterations)|Mode|Cnt|Score|Error|Units|
|--- |--- |--- |--- |--- |--- |--- |
|NM_FMA|100|thrpt|10|93.805|± 5.174|ops/ms|
|NM_FMA|1000|thrpt|10|9.420|± 1.169|ops/ms|
|NM_FMA|10000|thrpt|10|0.962|± 0.044|ops/ms|
|NM_HandWritten|100|thrpt|10|93.457|± 5.048|ops/ms|
|NM_HandWritten|1000|thrpt|10|9.274|± 0.483|ops/ms|
|NM_HandWritten|10000|thrpt|10|0.928|± 0.041|ops/ms|
