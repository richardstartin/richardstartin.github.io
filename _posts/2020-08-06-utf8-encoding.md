---
title: UTF8 Encoding
layout: post
author: Richard Startin
date: 2020-08-06
tags: java 
image: /assets/2020/08/utf8-encoding/tbd.png
---

Earlier this year I started a new job doing something completely new to me: working on a tracing library.
This transition came with a few surprises; primarily how much textual data tracing can produce, and one of the first things I looked at was reducing the cost of serialising traces.
Whilst I did have some profiling data to look at, the first thing I actually did was read the source code of the serialisation library.
I found this comment:

```java
// JVM performs various optimizations (memory allocation, reusing encoder etc.) when String.getBytes is used
byte[] bytes = s.getBytes(MessagePack.UTF8);
```

Just reading this comment made me wonder what would happen if I prevented this line of code from executing.

Since some of strings being serialised were constants, it took all of five minutes to cache their UTF-8 encodings in a `HashMap<String, byte[]>` in order to use a method which accepts `byte[]` inputs.
Despite this being only a tiny fraction of the strings which would need to be UTF-8 encoded, this reduced CPU utilisation by roughly 5%.
Since I have inordinate faith in the brilliance of JIT compilers and therefore expected the allocations of these small arrays to have been eliminated, I was surprised to find that the change had also reduced allocation pressure commensurately.
This turned out to be a rich seam and this post goes into some of the gritty details of UTF-8 encoding in Java I encountered along the way.

1. TOC 
{:toc}

### What is UTF-8?

In the beginning there was ASCII, a 7-bit fixed length character encoding which supports just about anything anybody would want to write in English: 26 letters in each case; punctuation; numbers and arithmetic operators. ASCII can't even support cognate European alphabets, which led to a proliferation of encodings, each supporting the particular characters which make each European nation so special. UTF-8, a variable length encoding which is a superset of ASCII, obviated many if these encodings and can support virtually anything anybody in the world would want to write. 

Importantly, UTF-8 is a variable length encoding; characters may be represented by between one and four bytes. Any ASCII character has the same encoding in UTF-8. Since the most significant bit is always unset in ASCII, it is used to mark continuations of bytes encoding non-ASCII characters. If a character is encoded to a 2-byte sequence, then the first byte will be of the form by `0b110xxxxx`, and the second will be of the form `0b10xxxxxx`. Similarly, a when a character is encoded to a 3-byte sequence, the first byte is of the form `0b1110xxxx`, and the next two are of the form `0b10xxxxxx`. Finally, the encoding for a character requiring a 4-byte sequence will start with a byte of the form `0b11110xxx`, followed by three bytes of the form `0b10xxxxxx`.

Here are some examples of characters from different scripts which have different lengths when encoded in UTF-8.

| Character    | Encoding (Hex) | Encoding (Binary)                   |
| ------------ | -------------- | ----------------------------------- |
| a (English)  | 61             | 01100001                            |
| ß (German)   | c3 9f          | 11000011 10011111                   |
| 道 (Chinese) | e9 81 93       | 11101001 10000001 10010011          |
| 𠜎 (Chinese) | f0 a0 9c 8e    | 11110000 10100000 10011100 10001110 |

This has a couple of immediate consequences: 

* UTF-8 prioritises the needs of English speakers over anyone else in the name of backward compatibility.
* Depending on how the characters are represented, encoding could be as simple as an array copy, or a relatively complex loop.
* UTF-8's backward compatibility with ASCII presents speculative optimisation opportunities when handling machine generated text, which is typically pseudo-English.

### What is ISO 8859-1?

ISO 8859-1, or _Latin 1_, is another extension of ASCII, which uses 8 bits per character and supports most Latin based scripts. It is a superset of ASCII, with some characters encoded to code points with the most significant bit set; mostly accented characters and common symbols like currencies. For characters which have an 8-bit encoding in ISO 8859-1, the encoding can be translated to UTF-8 by moving the top two bits of the ISO 8859-1 byte to the second byte, and inserting the appropriate control bits in each byte.

### What is a Java char?

`char` is a 16 bit integer, and Java's only unsigned type. `char` values are encoded in UTF-16, which packs characters into its address space more densely at the expense of using more bytes per character at the lower end of the address space. The reason for doing this is if a `char` has just 16 bits, binary equivalence with UTF-8, beyond the ASCII characters, would be wasteful. The range `[0x80, 0xFF]`would need to be empty, and characters like 道 would be impossible to encode in a single `char`. In UTF-16, the range `[0x80, 0xFF]` contains the characters found in ISO 8859-1 such as the Icelandic þ (`c3 be` in UTF-8), and the Chinese character 道 is the `char` `0x9053`. So `char` values beyond the ASCII range don't have binary equivalence with UTF-8. It's instructive to look at a few cases to understand how complex the translation process is.

Before `0x80`, each `char` is just ASCII with an empty high byte. 

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

The conclusion of the last two sections is that a `char[]` never has binary equivalence with the same text in a UTF-8 encoded `byte[]`. Translation between the two is a relatively laborious process, involving various range checks, shifts, and masks. 

In JDK8 and before, the internal representation of a `String` was a `char[]`, even though an awful lot of `String`s are ASCII or ISO 8859-1 and could be half the size if stored in a `byte[]`. In JDK9, [compact strings](https://openjdk.java.net/jeps/254) were introduced, which replaced the internal representation with a `byte[]`meaning that ASCII and ISO 8859-1 text could be stored using one `byte` per character, otherwise using the same UTF-16 encoding scheme but with two `bytes` in place of one `char`. 

As far as user data is concerned, the prevalence of ASCII and ISO 8859-1 text is an Anglophone phenomenon, but all users benefit to some extent from eliminating zero high bytes because so many identifiers in Java programs happen to be ASCII. Most of the long-lived strings like the class names `ClassLoader` uses to index class loading locks, or the strings representing class, method, and field names in constant pools are suddenly half the size, even if all the user data your program ever sees is Russian text.

Since JDK9, when constructing a string from a `byte[]`, the bytes are checked for negatives, and if no negatives are found, the more compact byte-per-character format is used, recording this decision with the `LATIN1` marker (excuse the `StringCoding`'s author's French):

```java
private static Result decodeUTF8(byte[] src, int sp, int len, boolean doReplace) {
    // ascii-bais, which has a relative impact to the non-ascii-only bytes
    if (COMPACT_STRINGS && !hasNegatives(src, sp, len))
        return resultCached.get().with(Arrays.copyOfRange(src, sp, sp + len),
                                       LATIN1);
    return decodeUTF8_0(src, sp, len, doReplace);
}
```

ASCII gets similar treatment, despite the presence of negatives in ASCII indicating _data corruption_ as opposed to needing more space (the curse of backwards compatibility?), ends up marked indistinguishably from ISO 8859-1 with the `LATIN1` coder:

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



Encoding the contents of a string _known to be ASCII_ could just be an array copy for all target encodings except UTF-16, but that's not what happens. The implementation strategy in the class `StringCoding` for cross encoding scenarios, where input encoding is assumed to be reliable and to be appropriate (i.e. that UTF-8 or ISO 8859-1 aren't used when ASCII would do), is outlined below. It's all reasonable, but doesn't isn't optimal for validated ASCII text.

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



### Is the allocation of `String.getBytes` ever eliminated?

As I mentioned before, when I avoided some of the calls to `String.getBytes(UTF_8)`I expected to save some cycles. The strings were compile time constants, and their hash codes are computed early in the program's lifecycle, making the lookups cheap. However, I had expected that the allocation of the `byte[]` produced would have been eliminated since the strings are very small and the array is written to an output buffer almost immediately, and I expected that all of the methods which interact with the array would be inlined. So I just assumed that the compiler would figure out that the array doesn't escape and do something about it. That's not what happens, and the caching reduced allocation pressure too.

I have often found that even if C2's escape analysis works in idealised microbenchmarks, it often doesn't work when the surrounding code gets more complex. To convince myself encoding a `String` will always allocate the `byte[]` no matter what, I created a benchmark which does nothing but get the encoding from the `String` which contains ASCII characters and return its length. As a control I added doing the same thing but copying from an array, which is what I think, holding the API constant, the operation should reduce to if it's known the `String` is ASCII and `String.getBytes` inlines.



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



Perhaps this is a hard problem, but I was disappointed to find that the array always gets allocated, even without the complications of surrounding context, no matter what the target encoding. There is no fast path for ASCII which avoids the allocation. This is true in JDK11, where the contents of the produced `byte[]` are identical to the contents of the `String`, and in JDK15 early access.

### Allocation-Free UTF-8 Encoding

Allocating hundreds of megabytes per second calling `String.getBytes` is probably unacceptable if you have performance requirements. In an ideal world, if you have performance sensitive code processing lots of data, you just wouldn't be using the `String` class at all, but let's say you are, and you're constrained by your API to continue doing so. What's the best alternative?

The most obvious thing to do is to iterate over the `String`'s `char`s, recreating the rather complex encoding logic from the JDK's `StringCoding` class. In JDK11, this is rather unfortunate, given that there may be a perfectly good ASCII `byte[]` sitting inside the `String`. It seems such a shame to need to UTF-16 encode it in order to access it without allocating profusely.

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

The performance characteristics of this approach varies between JDK8 and JDK11, but it's actually a lot slower than calling `String.getBytes` and putting the `byte[]` into the `ByteBuffer`. The reason why is bounds checks, both on the call to `String.charAt`and on the call to `ByteBuffer.put`. Bounds check-elimination on the call to `String.charAt` seems to have improved markedly since JDK8 (which is a good reason to stop using JDK8 in itself) but the elimination of bounds checks on `ByteBuffer.put` do not seem to have improved.

One way around this is to use `sun.misc.Unsafe` and to handle JDK8 and JDK9+ differently, perhaps with Multi-Release jars. There's often a lot of pushback against doing things like this though. If you have good reason to believe that most of the text being handled is ASCII, there's a safe trick exploiting the fact that ASCII characters won't have the most significant bit set which reduces the number of bounds checks significantly.

The idea is to accumulate the `char`s into a `long`, and then check that all 8 `char`s are ASCII at once by comparing them to a mask with each eighth bit unset. If the check fails, or there aren't 8 characters left, the slow path is fallen back to.

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

This is significantly faster than performing the encoding `char` by `char`, if your `String` is ASCII, and actually your best option (assuming performance is prioritised over readability) on JDK8. Still, it's hard not to feel sour that you can't have direct access to the perfectly good ASCII encoded bytes inside the `String` in JDK11  (or that you have to use the `String` class for a performance sensitive task for historical reasons).