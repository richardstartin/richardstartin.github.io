---
title: Sparse Bit Matrix Substring Search 
layout: post
date: 2020-02-07
tags: java parsing
image: /assets/2020/02/sparse-bitmatrix-substring-search/SlimFast.png
---

I recently read an interesting blog [post](https://medium.com/wix-engineering/beating-textbook-algorithms-in-string-search-5d24b2f1bbd0) about speeding up substring search.
The author found that, for strings with fewer than 65 characters, textbook algorithms could be beaten using bitwise operations.
The approach requires the construction of a bit matrix mapping each byte of the input to the positions in the string being searched for, but it struck me that the bit matrix was a little large.
This post is about adapting the algorithm to use a sparse bit matrix, and working around some of the costs incurred in saving space using tools available in JDK13.

1. TOC 
{:toc}

### Bit Matrix Substring Search

Before scanning the input, a bit matrix is constructed from the search term, which associates each byte with a bitmask of the positions at which it appears in the search term.
If the search term is "colonoscopy" then the mask for `'o'` will be `0b100101010` because the letter is in positions 1, 3, 5, and 8 of the string (note the endianness of the mask).
Byte `'l'` maps to the mask `0b100` because it appears at position 3; any byte not in the input is mapped to `0x0`. 

When the input is scanned, the least significant bit (LSB) is added to a bitmask and shifted left for each byte of the input.
For each input byte, a bitmask is looked up in the bit matrix and intersected with the current bitmask.
If the current byte is the first byte in the search term, the LSB will survive the intersection and shift left, because the bitmask's LSB is also set.
If the last $m$ bytes seen were all in the search term, then bit $m$ will be set because each bit $i~\in[0,m)$ should be in the bitmask obtained from the bit matrix for each byte $b_i$ by construction.
When $m = n$ for a search term of length $n$, there is a match and the algorithm terminates, returning the position the first encountered instance of the search term started at.
This is a really neat and branch-free algorithm.
 
The algorithm was designed to implement Netty's `ByteProcessor` interface, which I have called an "artifically narrow pipe" for data in another [post](https://richardstartin.github.io/posts/finding-bytes#artificially-narrow-pipes), so I adapted it to operate directly on a `byte[]` so I could evaluate it.

```java
public class BitMatrixSearcher implements Searcher {

    private final long[] masks = new long[256];
    private final long success;

    public BitMatrixSearcher(byte[] searchString) {
        if (searchString.length > 64) {
            throw new IllegalArgumentException("Too many bytes");
        }
        long word = 1L;
        for (byte key : searchString) {
            masks[key & 0xFF] |= word;
            word <<= 1;
        }
        this.success = 1L << (searchString.length - 1);
    }

    public int find(byte[] data) {
        long current = 0L;
        for (int i = 0; i < data.length; ++i) {
            current = ((current << 1) | 1) & masks[data[i] & 0xFF];
            if ((current & success) == success) {
                return i - Long.numberOfTrailingZeros(success);
            }
        }
        return -1;
    }
}
```

If you try running this you will find that it really is _very_ fast, and, combined with a more general purpose algorithm for long search terms, could be very useful.

It might be apparent by now that a `BitMatrixSearcher` instance will always use slightly more than 2KB, which, unless you are searching for very few terms or this is the only thing your application does, might have negative side effects.
You can see using [JOL](https://openjdk.java.net/projects/code-tools/jol/) for a three byte search term:

```
    BitMatrixSearcher@4141d797d object externals:
          ADDRESS       SIZE TYPE                  PATH                           VALUE
        71766fef8         24 BitMatrixSearcher                                    (object)
        71766ff10         24 (something else)      (somewhere else)               (something else)
        71766ff28       2064 [J                    .masks                         [0, 1, 2, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
```

A lot of this spatial overhead can be removed, at the cost of some degradation in throughput.

> You can read about the algorithm in its original context [here](https://medium.com/wix-engineering/beating-textbook-algorithms-in-string-search-5d24b2f1bbd0#0173).

### Sparse Bit Matrix 

Most of the bitmasks are zero, but take up the same amount of space as those serving a purpose; not storing them saves a lot of space.
To do that, as the matrix is constructed from the search term, the cardinality $m$ of the bytes which actually appear in the search term is accumulated.
The bitmasks are stored in an array of size $m + 1$, with an empty bitmask at position $m$ which will keep the lookup branch-free.  

The lookup from byte to bitmask is a bit more complicated now and a mapping table is needed.
If byte $i$ is in the search term, then the index into the bitmask table is stored at position $i$ of the table.
If position $j$ is not in the search term, the value $m$ is stored at position $j$ of the table.
Since there can only be 64 entries, there can be at most 65 bitmasks, so only 7 bits are needed per index; a `byte[]` is sufficient, but conversion to `int` by masking with `0xFF` will be needed when used.
In the worst case, this saves 1.25KB.

Here is `SparseBitMatrixSearcher`:

```java
public class SparseBitMatrixSearcher implements Searcher {

    private final long[] masks;
    private byte[] positions;
    private final long success;

    public SparseBitMatrixSearcher(byte[] searchString) {
        if (searchString.length > 64) {
            throw new IllegalArgumentException("Too many bytes");
        }
        int cardinality = 0;
        long[] existence = new long[4];
        for (byte key : searchString) {
            int value = key & 0xFF;
            long word = existence[value >>> 6];
            if ((word & (1L << value)) == 0) {
                ++cardinality;
                existence[value >>> 6] |= (1L << value);
            }
        }
        this.masks = new long[cardinality + 1];
        this.positions = new byte[256];
        Arrays.fill(positions, (byte)cardinality);
        int index = 0;
        for (byte key : searchString) {
            int position = rank(key, existence);
            positions[key & 0xFF] = (byte)position;
            masks[position] |= (1L << index);
            ++index;
        }
        this.success = 1L << (searchString.length - 1);
    }

    public int find(byte[] data) {
        long current = 0L;
        for (int i = 0; i < data.length; ++i) {
            int value = data[i] & 0xFF;
            long mask = masks[positions[value] & 0xFF];
            current = ((current << 1) | 1) & mask;
            if ((current & success) == success) {
                return i - Long.numberOfTrailingZeros(success);
            }
        }
        return -1;
    }

    private static int rank(byte key, long[] existence) {
        int value = (key & 0xFF);
        int wi = value >>> 6;
        int i = 0;
        int position = 0;
        while (i < wi) {
            position += Long.bitCount(existence[i]);
            ++i;
        }
        return position + Long.bitCount(existence[wi] & ((1L << value) - 1));
    }
}
``` 

JOL confirms that this saves a lot of space on the baseline of 2112 bytes.
For a three byte search term we have 424 bytes:

```
    SparseBitMatrixSearcher@4b5d6a01d object externals:
          ADDRESS       SIZE TYPE                     PATH                           VALUE
        7171fb460         32 SparseBitMatrixSearcher                                 (object)
        7171fb480         72 (something else)         (somewhere else)               (something else)
        7171fb4c8         48 [J                       .masks                         [1, 2, 4, 0]
        7171fb4f8        272 [B                       .positions                     [3, 0, 1, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3]

```

In the worst case we have 888 bytes:

```
    SparseBitMatrixSearcher@61230f6ad object externals:
          ADDRESS       SIZE TYPE                     PATH                           VALUE
        7170041a8         32 SparseBitMatrixSearcher                                 (object)
        7170041c8         48 (something else)         (somewhere else)               (something else)
        7170041f8        536 [J                       .masks                         [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768, 65536, 131072, 262144, 524288, 1048576, 2097152, 4194304, 8388608, 16777216, 33554432, 67108864, 134217728, 268435456, 536870912, 1073741824, 2147483648, 4294967296, 8589934592, 17179869184, 34359738368, 68719476736, 137438953472, 274877906944, 549755813888, 1099511627776, 2199023255552, 4398046511104, 8796093022208, 17592186044416, 35184372088832, 70368744177664, 140737488355328, 281474976710656, 562949953421312, 1125899906842624, 2251799813685248, 4503599627370496, 9007199254740992, 18014398509481984, 36028797018963968, 72057594037927936, 144115188075855872, 288230376151711744, 576460752303423488, 1152921504606846976, 2305843009213693952, 4611686018427387904, -9223372036854775808, 0]
        717004410        272 [B                       .positions                     [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64, 64]
```

### BitMatrixSearcher vs SparseBitMatrixSearcher

`BitMatrixSearcher` uses some extra space to make sure the byte to bitmask lookup is about as efficient as it can get, but is small enough to fit comfortably in L1 cache.
It should be expected that reduced footprint costs something and there will be some degradation in throughput in an isolated microbenchmark.
How much?

I benchmarked these two implementations with JMH, varying a few parameters.

```java
    @Param({"100", "1000", "2000"})
    int dataLength;

    @Param({ "3", "19", "40", "59"})
    int termLength;

    @Param({"7", "12"})
    int logVariety;

    @Param("90210")
    long seed;

    @Param
    SearcherType searcherType;
```

All of the parameters are self explanatory, except perhaps `logVariety`, which is the logarithm base-2 of the number of distinct inputs the benchmark will see.
The benchmark cycles through these inputs by calling `next` to get the next input:

```java
    private byte[][] data;
    private int instance;

    public byte[] next() {
        return data[instance++ & (data.length - 1)];
    }
...
    @Benchmark
    public int indexOfSearcher(SearchState searchState) {
        return searchState.searcher.find(searchState.next());
    }
```

I have found before that this prevents the benchmark from learning any branches, is more realistic than a single array hot in cache, and is reasonably cheap to do.

The data itself is generated randomly, with the search term at a random position close to the end of the input, somewhere between 0 and 10 bytes to the left of the last position it could still fit into the input.
This creates variability which should average out over lots of inputs.
Notably, the data and the search term are random, which is to ignore a lot of the structure to be found in real data, and would definitely be wrong for benchmarking heuristics. 
This likely penalises `SparseBitMatrixSearcher` more than `BitMatrixSearcher`, because random terms are less likely to contain repeated bytes, and `BitMatrixSearcher` stores them all anyway.

<div class="table-holder" markdown="block">

| data length | term length | dense (us/op) | sparse (us/op) | relative difference |
|-------------|-------------|---------------|----------------|---------------------|
| 100 | 3 | 0.11 | 0.14 | 28% |
| 100 | 19 | 0.11 | 0.14 | 28% |
| 100 | 40 | 0.11 | 0.15 | 28% |
| 100 | 59 | 0.11 | 0.14 | 27% |
| 1000 | 3 | 0.95 | 1.33 | 33% |
| 1000 | 19 | 0.94 | 1.33 | 34% |
| 1000 | 40 | 0.95 | 1.32 | 33% |
| 1000 | 59 | 0.94 | 1.32 | 34% |
| 2000 | 3 | 2.02 | 2.84 | 34% |
| 2000 | 19 | 2.03 | 2.82 | 33% |
| 2000 | 40 | 2.02 | 2.79 | 32% |
| 2000 | 59 | 2.03 | 2.79 | 32% |
   
</div>

Running the benchmark, it looks like there is a 30% penalty for the space saved.
I could probably find a metric to justify this difference, but let's find out where it comes from.

With `-prof perfasm` I can see bounds checks on most of the array accesses in `SparseBitMatrixSearcher`.

```java
for (int i = 0; i < data.length; ++i) {
    int value = data[i] & 0xFF;
    long mask = masks[positions[value] & 0xFF];
    current = ((current << 1) | 1) & mask;
    if ((current & success) == success) {
        return i - Long.numberOfTrailingZeros(success);
    }
}
```

```asm
  0.34%  ↗  0x00007fe26bc6a6d0:   movslq %r8d,%rbx  
  0.91%  │  0x00007fe26bc6a6d3:   movzbl 0x10(%rcx,%rbx,1),%r10d
----------------------------------------------------------------
  9.90%  │  0x00007fe26bc6a6d9:   cmp    %r13d,%r10d
         │  0x00007fe26bc6a6dc:   jae    0x00007fe26bc6a7c2
----------------------------------------------------------------
  0.12%  │  0x00007fe26bc6a6e2:   movzbl 0x10(%rbp,%r10,1),%r10d
----------------------------------------------------------------
  0.22%  │  0x00007fe26bc6a6e8:   cmp    %esi,%r10d
         │  0x00007fe26bc6a6eb:   jae    0x00007fe26bc6a816
----------------------------------------------------------------
  0.71%  │  0x00007fe26bc6a6f1:   shl    %rax
  9.26%  │  0x00007fe26bc6a6f4:   or     $0x1,%rax
  0.10%  │  0x00007fe26bc6a6f8:   and    0x10(%r9,%r10,8),%rax  
 19.40%  │  0x00007fe26bc6a6fd:   mov    %rax,%r10
  0.37%  │  0x00007fe26bc6a700:   and    %r11,%r10
 10.46%  │  0x00007fe26bc6a703:   cmp    %r11,%r10
         │  0x00007fe26bc6a706:   je     0x00007fe26bc6a588     
  8.91%  │  0x00007fe26bc6a70c:   movzbl 0x11(%rcx,%rbx,1),%r10d
  0.34%  │  0x00007fe26bc6a712:   mov    %r8d,%edx
  0.15%  │  0x00007fe26bc6a715:   inc    %edx                   
----------------------------------------------------------------
  1.03%  │  0x00007fe26bc6a717:   cmp    %r13d,%r10d
         │  0x00007fe26bc6a71a:   jae    0x00007fe26bc6a7c5
----------------------------------------------------------------
 10.14%  │  0x00007fe26bc6a720:   movzbl 0x10(%rbp,%r10,1),%r10d
----------------------------------------------------------------
  0.71%  │  0x00007fe26bc6a726:   cmp    %esi,%r10d
         │  0x00007fe26bc6a729:   jae    0x00007fe26bc6a819
----------------------------------------------------------------
  0.27%  │  0x00007fe26bc6a72f:   shl    %rax
  0.61%  │  0x00007fe26bc6a732:   or     $0x1,%rax
  9.28%  │  0x00007fe26bc6a736:   and    0x10(%r9,%r10,8),%rax  
  0.93%  │  0x00007fe26bc6a73b:   mov    %rax,%r10
  0.10%  │  0x00007fe26bc6a73e:   and    %r11,%r10
  0.83%  │  0x00007fe26bc6a741:   cmp    %r11,%r10
         │  0x00007fe26bc6a744:   je     0x00007fe26bc6a58b
  9.58%  │  0x00007fe26bc6a74a:   add    $0x2,%r8d              
  0.10%  │  0x00007fe26bc6a74e:   cmp    %r14d,%r8d
         ╰  0x00007fe26bc6a751:   jl     0x00007fe26bc6a6d0
```

It's easy to see that they are unnecessary, so long as the contents of the arrays never change.
`int value = data[i] & 0xFF;` _must_ never produce a value less than zero or greater than 255, because `data[i]` is a `byte`.
There are known to always be 256 elements in `positions`: `this.positions = new byte[256];`.
There are no checks for array underflow, but the upper bounds checks below are unnecessary.

```asm
  0.22%  │  0x00007fe26bc6a6e8:   cmp    %esi,%r10d
         │  0x00007fe26bc6a6eb:   jae    0x00007fe26bc6a816
...
  0.71%  │  0x00007fe26bc6a726:   cmp    %esi,%r10d
         │  0x00007fe26bc6a729:   jae    0x00007fe26bc6a819
```

Just by reading the constructor, the maximum value in `positions` must be `masks.length - 1` and because it is stored as a `byte` and masked with `0xFF` (`positions[value] & 0xFF`) it can't possibly be negative.
There are no checks for lower bounds, but the upper bounds checks below look like they might be expensive.

```asm
  9.90%  │  0x00007fe26bc6a6d9:   cmp    %r13d,%r10d
         │  0x00007fe26bc6a6dc:   jae    0x00007fe26bc6a7c2
...
  1.03%  │  0x00007fe26bc6a717:   cmp    %r13d,%r10d
         │  0x00007fe26bc6a71a:   jae    0x00007fe26bc6a7c5
```

### Manual Bounds Check Elimination

I consider bounds check elimination and propagation of context from construction to use to be a compiler's job, but all these checks can be made to go away by using `Unsafe`.
This is something you should avoid doing, because if you get something wrong bad stuff happens.
I reimplemented [`BitMatrixSearcher`](https://github.com/richardstartin/runtime-benchmarks/blob/master/src/main/java/com/openkappa/runtime/stringsearch/UnsafeBitMatrixSearcher.java) and [`SparseBitMatrixSearcher`](https://github.com/richardstartin/runtime-benchmarks/blob/master/src/main/java/com/openkappa/runtime/stringsearch/UnsafeSparseBitMatrixSearcher.java) using `Unsafe`.
This may even save a little bit of space by removing some object headers and padding, but JOL can't tell you about it because it no longer knows how to associate the data you are using with the instrumented instance.

The problematic loop in `SparseBitMatrixSearcher` becomes:

```java
for (int i = 0; i < data.length; ++i) {
    int value = data[i] & 0xFF;
    int position = UNSAFE.getByte(positionsOffset + value) & 0xFF;
    long mask = UNSAFE.getLong(masksOffset + position);
    current = ((current << 1) | 1) & mask;
    if ((current & success) == success) {
        return i - Long.numberOfTrailingZeros(success);
    }
}
```

The bounds checks are gone!

```asm
  2.70%  ↗  0x00007fe93fa4f9d0:   mov    0x18(%r11),%rbx
         │  0x00007fe93fa4f9d4:   movslq %edx,%rax                    
  9.88%  │  0x00007fe93fa4f9d7:   movzbq 0x10(%rsi,%rax,1),%rdi
  0.02%  │  0x00007fe93fa4f9dd:   movzbq (%rbx,%rdi,1),%rbx
  2.31%  │  0x00007fe93fa4f9e2:   shl    %r9
  0.02%  │  0x00007fe93fa4f9e5:   or     $0x1,%r9
  9.15%  │  0x00007fe93fa4f9e9:   mov    0x10(%r11),%rdi
  0.06%  │  0x00007fe93fa4f9ed:   and    (%rdi,%rbx,1),%r9
 10.00%  │  0x00007fe93fa4f9f1:   mov    0x20(%r11),%rdi              
  0.08%  │  0x00007fe93fa4f9f5:   mov    %r9,%rbx
  5.54%  │  0x00007fe93fa4f9f8:   and    %rdi,%rbx
  4.70%  │  0x00007fe93fa4f9fb:   cmp    %rdi,%rbx
         │  0x00007fe93fa4f9fe:   je     0x00007fe93fa4f8d7
  8.31%  │  0x00007fe93fa4fa04:   movzbl 0x11(%rsi,%rax,1),%edi       
  0.26%  │  0x00007fe93fa4fa09:   shl    %r9
  2.98%  │  0x00007fe93fa4fa0c:   movslq %edi,%rbx
  0.08%  │  0x00007fe93fa4fa0f:   or     $0x1,%r9
  8.60%  │  0x00007fe93fa4fa13:   mov    0x18(%r11),%rdi              
  0.06%  │  0x00007fe93fa4fa17:   movzbq (%rdi,%rbx,1),%rbx
  3.47%  │  0x00007fe93fa4fa1c:   mov    0x10(%r11),%rdi
  0.06%  │  0x00007fe93fa4fa20:   and    (%rdi,%rbx,1),%r9            
 10.99%  │  0x00007fe93fa4fa24:   mov    0x20(%r11),%rdi              
  0.02%  │  0x00007fe93fa4fa28:   mov    %r9,%rbx
  2.90%  │  0x00007fe93fa4fa2b:   and    %rdi,%rbx
  2.27%  │  0x00007fe93fa4fa2e:   cmp    %rdi,%rbx
         │  0x00007fe93fa4fa31:   je     0x00007fe93fa4f8d5           
  9.39%  │  0x00007fe93fa4fa37:   add    $0x2,%edx                    
  0.02%  │  0x00007fe93fa4fa3a:   cmp    %ecx,%edx
         ╰  0x00007fe93fa4fa3c:   jl     0x00007fe93fa4f9d0
```

Whilst `UnsafeBitMatrixSearcher` benefits marginally itself, the gap is smaller now.

<div class="table-holder" markdown="block">

| data length | term length | dense (us/op) | sparse (us/op) | relative difference |
|-------------|-------------|---------------|----------------|---------------------|
| 100 | 3 | 0.11 | 0.14 | 22% |
| 100 | 19 | 0.11 | 0.13 | 17% |
| 100 | 40 | 0.11 | 0.13 | 17% |
| 100 | 59 | 0.11 | 0.13 | 16% |
| 1000 | 3 | 0.93 | 1.18 | 23% |
| 1000 | 19 | 0.93 | 1.18 | 23% |
| 1000 | 40 | 0.94 | 1.18 | 23% |
| 1000 | 59 | 0.94 | 1.18 | 23% |
| 2000 | 3 | 1.99 | 2.50 | 22% |
| 2000 | 19 | 1.10 | 2.53 | 23% |
| 2000 | 40 | 2.01 | 2.50 | 21% |
| 2000 | 59 | 2.04 | 2.52 | 21% |

</div>

### Finding the First Byte Faster

The sparse implementation is slower, but at small lengths the difference is tiny. 
If the substring search were only ever done over small lengths, the difference wouldn't matter.
It could sometimes be a lot faster, depending on the statistics of the data, to check for a cheap condition with false positives and only switch to a substring search when it passes.
Searching for the first byte of the search term can make sense for some data.
For uniformly random bytes, the substring search should only be entered once every 256 bytes or so, so if the search for a single byte is much faster, it should show in these benchmarks.
If the input were English text, and the first byte were a space or the letter 'e', this would not be such a good strategy.

Since I changed the signature to allow access to the entire `byte[]` in the search, I can use SWAR to accelerate the byte search.
This approach can also be vectorised for large performance gains (I wrote a [post](/posts/finding-bytes) about this before).
Here, the input is scanned eight bytes at a time, and the sparse substring search is entered whenever the first byte of the input is found.
There will be false positives, so need to get out of the substring search as soon as the mask is empty and a multiple of 8 is reached.

```java
public int find(byte[] data) {
    long current = 0L;
    int i = 0;
    for (; i + 7 < data.length; i += Long.BYTES) {
        long word = first ^ UNSAFE.getLong(data, i + BYTE_ARRAY_OFFSET);
        long tmp = (word & 0x7F7F7F7F7F7F7F7FL) + 0x7F7F7F7F7F7F7F7FL;
        tmp = ~(tmp | word | 0x7F7F7F7F7F7F7F7FL);
        int j = Long.numberOfTrailingZeros(tmp) >>> 3;
        if (j != Long.BYTES) { // found the first byte
            for (int k = i + j; k < data.length; ++k) {
                int value = data[k] & 0xFF;
                int position = UNSAFE.getByte(positionsOffset + value) & 0xFF;
                long mask = UNSAFE.getLong(masksOffset + position);
                current = ((current << 1) | 1) & mask;
                if (current == 0 && (k & (Long.BYTES - 1)) == 0) {
                    break;
                }
                if ((current & success) == success) {
                    return k - Long.numberOfTrailingZeros(success);
                }
            }
        }
    }
    for (; i < data.length; ++i) {
        int value = data[i] & 0xFF;
        int position = UNSAFE.getByte(positionsOffset + value) & 0xFF;
        long mask = UNSAFE.getLong(masksOffset + position);
        current = ((current << 1) | 1) & mask;
        if ((current & success) == success) {
            return i - Long.numberOfTrailingZeros(success);
        }
    }
    return -1;
}
```

The full implementation is [here](https://github.com/richardstartin/runtime-benchmarks/blob/master/src/main/java/com/openkappa/runtime/stringsearch/UnsafeSWARSparseBitMatrixSearcher.java).
The heuristic works well for this data.

<div class="table-holder" markdown="block">


| data length | term length | sparse (us/op) | sparse swar (us/op) | relative difference |
|-------------|-------------|----------------|---------------------|---------------------|
| 100 | 3 | 0.13 | 0.05 | -97% |
| 100 | 19 | 0.13 | 0.06 | -75% |
| 100 | 40 | 0.13 | 0.08 | -44% |
| 100 | 59 | 0.13 | 0.09 | -33% |
| 1000 | 3 | 1.18 | 0.39 | -100% |
| 1000 | 19 | 1.18 | 0.38 | -102% |
| 1000 | 40 | 1.18 | 0.41 | -97% |
| 1000 | 59 | 1.18 | 0.43 | -94% |
| 2000 | 3 | 2.50 | 0.86 | -98% |
| 2000 | 19 | 2.53 | 0.88 | -97% |
| 2000 | 40 | 2.50 | 0.86 | -98% |
| 2000 | 59 | 2.52 | 0.86 | -98% |

</div>

I didn't bother implementing this with a dense bit matrix, and the point isn't to beat it but to reduce the time cost of the saved space.
It would undoubtedly be very slightly faster than with a sparse matrix, but the difference would provide scant justification for at least 1.25KB extra space.
In general, I think efficient solutions to this problem will consist of a heuristic for doing a fast and wide search for false positives, initiating a more costly exact search whenever a false positive is found.
Choice of heuristic should probably guided by profiling: assuming data seen in the past is similar to the data being processed at present, a histogram could be used to avoid worst case heuristic outcomes.    
It's also not possible to do a fast and wide search on the other side of an interface which only grants access to a byte of input at a time.


> Benchmarks run on OpenJDK 13 on Ubuntu 18.04.3 LTS, on a i7-6700HQ CPU, [benchmark data](https://github.com/richardstartin/runtime-benchmarks/blob/master/searcher.csv)