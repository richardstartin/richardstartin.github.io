---
ID: 10694
post_title: Population Count in Java
author: Richard Startin
post_excerpt: ""
layout: post
permalink: >
  http://richardstartin.uk/population-count-in-java/
published: true
post_date: 2018-03-05 21:41:53
---
How do you count the bits in a 32 bit integer? Since this is possible in a single instruction, `popcntd`, which is exposed by an intrinsic method in Java and several other languages, this is a completely academic question. Nevertheless, however futile, deriving an efficient expression is instructive.

A naive approach would be to check each of the 32 bits in sequence. This can be written in Java as follows:

```java
  public static int populationCountCheckEachBit(int value) {
    int count = 0;
    for (int i = 0; i < Integer.SIZE; ++i) {
      if ((value & (1 << i)) != 0) {
        ++count;
      }
    }
    return count;
  }
```

This has constant and high execution time, even when most of the bits are unset: there will always be 32 left shifts and 32 intersections. There is no inherent data dependency in the loop above so it can probably be unrolled and pipelined, even so, it's just too long to be practically useful. A less naive approach is to skip over the unset bits, which will actually be quite fast when the data is sparse.

```java
  public static int populationCountSkipUnsetBits(int value) {
    int count = 0;
    while (value != 0) {
      value ^= value & -value;
      ++count;
    }
    return count;
  }
```

The code above calculates the lowest bit and unsets it until there are no bits left. In other languages, resetting the bit can use the `blsr` instruction, but C2 would emit code using `blsi` instruction and an `xor` here. This code will do well for sparse data, but has a data dependency and the performance will be <a href="http://richardstartin.uk/iterating-over-a-bitset-in-java/" rel="noopener" target="_blank">absolutely terrible</a> for dense data (such as small negative numbers).

Since an integer's population count is the sum of the population counts of its constituent bytes, and the population count of a byte can only take 256 values, why not precompute a small lookup table containing the population counts for each possible byte? Then, with four masks, three right shifts, four moves and three additions, the population count can be calculated. 

```java
   private static int[] LOOKUP = {
           0, 1, 1, 2, 1, 2, 2, 3,
           1, 2, 2, 3, 2, 3, 3, 4,
           1, 2, 2, 3, 2, 3, 3, 4,
           2, 3, 3, 4, 3, 4, 4, 5,
           1, 2, 2, 3, 2, 3, 3, 4,
           2, 3, 3, 4, 3, 4, 4, 5,
           2, 3, 3, 4, 3, 4, 4, 5,
           3, 4, 4, 5, 4, 5, 5, 6,
           1, 2, 2, 3, 2, 3, 3, 4,
           2, 3, 3, 4, 3, 4, 4, 5,
           2, 3, 3, 4, 3, 4, 4, 5,
           3, 4, 4, 5, 4, 5, 5, 6,
           2, 3, 3, 4, 3, 4, 4, 5,
           3, 4, 4, 5, 4, 5, 5, 6,
           3, 4, 4, 5, 4, 5, 5, 6,
           4, 5, 5, 6, 5, 6, 6, 7,
           1, 2, 2, 3, 2, 3, 3, 4,
           2, 3, 3, 4, 3, 4, 4, 5,
           2, 3, 3, 4, 3, 4, 4, 5,
           3, 4, 4, 5, 4, 5, 5, 6,
           2, 3, 3, 4, 3, 4, 4, 5,
           3, 4, 4, 5, 4, 5, 5, 6,
           3, 4, 4, 5, 4, 5, 5, 6,
           4, 5, 5, 6, 5, 6, 6, 7,
           2, 3, 3, 4, 3, 4, 4, 5,
           3, 4, 4, 5, 4, 5, 5, 6,
           3, 4, 4, 5, 4, 5, 5, 6,
           4, 5, 5, 6, 5, 6, 6, 7,
           3, 4, 4, 5, 4, 5, 5, 6,
           4, 5, 5, 6, 5, 6, 6, 7,
           4, 5, 5, 6, 5, 6, 6, 7,
           5, 6, 6, 7, 6, 7, 7, 8
   };

  public static int populationCountWithLookupTable(int value) {
    return LOOKUP[value & 0xFF]
         + LOOKUP[(value & 0xFF00) >>> 8]
         + LOOKUP[(value & 0xFF0000) >>> 16]
         + LOOKUP[(value & 0xFF000000) >>> 24];
   }
```

This isn't as stupid as it looks. The number of instructions is low and they can be pipelined easily. C2 obviously can't autovectorise this, but I imagine this could possibly end up being quite fast (if used in a loop) once the <a href="https://software.intel.com/en-us/articles/vector-api-developer-program-for-java" rel="noopener" target="_blank">Vector API</a> becomes a reality. Lemire and Muła devised a <a href="http://richardstartin.uk/project-panama-and-population-count/" rel="noopener" target="_blank">fast vectorised population count algorithm</a> based on a lookup table of precalculated population counts for each nibble. Their algorithm is used by clang to calculate the population count of an array, but is far beyond both the scope of this post and the capabilities of Java.

We can avoid storing the table while using very few instructions with a divide and conquer approach, writing the result in place. The first thing to notice is that the population count of `N` bits can be expressed in at most `N` bits. So, interpreting the integer as a 16 element string of 2-bit nibbles we can calculate each 2-bit population count and store it in the same 2 bit nibble.

The masks `0x55555555` and `0xAAAAAAAA` each have alternating bits and are logical complements. Remember that the population count is the sum of the population counts of the even bits and the odd bits. The code below calculates the number of bits in each 2-bit nibble and stores the result into the same 2-bit nibble. It works because the addition can only carry left into a zero bit (the odd bits have all been shifted right).

```java
     int output = (value & 0x55555555) // mask the even bits
                + ((value & 0xAAAAAAAA) >>> 1); // mask the odd bits and shift right so they line up with the even bits
```

By way of example, consider the input value `0b11001010101101010101010101010011`. The population count is 17, and the output takes the value `0b10000101011001010101010101010010`. Notice that no 2-bit nibble takes the value `0b11` - we have 16 values of either zero, one or two: `2 + 0 + 1 + 1 + 1 + 2 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 0 + 2 = 17`. It's not necessary to have two separate constants: `(value & 0xAAAAAAAA) >>> 1` is equivalent to `(value >>> 1) & 0x55555555`. This saves a register.

We now have a smaller problem: we need to add up the 16 2-bit nibbles. The mask `0x33333333` covers all the even 2-bit nibbles, and the mask `0xCCCCCCCC` covers all the odd 2-bit nibbles. Shifting the odd values right and adding them to the even ones gives eight nibbles consisting of the 4-bit population counts:
```java
     value = (value & 0x55555555) + ((value >>> 1) & 0x55555555); 
     value = (value & 0x33333333) + ((value >>> 2) & 0x33333333); 
```

Like before, the expression `(value & 0xCCCCCCCC) >>> 2` has been replaced by `(value >>> 2) & 0x33333333` to save a constant. Now we have eight nibbles to add up into four bytes, after that we have two shorts, and finally a single integer. The complete method ends up as follows:

```java
  public static int populationCountWithMasks(int value) {
    value = (value & 0x55555555) + ((value >>> 1) & 0x55555555);
    value = (value & 0x33333333) + ((value >>> 2) & 0x33333333);
    value = (value & 0x0F0F0F0F) + ((value >>> 4) & 0x0F0F0F0F);
    value = (value & 0x00FF00FF) + ((value >>> 8) & 0x00FF00FF);
    value = (value & 0x0000FFFF) + ((value >>> 16) & 0x0000FFFF);
    return value;
  }
```

You can almost see it already, but if you write the hexadecimal constants above in binary you will realise that this is quite an elegant solution: the masks look like a tree:

<pre>
01010101010101010101010101010101
00110011001100110011001100110011
00001111000011110000111100001111
00000000111111110000000011111111
00000000000000001111111111111111
</pre>

This elegance comes at a small cost. There are various profitable transformations, the simplest of which is the elision of the redundant final mask. The others are more involved and are covered in depth in chapter 5 of <em>Hacker's Delight</em>. The end result can be seen in the `Integer` class.

```java
    @HotSpotIntrinsicCandidate
    public static int bitCount(int i) {
        // HD, Figure 5-2
        i = i - ((i >>> 1) & 0x55555555);
        i = (i & 0x33333333) + ((i >>> 2) & 0x33333333);
        i = (i + (i >>> 4)) & 0x0f0f0f0f;
        i = i + (i >>> 8);
        i = i + (i >>> 16);
        return i & 0x3f;
    }
```

The method above is intrinsified by C2 to the instruction `popcntd` and this method is the only way to access the instruction from Java. If it's not already obvious, the power of having this access can be shown with a comparative benchmark.

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead><tr><th>Benchmark</th>
<th>Mode</th>
<th>Threads</th>
<th>Samples</th>
<th>Score</th>
<th>Score Error (99.9%)</th>
<th>Unit</th>
</tr></thead>
<tbody><tr>
<td>intrinsic</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">341.572057</td>
<td align="right">1.983535</td>
<td>ops/us</td>
</tr>
<tr>
<td>lookupTable</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">205.373131</td>
<td align="right">0.557472</td>
<td>ops/us</td>
</tr>
<tr>
<td>masks</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">191.744272</td>
<td align="right">1.942700</td>
<td>ops/us</td>
</tr>
<tr>
<td>naive</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">26.651332</td>
<td align="right">0.101285</td>
<td>ops/us</td>
</tr>
<tr>
<td>skipUnsetBits</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">94.125249</td>
<td align="right">0.559893</td>
<td>ops/us</td>
</tr>
</tbody></table>
</div>


Despite its power, since no vectorisation of this operation is possible prior to the AVX-512 VPOPCNTD/VPOPCNTQ extension (available virtually nowhere), loops containing `popcnt` can quickly become bottlenecks. Looking beneath the surface is intriguing. I'm sure with explicit vectorisation the lookup approach could be powerful.