---
title: UTF8 Encoding
layout: post
author: Richard Startin
date: 2020-08-06
tags: java 
image: /assets/2020/08/utf8-encoding/tbd.png
---

Earlier this year I started a new job doing something completely new to me: working on a tracing library.
This transition came with a few surprises; primarily how much textual data tracing can produce, and one of the first things I looked at was reducing the cost of serializing traces.
Whilst I did have some profiling data to look at, the first thing I actually did was read the source code of the serialization library.
I found this comment:

```java
// JVM performs various optimizations (memory allocation, reusing encoder etc.) when String.getBytes is used
byte[] bytes = s.getBytes(MessagePack.UTF8);
```

Just reading this comment made me wonder what would happen if I prevented this line of code from executing.

The library had a method which accepted a raw `byte[]` input, trusting the caller to ensure that the input valid UTF-8. For this particular problem, it would have been ideal not to have needed to do the conversion at all and replace the encoding with an allocation-free array copy; but since some of the strings were constants, the second best thing was to look the encodings for the constants up in a `HashMap<String, byte[]>` . This might not have been such a good idea if they were dynamic values because it would have swapped encoding for hashing. Despite this being only a tiny fraction of the strings which would need to be UTF-8 encoded, this reduced consumed CPU ticks by roughly 5%.

This turned out to be a rich seam for improved performance and this post goes into some of the gritty details of UTF-8 encoding in Java I encountered along the way.

1. TOC 
{:toc}

## A Quick Tour of Common Encodings

### UTF-8 Encoding

In the beginning there was ASCII, a 7-bit fixed length character encoding which supports just about anything anybody would want to write in English: 26 letters in each case; punctuation; numbers and arithmetic operators. ASCII can't even support cognate European alphabets, which led to a proliferation of encodings, each supporting the particular characters which make each European nation so special. UTF-8 is a superset of ASCII, and obviated many of these encodings. It can support virtually anything anybody in the world would want to write. 

One of the design goals of UTF-8 was to maintain backward compatibility with ASCII, so that existing ASCII data could be interpreted as UTF-8. This means that UTF-8 had to be a variable length encoding; ASCII characters needed to be represented with the 7-bit encoding, whilst supporting an array of new characters. Characters in UTF-8 may be represented by between one and four bytes. 

Since the most significant bit is always unset in ASCII, it is used to mark continuations of bytes encoding non-ASCII characters. If a character is encoded to a 2-byte sequence, then the first byte will be of the form by `0b110xxxxx`, and the second will be of the form `0b10xxxxxx`. Similarly, a when a character is encoded to a 3-byte sequence, the first byte is of the form `0b1110xxxx`, and the next two are of the form `0b10xxxxxx`. Finally, the encoding for a character requiring a 4-byte sequence will start with a byte of the form `0b11110xxx`, followed by three bytes of the form `0b10xxxxxx`.

Here are some examples of characters from different scripts which have different lengths when encoded in UTF-8.

| Character    | Encoding (Hex) | Encoding (Binary)                   |
| ------------ | -------------- | ----------------------------------- |
| a (English)  | 61             | 01100001                            |
| ß (German)   | c3 9f          | 11000011 10011111                   |
| 道 (Chinese) | e9 81 93       | 11101001 10000001 10010011          |
| 𠜎 (Chinese) | f0 a0 9c 8e    | 11110000 10100000 10011100 10001110 |

### ISO 8859-1 Encoding

*ISO 8859-1*, or _Latin 1_, is another extension of ASCII, which uses 8 bits per character and supports most Latin based scripts. It is a superset of ASCII, with some characters encoded to code points with the most significant bit set; mostly accented characters and commonly used symbols like currencies. Since it is also backwards compatible with ASCII, ISO 8859-1 overlaps with but is not compatible with UTF-8. For characters which have an 8-bit encoding in ISO 8859-1, the encoding can be translated to UTF-8 by moving the top two bits of the ISO 8859-1 byte to a second byte, and inserting the appropriate control bits in each byte. 

### UTF-16 Encoding

UTF-8 is an excellent encoding for English speakers, but less so for speakers of languages like Chinese, Japanese, and Korean. Characters from these languages typically require three to four bytes each, and a significant fraction of the bits required to encode these scripts are UTF-8 control bits. *UTF-16* broke compatibility with ASCII in order to provide an (overall) denser character space. All characters require at least 16 bits, and ASCII characters are identical except for an empty high byte. Characters which require three bytes in UTF-8 require just two in UTF-16, and those rare enough to require four bytes in UTF-8 also need four in UTF-16 (*surrogate pairs*). 

Whether this is good or not depends on perspective. As an English speaker, this encoding seems wasteful; it would roughly double the size of this text. For speakers of far eastern languages, UTF-16 must be a no-brainer. It seems to have been popular with language runtime designers too; Java's `char`s are encoded in UTF-16.

## The `String` class

### `char` and UTF-16/UTF-8 Conversion

Java's `char` values are UTF-16 encoded. Since UTF-8 is extremely popular on the web, and UTF-16 and UTF-8 are not compatible, this means that some encoding logic is likely required if you have a `char[]` and want to send it over the network. 

It's instructive to look at a few cases to understand how complex the translation process is.

Until `0x80`, each `char` is just ASCII with an empty high byte. 

```java
char c = (char)(utf8[0] & 0x7F);
```

| Character | UTF-8 (binary) | `char` (binary)      |
| --------- | -------------- | -------------------- |
| `a`       | `0b01100001`   | `0b0000000001100001` |

In 2-byte UTF-8 byte sequences, there are five control bits (three in the first byte and two in the second), so only 11 bits are required in a `char`. In the range `[0x80, 0x7FF]`, a Java `char`is just the lower bits of the UTF-8 bytes, realigned to 6 bits: 

```java
char c = (char)(((utf8[0] & 0x3F) << 6) | (utf8[1] & 0x1F));
```

| Character | UTF-8 (binary)            | `char` (binary)      |
| --------- | ------------------------- | -------------------- |
| `ß`       | `0b11000011` `0b10011111` | `0b0000000011011111` |

In a 3-byte UTF-8 sequence, there are 8 control bits so 16 bits is be enough after removing them.

```java
c = (char)(((utf8[0] & 0x3F) << 12) | ((utf8[1] & 0x3F) << 6) | (utf8[2] & 0x1F));
```

| Character | UTF-8 (binary)                         | `char` (binary)      |
| --------- | -------------------------------------- | -------------------- |
| `道`      | `0b11101001` `0b10000001` `0b10010011` | `0b1001000001010011` |

Characters rare enough to need four bytes, like 𠜎, don't fit into the 16 bits of a `char`, so they are represented as [UTF-16 surrogate pairs](https://en.wikipedia.org/wiki/UTF-16). The encoding of surrogate pairs is a bit more complicated than UTF-8's continuation bits, but they are just pairs of 16 bit integers in the range `[0xD800, 0xDFFF]`. The first `char`, or the _high surrogate_ can take any value in the range `[0xD800, 0xDBFF]`, and the second `char`, or the _low surrogate_ can take any value in the range `[0xDC00, 0xDFFF]`. 

| Character | UTF-8 (binary)                                      | `char` (binary)                           |
| --------- | --------------------------------------------------- | ----------------------------------------- |
| 𠜎        | `0b11110000` `0b10100000` `0b10011100` `0b10001110` | `0b1101100001000001` `0b1101111100001110` |

Java has the methods `Character.isSurrogate(char)`, `Character.isHighSurrogate(char)`, and `Character.isLowSurrogate(char)` for detecting surrogates, which just check if the character belongs to the appropriate range.

### Compact Strings

In JDK8, the internal representation of the `String` class was a `char[]`, requiring 16 bits per character. There is a lot of ASCII and ISO 8859-1 text out there, meaning that in lots of `String` objects, half the string, every other byte, would be empty. On top of this, UTF-16 is not a popular for data interchange, making encoding a very common task, but a `char[]` never has binary equivalence with the same text in a UTF-8 encoded `byte[]`. To convert a `char[]` into a UTF-8 encoded `byte[]` , there are a lot of data dependencies  making translation between the two is a laborious process.

In JDK9, [compact strings](https://openjdk.java.net/jeps/254) were introduced, which replaced the internal representation with a `byte[]`meaning that ASCII and ISO 8859-1 text could be stored using one `byte` per character, otherwise using the same UTF-16 encoding scheme but with two `bytes` in place of one `char`. 

As far as user data is concerned, the prevalence of ASCII and ISO 8859-1 text is an Anglophone phenomenon, but all users benefit to some extent from eliminating zero high bytes because so many identifiers in Java programs happen to be ASCII. Most of the long-lived strings like the class names `ClassLoader` uses to index class loading locks, or the strings representing class, method, and field names in constant pools are suddenly half the size, even if all the user data your program ever sees is Russian text.

Since JDK9, `String`s have had a `byte` field called `coder`which indicates which encoding is used. When constructing a string from a `byte[]`, the implementation differs according to the supplied `Charset` , but also according to the data itself. For instance, in the code below:

```java
new String(bytes, StandardCharsets.UTF_8);
```

The method `StringCoding.decodeUTF8` is called. The bytes are checked for negatives, and if no negatives are found, the more compact byte-per-character format is used, recording this decision with the `LATIN1` marker (excuse the `StringCoding`'s author's French):

```java
private static Result decodeUTF8(byte[] src, int sp, int len, boolean doReplace) {
    // ascii-bais, which has a relative impact to the non-ascii-only bytes
    if (COMPACT_STRINGS && !hasNegatives(src, sp, len))
        return resultCached.get().with(Arrays.copyOfRange(src, sp, sp + len),
                                       LATIN1);
    return decodeUTF8_0(src, sp, len, doReplace);
}
```

If you claim the input is ASCII:

```java
new String(bytes, StandardCharsets.US_ASCII);
```

You end up in `StringCoding.decodeASCII`, and the treatment is similar, despite the presence of negatives in ASCII indicating _data corruption_ as opposed to a need for extra space (the curse of backwards compatibility perhaps?). The encoding is conflated with ISO 8859-1 and is also marked with the `LATIN1` coder (ASCII is a subset of ISO 8859-1 so this is not incorrect):

```java
private static Result decodeASCII(byte[] ba, int off, int len) {
    Result result = resultCached.get();
    if (COMPACT_STRINGS && !hasNegatives(ba, off, len)) {
        return result.with(Arrays.copyOfRange(ba, off, off + len),
                           LATIN1);
    }
    byte[] dst = new byte[len<<1];
    int dp = 0;
    while (dp < len) {
        int b = ba[off++];
        putChar(dst, dp++, (b >= 0) ? (char)b : repl);
    }
    return result.with(dst, UTF16);
}
```

Conflation of ASCII with ISO 8859-1 seems unfortunate, given the prevalence of UTF-8 on the web. This creates work if the `String` is ever encoded to UTF-8 or ASCII. Even if a `String`'s contents are all ASCII characters, as far as the encoding logic can be aware, the contents _could_ be ISO 8859-1 encoded; it only has the bivalent field `coder` to go on. It isn't correct to copy just copy potentially ISO 8859-1 encoded bytes if the target is UTF-8 or ASCII, so the encoder has to check for negatives. 

See `StringCoding.encodeUTF8`:

```java
    private static byte[] encodeUTF8(byte coder, byte[] val, boolean doReplace) {
        if (coder == UTF16)
            return encodeUTF8_UTF16(val, doReplace);

        if (!hasNegatives(val, 0, val.length))
            return Arrays.copyOf(val, val.length);

        int dp = 0;
        byte[] dst = new byte[val.length << 1];
        for (int sp = 0; sp < val.length; sp++) {
            byte c = val[sp];
            if (c < 0) {
                dst[dp++] = (byte)(0xc0 | ((c & 0xff) >> 6));
                dst[dp++] = (byte)(0x80 | (c & 0x3f));
            } else {
                dst[dp++] = c;
            }
        }
        if (dp == dst.length)
            return dst;
        return Arrays.copyOf(dst, dp);
    }
```



The implementation strategy in the class `StringCoding` for cross encoding scenarios, where input encoding is assumed to be reliable and to be appropriate (i.e. that UTF-8 or ISO 8859-1 aren't used when ASCII would do), is outlined below. It's all reasonable, but doesn't isn't optimal for validated ASCII text.

| Input Encoding | Inferred Coder | Output Encoding | Ideal Implementation                         | Actual Implementation                                        |
| -------------- | -------------- | --------------- | -------------------------------------------- | ------------------------------------------------------------ |
| ASCII          | LATIN1         | ASCII           | Array copy                                   | Loop with replacement of negatives (see `StringCoding.encodeASCII`) |
| ASCII          | LATIN1         | ISO 8859-1      | Array copy                                   | Array copy (see `StringCoding.encode8859_1`)                 |
| ASCII          | LATIN1         | UTF-8           | Array copy                                   | negatives check before array copy (see `StringCoding.encodeASCII`) |
| ISO 8859-1     | LATIN1         | ASCII           | Loop with replacement of negatives           | Loop with replacement of negatives (see `StringCoding.encodeASCII`) |
| ISO 8859-1     | LATIN1         | ISO 8859-1      | Array copy                                   | Array copy (see `StringCoding.encode8859_1`)                 |
| ISO 8859-1     | LATIN1         | UTF-8           | Numerous approaches, including the one taken | Scan bytes, if no negatives are found, array copy, otherwise scan bytes again translating high code points to UTF-8 pairs where necessary (see `StringCoding.encodeUTF8`) |
| UTF-8          | UTF16          | ASCII           | Loop with replacement of negatives           | Loop with replacement of negatives (see `StringCoding.encodeASCII`) |
| UTF-8          | UTF16          | ISO 8859-1      | Numerous approaches, including the one taken | Map pairs of `byte`s to `char`s, for each `char`less than `0xFF`, cast to `byte`, otherwise, replace with an unencodable symbol (see `StringCoding.encode8859_1`). |
| UTF-8          | UTF16          | UTF-8           | Numerous approaches, including the one taken | Loop with fast path for ASCII. Slow path converts to `char` and handles specially according to value (ASCII, pair, triplet, surrogate) (see `StringCoding.encodeUTF8_UTF16`) |



## Performance Observations

### Is the allocation of `String.getBytes` ever eliminated?

As I mentioned before, when I avoided some of the calls to `String.getBytes(UTF_8)`I expected to save some cycles. The strings were constants, and their hash codes are computed early in the program's lifecycle, making the lookups cheap. However, I had expected that the allocation of the `byte[]` produced would have been eliminated since the strings are very small and the array is written to an output buffer almost immediately, and I expected that all of the methods which interact with the array would be inlined. So I just assumed that the compiler would figure out that the array doesn't escape and do something about it. That's not what happens, and the caching reduced allocation pressure too.

I have often found that even if C2's escape analysis leads to eliminated allocations in idealised microbenchmarks, it sometimes doesn't work when the surrounding context gets more complex. So to convince myself encoding a `String` will never eliminate the allocation of the `byte[]`, I tested it in the simplest possible setting. I created a benchmark which does nothing but get the encoding from the `String` which contains ASCII characters and return its length. As a control I added copying into a freshly allocated array; perhaps this allocation would be eliminated.



```java
    @Benchmark
    public int utf8EncodeLength(ASCIIStringState state) {
        return state.string.getBytes(StandardCharsets.UTF_8).length;
    }

    @Benchmark
    public int latin1EncodeLength(ASCIIStringState state) {
        return state.string.getBytes(StandardCharsets.ISO_8859_1).length;
    }

    @Benchmark
    public int asciiEncodeLength(ASCIIStringState state) {
        return state.string.getBytes(StandardCharsets.US_ASCII).length;
    }

    @Benchmark
    public int asciiEncodeLengthDirect(ASCIIStringState state) {
        return Arrays.copyOf(state.bytes, state.bytes.length).length;
    }
```



Perhaps this is a hard problem, but I was disappointed to find that the array always gets allocated, even without the complications of surrounding context, no matter what the target encoding. There is no fast path for ASCII which avoids the allocation. This is true in JDK11, where the contents of the produced `byte[]` are identical to the contents of the `String`, and in JDK15 early access. With compressed strings, getting a `byte[]` from `String.getBytes` is similar to copying a `byte[]`. 

| Benchmark                                   | Length | JDK   | Allocated Bytes |
| ------------------------------------------- | ------ | ----- | --------------- |
| asciiEncodeLength:·gc.alloc.rate.norm       | 4      | jdk8  | 96              |
| asciiEncodeLength:·gc.alloc.rate.norm       | 4      | jdk11 | 24              |
| asciiEncodeLength:·gc.alloc.rate.norm       | 4      | jdk15 | 24              |
| latin1EncodeLength:·gc.alloc.rate.norm      | 4      | jdk8  | 96              |
| latin1EncodeLength:·gc.alloc.rate.norm      | 4      | jdk11 | 24              |
| latin1EncodeLength:·gc.alloc.rate.norm      | 4      | jdk15 | 24              |
| utf8EncodeLength:·gc.alloc.rate.norm        | 4      | jdk8  | 160             |
| utf8EncodeLength:·gc.alloc.rate.norm        | 4      | jdk11 | 24              |
| utf8EncodeLength:·gc.alloc.rate.norm        | 4      | jdk15 | 24              |
| asciiEncodeLengthDirect:·gc.alloc.rate.norm | 4      | jdk8  | 24              |
| asciiEncodeLengthDirect:·gc.alloc.rate.norm | 4      | jdk11 | 24              |
| asciiEncodeLengthDirect:·gc.alloc.rate.norm | 4      | jdk15 | 24              |

### Allocation-Free UTF-8 Encoding

Allocating hundreds of megabytes per second calling `String.getBytes` is probably unacceptable if you have performance requirements, and, sadly, C2 doesn't help on any Hotspot version I tested. In an ideal world, if you have performance sensitive code processing lots of data, you just wouldn't be using the `String` class at all, but let's say you are, and you're constrained by your API to continue doing so. What's the best alternative?

The most obvious thing to do is to iterate over the `String`'s `char`s, recreating the rather complex encoding logic from the JDK's `StringCoding` class. In JDK11, this is rather unfortunate, given that there may be a perfectly good ASCII `byte[]` sitting inside the `String` (even if the `String` doesn't know it itself). It seems such a shame to need to UTF-16 encode it in order to access it without allocating profusely.

```java
        for (; i < string.length(); ++i) {
            char c = string.charAt(i);
            if (c < 0x80) {
                buffer.put((byte) c);
            } else if (c < 0x800) {
                buffer.putChar((char) (((0xC0 | (c >> 6)) << 8) | (0x80 | (c & 0x3F))));
            } else if (Character.isSurrogate(c)) {
                if (!Character.isHighSurrogate(c)) {
                    buffer.put((byte) '?');
                } else if (++i == string.length()) {
                    buffer.put((byte) '?');
                } else {
                    char next = string.charAt(i);
                    if (!Character.isLowSurrogate(next)) {
                        buffer.put((byte) '?');
                        buffer.put(Character.isHighSurrogate(next) ? (byte) '?' : (byte) next);
                    } else {
                        int codePoint = Character.toCodePoint(c, next);
                        buffer.putInt(((0xF0 | (codePoint >> 18)) << 24)
                                | ((0x80 | ((codePoint >> 12) & 0x3F)) << 16)
                                | ((0x80 | ((codePoint >> 6) & 0x3F)) << 8)
                                | ((0x80 | (codePoint & 0x3F))));
                    }
                }
            } else {
                buffer.put((byte)(0xE0 | c >> 12));
                buffer.put((byte)(0x80 | c >> 6 & 0x3F));
                buffer.put((byte)(0x80 | c & 0x3F));
            }
        }
```

The performance characteristics of this approach varies between JDK8 and JDK11, but it's actually a lot slower than calling `String.getBytes` and putting the allocated `byte[]` into the `ByteBuffer`. This is because of bounds checks, which are mostly eliminated from the call to `String.charAt`but not on the call to `ByteBuffer.put`.  In fact, `ByteBuffer.put` is bounds checked both manually (in the method `Buffer.nextPutIndex`) and automatically by the compiler. The loop below is actually unrolled twice.

```asm
  0.27%     ↗│  0x00007fefbd15b859: movzwl 0x12(%r14,%rbp,2),%ebp  ; String.charAt(i), no bounds check
  6.67%     ││  0x00007fefbd15b85f: cmp    $0x80,%ebp      ; if it's not an ASCII char, execute some code never executed in this benchmark 
            ││  0x00007fefbd15b865: jge    0x00007fefbd15b96c  
  0.34%     ││  0x00007fefbd15b86b: cmp    %ebx,%r9d       ; ByteBuffer manual bounds check (BUffer.nextPutIndex)
            ││  0x00007fefbd15b86e: jge    0x00007fefbd15b9b6 
  0.13%     ││  0x00007fefbd15b874: add    $0x3,%edi
  0.21%     ││  0x00007fefbd15b877: mov    %edi,0x18(%rcx)    
  6.75%     ││  0x00007fefbd15b87a: add    $0x2,%edx          
  0.21%     ││  0x00007fefbd15b87d: cmp    %esi,%edx       ; ByteBuffer.put bounds check inserted by compiler
            ││  0x00007fefbd15b87f: jae    0x00007fefbd15b91c
  0.38%     ││  0x00007fefbd15b885: mov    %bpl,0x12(%rax,%r10,1)
  4.75%     ││  0x00007fefbd15b88a: add    $0x2,%r11d 
  5.68%     ││  0x00007fefbd15b88e: cmp    0x70(%rsp),%r11d
            ╰│  0x00007fefbd15b893: jl     0x00007fefbd15b800 
  0.02%      │  0x00007fefbd15b899: vmovd  %xmm3,%r10d
             │  0x00007fefbd15b89e: mov    0x18(%r10),%edx    
  0.31%      │  0x00007fefbd15b8a2: vmovd  %xmm6,%r8d
  0.06%      │  0x00007fefbd15b8a7: cmp    %r8d,%r11d
             ╰  0x00007fefbd15b8aa: jge    0x00007fefbd15b661  
```

Bounds check-elimination seems to have improved markedly since JDK8 (which is a good reason to stop using JDK8 in itself). The pattern below is unrolled four times, and bounds checks moved to the start of the loop.

```asm
            │↗│  0x00007f9a783e72f0: movsbl 0x10(%r13,%rbx,1),%edi  ; String.charAt(i), loads a byte, no bounds check
  1.85%     │││  0x00007f9a783e72f6: mov    %edi,%edx
            │││  0x00007f9a783e72f8: movzbl %dl,%edx           
  4.89%     │││  0x00007f9a783e72fb: cmp    $0x80,%edx
  0.02%     │││  0x00007f9a783e7301: jge    0x00007f9a783e73f5  ; if it's not ASCII, execute some other code
            │││  0x00007f9a783e7307: mov    %ebx,%r8d
  1.71%     │││  0x00007f9a783e730a: inc    %r8d               
            │││  0x00007f9a783e730d: mov    %r8d,0x18(%rax)    ; Buffer.nextPutIndex, no conditional
 10.20%     │││  0x00007f9a783e7311: mov    %ebx,%r9d
            │││  0x00007f9a783e7314: add    %r14d,%r9d         
  0.31%     │││  0x00007f9a783e7317: mov    %dil,0x10(%r10,%r9,1)  ; ByteBuffer.put, no bounds check
```

Unfortunately, this is still a lot slower than calling `String.getBytes`.

One way around this is to use `sun.misc.Unsafe` and to handle JDK8 and JDK9+ differently, perhaps with Multi-Release jars, but let's suppose someone tells you that you can't. If you _know_ the data is all ISO 8859-1 encoded, and you need to produce UTF-8, there's a safe trick exploiting the fact that ASCII characters won't have the most significant bit set which reduces the number of bounds checks significantly.

The idea is to accumulate the `char`s into a `long`, and then check that all 8 `char`s are ASCII at once by comparing them to a mask with each eighth bit unset. If the check fails, or there aren't 8 characters left, the slow path is fallen back to. This is not safe to do if you don't know the input is ISO 8859-1 or ASCII.

```java
        while (i < s.length()) {
            if (i + 7 < s.length()) {
                // bounds check elimination:
                // ASCII text will never use more than 7 bits per character,
                // we can detect non latin 1 and revert to a slow path by
                // merging the chars and checking every 8th bit is empty
                long word = s.charAt(i);
                word = (word << 8 | s.charAt(i + 1));
                word = (word << 8 | s.charAt(i + 2));
                word = (word << 8 | s.charAt(i + 3));
                word = (word << 8 | s.charAt(i + 4));
                word = (word << 8 | s.charAt(i + 5));
                word = (word << 8 | s.charAt(i + 6));
                word = (word << 8 | s.charAt(i + 7));
                if ((word & 0x7F7F7F7F7F7F7F7FL) == word) {
                    buffer.putLong(word);
                    i += 8;
                    continue;
                }
            }
            // input length not multiple of 8 or encountered non ASCII character, go to slow path
            encode(i, s, buffer);
            return;
        }
    }
```

This is significantly faster than performing the encoding `char` by `char`, if your `String` is ASCII, and actually your best option (assuming performance is prioritised over readability) on JDK8. 

![JDK8](/assets/2020/08/utf8-encoding/encoding_jdk8.png)

![JDK11](/assets/2020/08/utf8-encoding/encoding_jdk11.png)

![JDK15](/assets/2020/08/utf8-encoding/encoding_jdk15.png)