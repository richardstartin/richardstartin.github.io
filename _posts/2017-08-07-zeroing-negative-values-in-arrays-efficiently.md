---
title: "Zeroing Negative Values in Arrays Efficiently"
layout: default

date: 2017-08-07
redirect_from:
    /zeroing-negative-values-in-arrays-efficiently/
---

Replacing negatives with zeroes in large arrays of values is a primitive function of several complex financial risk measures, including potential future exposure (PFE) and the liquidity coverage ratio (LCR). While this is not an interesting operation by any stretch of the imagination, it is useful and there is significant benefit in its performance. This is an operation that can be computed very efficiently using the instruction `VMAXPD`. <a href="https://software.intel.com/sites/default/files/managed/ad/dc/Intel-Xeon-Scalable-Processor-throughput-latency.pdf" target="_blank">For Intel Xeon processors</a>, this instruction requires half a cycle to calculate and has a latency (how long before another instruction can use its result) of four cycles. There is currently no way to trick Java into using this instruction for this simple operation, though there is a placeholder implementation on the current `DoubleVector` <a href="http://hg.openjdk.java.net/panama/panama/jdk/file/776788a90cf3/test/panama/vector-draft-spec/src/main/java/com/oracle/vector/DoubleVector.java" target="_blank">prototype</a> in Project Panama which may do so.

#### C++ Intel Intrinsics

It's possible to target instructions from different processor vendors, in my case Intel, by using intrinsic functions which expose instructions as high level functions. The code looks incredibly ugly but it works. Here is a C++ function for 256 bit ymm registers:

```cpp
void zero_negatives(const double* source, double* target, const size_t length) {
	for (size_t i = 0; i + 3 < length; i += 4) {
		__m256d vector = _mm256_load_pd(source + i);
		__m256d zeroed = _mm256_max_pd(vector, _mm256_setzero_pd());
		_mm256_storeu_pd(target + i, zeroed);
	}
}
```

The function loads doubles into 256 bit vectors, within each vector replaces the negative values with zero, and writes them back into an array. It generates the following assembly code (which, incidentally, is less of a shit show to access than in Java):

```asm
void zero_negatives(const double* source, double* target, const size_t length) {
00007FF746EE5110  mov         qword ptr [rsp+18h],r8  
00007FF746EE5115  mov         qword ptr [rsp+10h],rdx  
00007FF746EE511A  mov         qword ptr [rsp+8],rcx  
00007FF746EE511F  push        r13  
00007FF746EE5121  push        rbp  
00007FF746EE5122  push        rdi  
00007FF746EE5123  sub         rsp,250h  
00007FF746EE512A  mov         r13,rsp  
00007FF746EE512D  lea         rbp,[rsp+20h]  
00007FF746EE5132  and         rbp,0FFFFFFFFFFFFFFE0h  
00007FF746EE5136  mov         rdi,rsp  
00007FF746EE5139  mov         ecx,94h  
00007FF746EE513E  mov         eax,0CCCCCCCCh  
00007FF746EE5143  rep stos    dword ptr [rdi]  
00007FF746EE5145  mov         rcx,qword ptr [rsp+278h]  
	for (size_t i = 0; i + 3 < length; i += 4) {
00007FF746EE514D  mov         qword ptr [rbp+8],0  
00007FF746EE5155  jmp         zero_negatives+53h (07FF746EE5163h)  
00007FF746EE5157  mov         rax,qword ptr [rbp+8]  
00007FF746EE515B  add         rax,4  
00007FF746EE515F  mov         qword ptr [rbp+8],rax  
00007FF746EE5163  mov         rax,qword ptr [rbp+8]  
00007FF746EE5167  add         rax,3  
00007FF746EE516B  cmp         rax,qword ptr [length]  
00007FF746EE5172  jae         zero_negatives+0DDh (07FF746EE51EDh)  
		__m256d vector = _mm256_load_pd(source + i);
00007FF746EE5174  mov         rax,qword ptr [source]  
00007FF746EE517B  mov         rcx,qword ptr [rbp+8]  
00007FF746EE517F  lea         rax,[rax+rcx*8]  
00007FF746EE5183  vmovupd     ymm0,ymmword ptr [rax]  
00007FF746EE5187  vmovupd     ymmword ptr [rbp+180h],ymm0  
00007FF746EE518F  vmovupd     ymm0,ymmword ptr [rbp+180h]  
00007FF746EE5197  vmovupd     ymmword ptr [rbp+40h],ymm0  
		__m256d zeroed = _mm256_max_pd(vector, _mm256_setzero_pd());
00007FF746EE519C  vxorpd      xmm0,xmm0,xmm0  
00007FF746EE51A0  vmovupd     ymmword ptr [rbp+200h],ymm0  
00007FF746EE51A8  vmovupd     ymm0,ymmword ptr [rbp+40h]  
00007FF746EE51AD  vmaxpd      ymm0,ymm0,ymmword ptr [rbp+200h]  
00007FF746EE51B5  vmovupd     ymmword ptr [rbp+1C0h],ymm0  
00007FF746EE51BD  vmovupd     ymm0,ymmword ptr [rbp+1C0h]  
00007FF746EE51C5  vmovupd     ymmword ptr [rbp+80h],ymm0  
		_mm256_storeu_pd(target + i, zeroed);
00007FF746EE51CD  mov         rax,qword ptr [target]  
00007FF746EE51D4  mov         rcx,qword ptr [rbp+8]  
00007FF746EE51D8  lea         rax,[rax+rcx*8]  
00007FF746EE51DC  vmovupd     ymm0,ymmword ptr [rbp+80h]  
00007FF746EE51E4  vmovupd     ymmword ptr [rax],ymm0  
	}
00007FF746EE51E8  jmp         zero_negatives+47h (07FF746EE5157h)  
}
00007FF746EE51ED  lea         rsp,[r13+250h]  
00007FF746EE51F4  pop         rdi  
00007FF746EE51F5  pop         rbp  
00007FF746EE51F6  pop         r13  
00007FF746EE51F8  ret    
```

This code is noticeably fast. I measured the throughput averaged over 1000 iterations, with an array of 10 million doubles (800MB) uniformly distributed between +/- 1E7, to quantify the throughput in GB/s and iterations/s. This code does between 4.5 and 5 iterations per second, which translates to processing approximately 4GB/s. This seems high, and since I am unaware of best practices in C++, if the measurement is flawed, I would gratefully be educated in the comments.

```cpp
void benchmark() {
	const size_t length = 1E8;
	double* values = new double[length];
	fill_array(values, length);
	double* zeroed = new double[length];
	auto start = std::chrono::high_resolution_clock::now();
	int iterations = 1000;
	for (int i = 0; i < iterations; ++i) {
		zero_negatives(values, zeroed, length);
	}
	auto end = std::chrono::high_resolution_clock::now();
	auto nanos = std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count();
	double thrpt_s = (iterations * 1E9) / nanos;
	double thrpt_gbps = (thrpt_s * sizeof(double) * length) / 1E9;
	std::cout << thrpt_s << "/s" << std::endl;
	std::cout << thrpt_gbps << "GB/s" << std::endl;
	delete[] values;
	delete[] zeroed;
}
```

While I am sure there are various ways an expert could tweak this for performance, this code can't get much faster unless there are 512 bit zmm registers available, in which case it would be wasteful. While the code looks virtually the same for AVX512 (just replace "256" with "512"), portability and efficiency are at odds. Handling the mess of detecting the best instruction set for the deployed architecture is the main reason for using Java in performance sensitive (but not critical) applications. But this is not the code the JVM generates.

#### Java Auto-Vectorisation (Play Your Cards Right)

There is currently no abstraction modelling vectorisation in Java. The only access available is if the compiler engineers implement an intrinsic, or auto-vectorisation, which will try, and sometimes succeed admirably, to translate your code to a good vector implementation. There is currently a prototype project for explicit vectorisation in <a href="http://openjdk.java.net/projects/panama/" target="_blank">Project Panama</a>. There are a few ways to skin this cat, and it's worth looking at the code they generate and the throughput available from each approach.

There is a choice between copying the array and zeroing out the negatives, and allocating a new array and only writing the non-negative values. There is another choice between an if statement and branchless code using `Math.max`. This results in the following four implementations which I measure on comparable data to the C++ benchmark (10 million doubles, normally distributed with mean zero). To be fair to the Java code, as in the C++ benchmarks, the cost of allocation is isolated by writing into an array pre-allocated once per benchmark. This penalises the approaches where the array is copied first and then zeroed wherever the value is negative. The code is online at <a href="https://github.com/richardstartin/simdbenchmarks" target="_blank">github</a>.

```java
    @Benchmark
    @CompilerControl(CompilerControl.Mode.DONT_INLINE)
    public double[] BranchyCopyAndMask(ArrayWithNegatives state) {
        double[] data = state.data;
        double[] result = state.target;
        System.arraycopy(data, 0, result, 0, data.length);
        for (int i = 0; i < result.length; ++i) {
            if (result[i] < 0D) {
                result[i] = 0D;
            }
        }
        return result;
    }

    @Benchmark
    @CompilerControl(CompilerControl.Mode.DONT_INLINE)
    public double[] BranchyNewArray(ArrayWithNegatives state) {
        double[] data = state.data;
        double[] result = state.target;
        for (int i = 0; i < result.length; ++i) {
            result[i] = data[i] < 0D ? 0D : data[i];
        }
        return result;
    }

    @Benchmark
    @CompilerControl(CompilerControl.Mode.DONT_INLINE)
    public double[] NewArray(ArrayWithNegatives state) {
        double[] data = state.data;
        double[] result = state.target;
        for (int i = 0; i < result.length; ++i) {
            result[i] = Math.max(data[i], 0D);
        }
        return result;
    }

    @Benchmark
    @CompilerControl(CompilerControl.Mode.DONT_INLINE)
    public double[] CopyAndMask(ArrayWithNegatives state) {
        double[] data = state.data;
        double[] result = state.target;
        System.arraycopy(data, 0, result, 0, data.length);
        for (int i = 0; i < result.length; ++i) {
            result[i] = Math.max(result[i], 0D);
        }
        return result;
    }
```

None of these implementations comes close to the native code above. The best implementation performs 1.8 iterations per second which equates to processing approximately 1.4GB/s, vastly inferior to the 4GB/s achieved with Intel intrinsics. The results are below:

<div class="table-holder" markdown="block">

|Benchmark|Mode|Threads|Samples|Score|Score Error (99.9%)|Unit|
|--- |--- |--- |--- |--- |--- |--- |
|BranchyCopyAndMask|thrpt|1|10|1.314845|0.061662|ops/s|
|BranchyNewArray|thrpt|1|10|1.802673|0.061835|ops/s|
|CopyAndMask|thrpt|1|10|1.146630|0.018903|ops/s|
|NewArray|thrpt|1|10|1.357020|0.116481|ops/s|

</div>

As an aside, there is a very interesting observation to make, worthy of its own post: if the array consists only of positive values, the "branchy" implementations run very well, at speeds comparable to the `zero_negatives` (when it ran with 50% negatives). The ratio of branch hits to misses is an orthogonal explanatory variable, and the input data, while I often don't think about it enough, is very important.

I only looked at the assembly emitted for the fastest version (BranchyNewArray) and it doesn't look anything like `zero_negatives`, ~~though it does use some vectorisation~~ - as pointed out by Daniel Lemire in the comments, this code has probably not been vectorised and is probably using SSE2 (indeed only quad words are loaded into 128 bit registers):

```asm
  0x000002ae309c3d5c: vmovsd  xmm0,qword ptr [rdx+rax*8+10h]
  0x000002ae309c3d62: vxorpd  xmm1,xmm1,xmm1    
  0x000002ae309c3d66: vucomisd xmm0,xmm1        
```

I don't really understand, and haven't thought about, the intent of the emitted code, but it makes extensive use of the instruction [`VUCOMISD`](http://www.felixcloutier.com/x86/UCOMISD.html) for comparisons with zero, which has a lower latency but lower throughput than `VMAXPD`.  It would certainly be interesting to see how Project Panama does this. Perhaps this should just be made available as a fail-safe intrinsic like [`Arrays.mismatch`](https://richardstartin.github.io/posts/new-methods-in-java-9-math-fma-and-arrays-mismatch)?
