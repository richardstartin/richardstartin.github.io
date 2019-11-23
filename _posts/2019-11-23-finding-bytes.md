---
title: "Finding Bytes in Arrays"
layout: default
date: 2019-11-23
author: "Richard Startin"
---

> Thanks to reviews from (reviewers).

This post considers the benefits of branch-free algorithms through the lens of a trivial problem: finding the first position of a byte within an array.
While this problem is simple, it has many applications in parsing:
[BSON keys](http://bsonspec.org/spec.html) are null terminated strings;
[HTTP 1.1 headers](https://tools.ietf.org/html/rfc7230#section-3) are delimited by CRLF sequences;
[CBOR arrays](https://tools.ietf.org/html/rfc7049#section-2.2.1) are terminated by the stop character `0xFF`.
I compare the most obvious, but branchy, implementation with a branch-free implementation, and attempt to vectorise the branch-free version using the Project Panama Vector API.

### Motivation: Parsing BSON

BSON has a very simple [structure](https://tools.ietf.org/html/rfc7049#section-2.2.1): except at the very top level, it is a list of triplets consisting of a type byte, a name, and a (recursively defined) BSON value.
Imagine you are writing a BSON parser.
You just need a jump table associating each value type with the appropriate callback for values of that type.
Then you read the type byte, read the attribute name, then jump to the value handler and parse the value.
The attribute names in persisted documents are pure overhead;
in order to save space, attribute names in BSON are null terminated, at the cost of one byte, rather than length-prefixed, at the cost of four.
This means that extracting the name is linear in the size of the name, rather than constant time.
Here's what this looks like in the [MongoDB Java driver](https://github.com/mongodb/mongo-java-driver/blob/master/bson/src/main/org/bson/io/ByteBufferBsonInput.java):

```java
@Override
public String readCString() {
    ensureOpen();

    // TODO: potentially optimize this
    int mark = buffer.position();
    readUntilNullByte();
    int size = buffer.position() - mark;
    buffer.position(mark);

    return readString(size);
}

private void readUntilNullByte() {
    //CHECKSTYLE:OFF
    while (readByte() != 0) { //NOPMD
        //do nothing - checkstyle & PMD hate this, not surprisingly
    }
    //CHECKSTYLE:ON
}
```

If you find yourself with a very large MongoDB cluster and are in any way sensible, you will quickly make three document schema changes:

1. Replace the attribute names with very short codes.
2. Reduce nesting! BSON trivia: each document has a 4 byte length marker, and they accumulate quickly.
3. Use arrays where possible.

If you can make all of these changes, you will have a larger impact on throughput than optimising the BSON parser.
I recently worked on a project which couldn't make these changes, so I wrote a proprietary BSON parser over 50x faster than the MongoDB Java driver implementation.
You can't get anywhere near 50x improvements just by reimplementing `readUntilNullByte`, but without making _all_ of the schema changes your documents will contain lots of variable length names, and therefore many unpredictable branches while traversing documents.

### Finding null terminators without branches

How do you extract null terminated strings without branching? Fortunately, it's a very old problem and Chapter 6 of _Hacker's Delight_ has a solution to find a zero byte in a 32 bit word, which can be adapted to process 64 bits at a time.
The code looks weird though.

```java
private static int firstZeroByte(long word) {
    long tmp = (word & 0x7F7F7F7F7F7F7F7FL) + 0x7F7F7F7F7F7F7F7FL;
    tmp = ~(tmp | word | 0x7F7F7F7F7F7F7F7FL);
    return Long.numberOfLeadingZeros(tmp) >>> 3;
}
```

Explaining this to myself as if to a five year old was helpful.
The mask `0x7F` masks out the eighth bit of a byte, which creates a "hole" for a bit to carry into.
Adding `0x7F` to the masked value will cause a carry over into the hole if and only if any of the lower seven bits are set.
Now, the value `0x7F` in `tmp` indicates that the input was either `0x0` or `0x80`, and if the byte is negated, we get `0x80`.
Any other input value will have the eighth bit set, so uniting with `0x7F` and negating makes `0x0`.
In order to knock out any `0x80`s present in the input, the input word is included in the union because `~(0x80 | 0x7F)` is zero.
After performing the negated union, wherever the input byte was zero, the eighth bit will be set.
Taking the number of leading zeroes (a hotspot intrinsic targeting the `lzcnt`/`clz` instructions) gives the position of the bit.
Dividing by eight gives the position of the byte.

Some examples might help:

```java
// all zeroes
private static int firstZeroByte(long word /* word = 0b0000000000000000000000000000000000000000000000000000000000000000 */) {
    long tmp = (word & 0x7F7F7F7F7F7F7F7FL) + 0x7F7F7F7F7F7F7F7FL;
    // tmp = 0b0111111101111111011111110111111101111111011111110111111101111111
    tmp = ~(tmp | word | 0x7F7F7F7F7F7F7F7FL);
    // tmp = 0b1000000010000000100000001000000010000000100000001000000010000000
    return Long.numberOfLeadingZeros(tmp) >>> 3; // 0 / 8 = 0
}

// all 0x80
private static int firstZeroByte(long word /* word = 0b1000000010000000100000001000000010000000100000001000000010000000 */) {
    long tmp = (word & 0x7F7F7F7F7F7F7F7FL) + 0x7F7F7F7F7F7F7F7FL;
    // tmp = 0b0111111101111111011111110111111101111111011111110111111101111111
    tmp = ~(tmp | word | 0x7F7F7F7F7F7F7F7FL);
    // tmp = 0b0000000000000000000000000000000000000000000000000000000000000000
    return Long.numberOfLeadingZeros(tmp) >>> 3; // 64 / 8 = 8 (not found)
}

// {31, 25, 100, 0x7F, 9, 0, 127, 0x80}
private static int firstZeroByte(long word /* word = 0b0001111100011001011001000111111100001001000000000111111110000000 */) {
    long tmp = (word & 0x7F7F7F7F7F7F7F7FL) + 0x7F7F7F7F7F7F7F7FL;
    // tmp = 0b1001111010011000111000111111111010001000011111111111111001111111
    tmp = ~(tmp | word | 0x7F7F7F7F7F7F7F7FL);
    // tmp = 0b0000000000000000000000000000000000000000100000000000000000000000
    return Long.numberOfLeadingZeros(tmp) >>> 3; // 40 / 8 = 5
}

```

### A Microbenchmark

I like to find some evidence in favour of a change in idealised settings before committing to prototyping the change.
Though effects are often more pronounced in microbenchmarks than at system level, if I can't find evidence of improvement in idealised conditions _which I can easily control_, I wouldn't want to waste time and risk-budget hacking the change into existing code.
Contrary to widespread prejudice against microbenchmarking, I find a lot of bad ideas can be killed off quickly by spending a little bit of time doing bottom up experiments.

Despite that, it's very easy to write a microbenchmark to discard the branch-free implementation by creating very predictable benchmark data, and it's very common not to vary microbenchmark data much to avoid GC related noise.
The problem with making this comparison is that branch prediction is both effective and stateful on modern processors.
The branch predictor is capable of learning (and over-fitting to) the benchmark data; the benchmark must be able to maintain uncertainty without introducing other confounding factors. Dan Luu's [presentation](https://danluu.com/branch-prediction/) about branch predictors is excellent.

While the BSON attribute extraction use case is focused on very small strings, I also vary the length of the strings from very small to very large, with the null terminator at a random position within the last word of the input.
To make the data unpredictable without allocations causing problems, I generate lots of similar inputs and cycle through them on each invocation.
I want the cycling to be almost free so choose parameterised powers of two to vary the number of inputs.
When there aren't many inputs, the branchy version should be faster and the number of perf `branch-misses` should be low, and should slow down as more distinct inputs are provided.
That is, I expect the branch predictor to learn the benchmark data when too few distinct inputs are provided.
I expect the branch-free version to be unaffected by the variability of the input.
I called the branchy implementation "scan" and the branch-free implementation "swar".

Focusing only on the smaller inputs relevant to BSON parsing, it's almost as if I ran the benchmarks before making the predictions.
The benchmark was run on Ubuntu 18.04.3 LTS using OpenJDK 13, with a i7-6700HQ CPU.

| inputs | scan:branch-misses | scan:CPI | scan (ops/us) | swar (ops/us) | swar:CPI | swar:branch-misses|
|--------|--------------------|----------|---------------|---------------|----------|-------------------|
|128 | 0.00 | 0.24 | 210.94 | 205.42 | 0.26 | 0.00|
|256 | 0.00 | 0.24 | 210.53 | 205.00 | 0.26 | 0.00|
|512 | 0.00 | 0.25 | 208.37 | 205.33 | 0.26 | 0.00|
|1024 | 0.05 | 0.40 | 129.23 | 201.10 | 0.26 | 0.00|
|2048 | 0.50 | 0.55 | 91.41 | 204.32 | 0.27 | 0.00|
|4096 | 0.80 | 0.70 | 72.50 | 204.62 | 0.26 | 0.00|
|8192 | 0.90 | 0.75 | 67.31 | 204.60 | 0.26 | 0.00|
|16384 | 0.98 | 0.79 | 63.83 | 204.28 | 0.26 | 0.00|
|32768 | 0.98 | 0.80 | 62.13 | 204.26 | 0.26 | 0.00|

The far left column is the number of distinct inputs fed to the benchmark.
The inner two columns are the throughputs in operations per microsecond;
the branchy implementation (_scan_) reducing as a function of input variety;
the branch-free implementation (swar) constant.
_Cycles per instruction_ (CPI) is constant for the branch-free implementation;
the percentage of branches missed is noisy but stationary.
As input variety is increased, branch misses climb from 0 (the input has been learnt) to 0.98 per invocation, with CPI increasing in proportion.
This would have seemed like a really bad idea with just one random input.

> [Raw data](https://github.com/richardstartin/runtime-benchmarks/blob/master/findbyte-perfnorm.csv) and [benchmark](https://github.com/richardstartin/runtime-benchmarks/blob/master/src/main/java/com/openkappa/runtime/findbyte/FindByte.java).

### Searching for arbitrary bytes

Arbitrary sequences of bytes can be found by, in effect, modifying the input such that a search for a zero byte would produce the correct answer.
This can be done cheaply by XORing the input with the broadcast word of the sought byte.
For instance, line-feeds can be found:

```java

int position = firstInstance(getWord(new byte[]{1, 2, 0, 3, 4, 10, (byte)'\n', 5}, 0), compilePattern((byte)'\n');
...

private static long compilePattern(byte byteToFind) {
    long pattern = byteToFind & 0xFFL;
    return pattern
        | (pattern << 8)
        | (pattern << 16)
        | (pattern << 24)
        | (pattern << 32)
        | (pattern << 40)
        | (pattern << 48)
        | (pattern << 56);
}

private static int firstInstance(long word, long pattern) {
    long input = word ^ pattern;
    long tmp = (input & 0x7F7F7F7F7F7F7F7FL) + 0x7F7F7F7F7F7F7F7FL;
    tmp = ~(tmp | input | 0x7F7F7F7F7F7F7F7FL);
    return Long.numberOfLeadingZeros(tmp) >>> 3;
}
```

One of the benefits in working 64 bits at a time is reducing the number of load instructions required to scan the input.
Contrast this with the solution in [Netty](https://github.com/netty/netty/blob/00afb19d7a37de21b35ce4f6cb3fa7f74809f2ab/common/src/main/java/io/netty/util/ByteProcessor.java#L29),
which avoids bounds checks at the cost of a virtual call per byte.

```java
/**
 * A {@link ByteProcessor} which finds the first appearance of a specific byte.
 */
class IndexOfProcessor implements ByteProcessor {
    private final byte byteToFind;

    public IndexOfProcessor(byte byteToFind) {
        this.byteToFind = byteToFind;
    }

    @Override
    public boolean process(byte value) {
        return value != byteToFind;
    }
}

/**
 * Aborts on a {@code LF ('\n')}.
 */
ByteProcessor FIND_LF = new IndexOfProcessor(LINE_FEED);
```

This seems like such a narrow conduit to pipe data through, and here abstraction totally prevents doing something efficient.
Ultimately, we have APIs like this in Java because people (rightly) don't want to copy data, but the language lacks `const` semantics.
Hiding data and restricting access to it to tiny peepholes prevents getting anywhere near saturation of the hardware, and only much smarter JIT compilation (better inlining, better at spotting and rewriting idioms) could compensate for this.

### Vectorisation?

The branch-free algorithm is scalable in that it can mark bytes (that is, set interesting bytes to `0x80`) in as wide a word as you like.
With AVX-512 this means processing 64 bytes in parallel, which could be quite effective for large inputs.
The problem with vectorising the process is finding the leftmost tagged bit, because there's no built-in way of extracting it from the vector.
However, whenever there is no match, a zero vector will be produced, which can be tested.
When a non-zero vector is produced, the scalar values can be extracted and `Long.numberOfLeadingZeros` can be used to get the position of the tag bit.
This isn't branch-free, but it reduces the number of branches by a factor of the vector width.

This is the implementation based on a recent build (`50726e922bab01766162bdc1e28fc0a97725d3f0`) of the [vectorIntrinsics branch](https://github.com/openjdk/panama/tree/vectorIntrinsics) of the Vector API.

```java
public static int firstZeroByte(byte[] data) {
    int offset = 0;
    var holes = IntVector.broadcast(I256, 0x7F7F7F7F);
    var zero = IntVector.zero(I256);
    while (offset < data.length) {
        var vector = ByteVector.fromArray(B256, data, offset).reinterpretAsInts();
        offset += B256.length();
        var tmp = vector.and(holes)
                        .add(holes)
                        .or(vector)
                        .or(holes)
                        .not();
        if (!tmp.eq(zero).allTrue()) {
            var longs = tmp.reinterpretAsLongs();
            for (int i = 0; i < 4; ++i) {
                long word = longs.lane(i);
                if (word != 0) {
                    return offset - (i * Long.BYTES + Long.numberOfLeadingZeros(word) >>> 3);
                }
            }
        }
    }
    return -1;
}

```

This implementation is much faster than either scalar version, but highlights some of the potential pitfalls of the abstract nature of the Vector API.
Notice how `IntVector` rather than `LongVector` has been used in several places.
On a machine with AVX2, but not AVX-512, the more obvious choice of `LongVector` would lead to slow code, because the hardware doesn't support 64-bit vector addition.
This is a shortcoming of AVX2, rather than the Vector API, but the reality is that the programmer will probably need to consider hardware.
On the other hand, by the time the API is released, AVX-512, which is a much more complete offering, will probably be a lot more widespread.

The numbers below, for 1KB `byte[]`s, are not directly comparable to the numbers above because they were run with a custom built JDK, but give an idea of the possible improvement in throughput.


|inputs | scan:branch-misses | scan:CPI | scan (ops/us) | vector (ops/us) | vector:CPI | vector:branch-misses|
|-------|--------------------|----------|---------------|-----------------|------------|---------------------|
|128 | 1.89 | 0.30 | 3.16 | 13.12 | 0.30 | 0.02|
|256 | 1.98 | 0.30 | 3.16 | 12.90 | 0.31 | 0.01|
|512 | 1.85 | 0.30 | 3.16 | 12.53 | 0.32 | 0.02|
|1024 | 1.84 | 0.30 | 3.14 | 12.47 | 0.32 | 0.01|
|2048 | 1.92 | 0.30 | 3.13 | 11.69 | 0.34 | 0.01|
|4096 | 1.87 | 0.30 | 3.02 | 10.12 | 0.36 | 0.01|
|8192 | 1.84 | 0.31 | 2.67 | 7.84 | 0.40 | 0.03|
|16384 | 1.92 | 0.32 | 2.45 | 7.79 | 0.38 | 0.01|
|32768 | 1.87 | 0.32 | 2.46 | 7.55 | 0.41 | 0.02|



> [Raw data](https://github.com/richardstartin/vectorbenchmarks/blob/master/bytesearch-perfnorm.csv) and [benchmark](https://github.com/richardstartin/vectorbenchmarks/blob/master/bytesearch-perfnorm.csv)


















