---
ID: 11190
title: Base64 Encoding
author: Richard Startin
post_excerpt: ""
layout: post
published: true
date: 2018-08-12 20:22:04
---
Base64 encoding is the standard mechanism of converting binary data to text, and is used extensively in web technologies. You will encounter it wherever binary data such as authentication tokens or compressed BLOBs meet JSON. 

There are two common Base64 encoding formats: a standard format and an URL-safe format which replaces '/' with '_' and '+' with '-'. Base64 uses ASCII characters which require just a byte each, but since each byte encodes six bits, the output is always 33% larger than the input. It's a very simple two stage process to encode a sequence of bytes as text:

<ol>
	<li>For each three byte sequence shift each 6-bit subword onto 8-bit boundaries to produce four bytes</li>
	<li>For each of the four intermediate bytes, locate a character in a 64 element lookup table corresponding to the format being used.</li>
</ol> 

It's easy to implement:

```java
    int i = 0;
    int j = 0;
    // 3 bytes in, 4 bytes out
    for (; j + 3 < out.length && i + 2 < in.length; i += 3, j += 4) {
      // map 3 bytes into the lower 24 bits of an integer
      int word = (in[i + 0] & 0xFF) << 16 | (in[i + 1] & 0xFF) << 8 | (in[i + 2] & 0xFF);
      // for each 6-bit subword, find the appropriate character in the lookup table
      out[j + 0] = ENCODING[(word >>> 18) & 0x3F];
      out[j + 1] = ENCODING[(word >>> 12) & 0x3F];
      out[j + 2] = ENCODING[(word >>> 6) & 0x3F];
      out[j + 3] = ENCODING[word & 0x3F];
    }
```

Since JDK8 there has been `java.util.Base64.Encoder` which benchmarks favourably against older library implementations. How does it work? The best way to find out is always JMH perfasm. Here's the hottest part of the encoding loop for a `byte[]` (JDK10 on Ubuntu), annotated to explain what is going on.

```asm
                  ╭        0x00007f02993ad1e9: jge    0x00007f02993ad3ae  
                  │        0x00007f02993ad1ef: mov    %r13d,%edx
                  │        0x00007f02993ad1f2: xor    %r10d,%r10d
  0.01%    0.00%  │╭       0x00007f02993ad1f5: jmpq   0x00007f02993ad305
                  ││       0x00007f02993ad1fa: nopw   0x0(%rax,%rax,1)
  2.36%    2.08%  ││ ↗     0x00007f02993ad200: add    $0x4,%r10d         
  2.33%    2.11%  ││ │     0x00007f02993ad204: mov    %r8d,%esi          
  2.38%    2.17%  ││ │  ↗  0x00007f02993ad207: vmovq  %xmm0,%r11              ; overflow into FPU has occurred, move byte from SSE register just in time
-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  2.34%    2.21%  ││ │  │  0x00007f02993ad20c: movzbl 0x10(%r11,%rsi,1),%r11d ; load the first input byte
  2.34%    2.21%  ││ │  │  0x00007f02993ad212: shl    $0x10,%r11d             ; shift the first input byte into the third byte of the intermediate dword (r11d)  
  2.43%    2.17%  ││ │  │  0x00007f02993ad216: mov    %esi,%r8d
  2.35%    2.34%  ││ │  │  0x00007f02993ad219: add    $0x3,%r8d          
  2.37%    2.20%  ││ │  │  0x00007f02993ad21d: movslq %esi,%rax
  2.36%    2.18%  ││ │  │  0x00007f02993ad220: mov    %r10d,%edi
  2.38%    2.69%  ││ │  │  0x00007f02993ad223: inc    %edi               
  2.38%    2.77%  ││ │  │  0x00007f02993ad225: vmovq  %xmm0,%rsi              ; floating point spill, move to rsi just in time to load the byte
  2.31%    2.71%  ││ │  │  0x00007f02993ad22a: movzbl 0x12(%rsi,%rax,1),%esi  ; load the third input byte 
  2.41%    2.77%  ││ │  │  0x00007f02993ad22f: vmovq  %xmm0,%rbp
  2.37%    2.26%  ││ │  │  0x00007f02993ad234: movzbl 0x11(%rbp,%rax,1),%eax  ; load the second input byte
  2.34%    2.19%  ││ │  │  0x00007f02993ad239: shl    $0x8,%eax               ; shift the second input byte into the second byte of r11d
  2.28%    2.17%  ││ │  │  0x00007f02993ad23c: or     %eax,%r11d              ; combine the second byte with the intermediate dword (disjoint union, byte 2 now in second byte of dword)
  2.39%    2.14%  ││ │  │  0x00007f02993ad23f: or     %esi,%r11d              ; combine the third byte with the intermediate word (disjoint union, byte 3 now in lower order bits of dword)
-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  2.28%    2.72%  ││ │  │  0x00007f02993ad242: mov    %r11d,%esi              ; encoding starts here, copies the intermediate word in esi to break dependency on r11d
  2.29%    2.67%  ││ │  │  0x00007f02993ad245: shr    $0x12,%esi              ; shift copy of dword right 18 (careful: 12 = $0xC :)) bits
  2.27%    2.78%  ││ │  │  0x00007f02993ad248: and    $0x3f,%esi              ; mask to get 6 bits (one position in lookup table computed and stored in esi now)   
  2.37%    2.79%  ││ │  │  0x00007f02993ad24b: movzwl 0x10(%r14,%rsi,2),%eax  ; load the character encoding the first byte
  2.54%    2.29%  ││ │  │  0x00007f02993ad251: cmp    %edx,%r10d
                  ││╭│  │  0x00007f02993ad254: jae    0x00007f02993ad469
  2.29%    2.22%  ││││  │  0x00007f02993ad25a: mov    %al,0x10(%r9,%r10,1)  
  2.43%    2.29%  ││││  │  0x00007f02993ad25f: mov    %r10d,%eax
  2.33%    2.16%  ││││  │  0x00007f02993ad262: add    $0x3,%eax
  2.34%    2.14%  ││││  │  0x00007f02993ad265: mov    %r11d,%esi
  2.37%    2.24%  ││││  │  0x00007f02993ad268: shr    $0xc,%esi               ; shift a copy of the dword right by 12 bits  
  2.36%    2.26%  ││││  │  0x00007f02993ad26b: and    $0x3f,%esi              ; mask it to get 6 bits
  2.26%    2.83%  ││││  │  0x00007f02993ad26e: movzwl 0x10(%r14,%rsi,2),%esi  ; load the character encoding for the second output byte
  2.37%    2.72%  ││││  │  0x00007f02993ad274: cmp    %edx,%eax
                  ││││  │  0x00007f02993ad276: jae    0x00007f02993ad4bd
  2.27%    2.80%  ││││  │  0x00007f02993ad27c: mov    %r11d,%edi              ; copy the intermediate word
  2.43%    2.81%  ││││  │  0x00007f02993ad27f: and    $0x3f,%edi              ; mask the lower 6 bits
  2.29%    2.12%  ││││  │  0x00007f02993ad282: movzwl 0x10(%r14,%rdi,2),%eax  ; load the character encoding for the fourth output byte
  2.36%    2.22%  ││││  │  0x00007f02993ad288: shr    $0x6,%r11d              ; shift the word 6 bits right
  2.31%    2.15%  ││││  │  0x00007f02993ad28c: and    $0x3f,%r11d             ; mask the lower 6 bits
  2.40%    2.26%  ││││  │  0x00007f02993ad290: movzwl 0x10(%r14,%r11,2),%r11d ; load the character encoding for third output byte 
```

The first thing to notice is there are several XMM registers used, but no vectorisation: these are <a href="https://shipilev.net/jvm-anatomy-park/20-fpu-spills/" rel="noopener" target="_blank">floating point spills</a> and their presence indicates register pressure. Hotspot stores variables in XMM registers to avoid storing the variable somewhere costlier to fetch from, but instructions for manipulating bytes and integers can't take an XMM register as an operand, so the variable is always moved to an appropriate register just in time. Note that in the perfasm output, the target of the move from the XMM register is always used as an operand immediately after the move.

The middle section above is spent collecting the three input bytes into an integer, the time spent here is roughly one third of the total runtime of the method. Some of the section is executed in parallel: loading the input bytes is independent, but combining them is sequential. The intermediate integer is then copied several times before doing the encoding lookup, meaning the four lookups happen independently. Roughly 45% of the time is spent here. 

Can this code be vectorised? Yes: Wojciech Mula has a <a href="http://0x80.pl/notesen/2016-01-12-sse-base64-encoding.html" rel="noopener" target="_blank">blog post</a> on this topic, and wrote a <a href="https://arxiv.org/pdf/1704.00605.pdf" rel="noopener" target="_blank">paper</a> with Daniel Lemire. I read both of these references recently. Their approach is roughly ten times faster than their scalar baseline, which is virtually identical to the JDK implementation.

The AVX2 version of their algorithm starts by loading 32 bytes into a YMM register, but making sure that the 24 bytes of interest are loaded into the centre of the register, that is, the 4 bytes at either end are rubbish and will be ignored. This is achieved by loading at an offset of -4, which is quite problematic in a safe language like Java. The 24 bytes in the middle of the register are then permuted so some permutation (with duplication) of each 3 byte sequence is contained within a 4 byte lane.

<pre>
load 24 bytes centred in a 256-bit register
|**-**-**-**|A1-A2-A3-B1|B2-B3-C1-C2|C3-D1-D2-D3|E1-E2-E3-F1|F2-F3-G1-G2|G3-H1-H2-H3|**-**-**-**|
permute the bytes of the LHS
|10-11- 9-10| 7- 8- 6- 7| 4- 5- 3- 4| 1- 2- 0- 1|
|**-**-**-**|A1-A2-A3-B1|B2-B3-C1-C2|C3-D1-D2-D3|E1-E2-E3-F1|F2-F3-G1-G2|G3-H1-H2-H3|**-**-**-**|
|A2-A3-A1-A2|B2-B3-B1-B2|C2-C3-C1-C2|D2-D3-D1-D2|E1-E2-E3-F1|F2-F3-G1-G2|G3-H1-H2-H3|**-**-**-**|
permute the bytes of the RHS 
                                                |14-15-13-14|11-12-10-11| 8- 9- 7- 8| 5- 6- 4- 5|
|A2-A1-A3-A2|B2-B1-B3-B2|C2-C1-C3-C2|D2-D1-D3-D2|E1-E2-E3-F1|F2-F3-G1-G2|G3-H1-H2-H3|**-**-**-**|
|A2-A3-A1-A2|B2-B3-B1-B2|C2-C3-C1-C2|D2-D3-D1-D2|E2-E3-E1-E2|F2-F3-F1-F2|G2-G3-G1-G2|H2-H3-H1-H2|
</pre> 

It looks like the ordering is wrong, and the second byte is always duplicated, but it's intentional. Now the bytes are in the correct integer lanes, in order to use them as indexes into the encoding lookup table, the four 6-bit sequences need to be extracted by masking and shifting into the right positions.

Each 24-bit sequence has undergone the following transformation, where the letter indicates the 6-bit sequence, but the number indicates the bit number, with 8 bit lanes:

<pre>
|         PREVIOUS      |           A1          |           A2          |          A3           |
|**-**-**-**-**-**-**-**|a8-a7-a6-a5-a4-a3-b2-b1|b8-b7-b6-b5-c4-c3-c2-c1|c8-c7-d6-d5-d4-d3-d2-d1|
|           A2          |           A3          |           A1          |          A2           |
|b8-b7-b6-b5-c4-c3-c2-c1|c8-c7-d6-d5-d4-d3-d2-d1|a8-a7-a6-a5-a4-a3-b2-b1|b8-b7-b6-b5-c4-c3-c2-c1|
</pre>

Based on the input integer and its shuffled form above, the target structure of each integer prior to encoding is:

<pre>
|**-**-**-**-**-**-**-**|a8-a7-a6-a5-a4-a3-b2-b1|b8-b7-b6-b5-c4-c3-c2-c1|c8-c7-d6-d5-d4-d3-d2-d1|
|b8-b7-b6-b5-c4-c3-c2-c1|c8-c7-d6-d5-d4-d3-d2-d1|a8-a7-a6-a5-a4-a3-b2-b1|b8-b7-b6-b5-c4-c3-c2-c1|
|00-00-d6-d5-d4-d3-d2-d1|00-00-c4-c3-c2-c1-c8-c7|00-00-b2-b1-b8-b7-b6-b5|00-00-a8-a7-a6-a5-a4-a3|
</pre>

So, sequence c needs to move 6 bits right and sequence a must move right by 10 bits. AVX2 doesn't make it possible to do both of these shifts at once. So the following operations could be performed:

<pre>
mask a
| 0- 0- 0- 0- 0- 0- 0- 0| 0- 0- 0- 0- 0- 0- 0- 0| 1- 1- 1- 1- 1- 1- 0- 0| 0- 0- 0- 0- 0- 0- 0- 0|
|b8-b7-b6-b5-c4-c3-c2-c1|c8-c7-d6-d5-d4-d3-d2-d1|a8-a7-a6-a5-a4-a3-b2-b1|b8-b7-b6-b5-c4-c3-c2-c1|
|00-00-00-00-00-00-00-00|00-00-00-00-00-00-00-00|a8-a7-a6-a5-a4-a3-00-00|00-00-00-00-00-00-00-00|
shift right 10 bits
|00-00-00-00-00-00-00-00|00-00-00-00-00-00-00-00|00-00-00-00-00-00-00-00|00-00-a8-a7-a6-a5-a4-a3|
mask c
| 0- 0- 0- 0- 1- 1- 1- 1| 1- 1- 0- 0- 0- 0- 0- 0| 0- 0- 0- 0- 0- 0- 0- 0| 0- 0- 0- 0- 0- 0- 0- 0|
|b8-b7-b6-b5-c4-c3-c2-c1|c8-c7-d6-d5-d4-d3-d2-d1|a8-a7-a6-a5-a4-a3-b2-b1|b8-b7-b6-b5-c4-c3-c2-c1|
|00-00-00-00-c4-c3-c2-c1|c8-c7-00-00-00-00-00-00|00-00-00-00-00-00-00-00|00-00-00-00-00-00-00-00|
shift right 6 bits
|00-00-00-00-00-00-00-00|00-00-c4-c3-c2-c1-c8-c7|00-00-00-00-00-00-00-00|00-00-00-00-00-00-00-00|
union
|00-00-00-00-00-00-00-00|00-00-00-00-00-00-00-00|00-00-00-00-00-00-00-00|00-00-a8-a7-a6-a5-a4-a3|
|00-00-00-00-00-00-00-00|00-00-c4-c3-c2-c1-c8-c7|00-00-00-00-00-00-00-00|00-00-00-00-00-00-00-00|
|00-00-00-00-00-00-00-00|00-00-c4-c3-c2-c1-c8-c7|00-00-00-00-00-00-00-00|00-00-a8-a7-a6-a5-a4-a3|
</pre>

However, that's two masks, two shifts and a union, and needs several registers for temporary results. A single mask can be created by broadcasting `0x0fc0fc00` and two independent 16 bit shifts can be emulated in a single instruction with a special multiplication, using the semantic snowflake <a href="https://software.intel.com/sites/landingpage/IntrinsicsGuide/#techs=AVX2&text=_mm256_mulhi_epi16">vpmulhuw</a>, which does an unsigned 16-bit multiplication, storing the upper 16-bits.

Sequence b needs to shift left 4 bits, and sequence d needs to shift left 8 bits. Rather than use two separate masks and shifts, a single  <a href="https://software.intel.com/sites/landingpage/IntrinsicsGuide/#techs=AVX2&text=_mm256_mullo_epi16">vpmullw</a>, an unsigned multiplication outputting the lower 16 bits, achieves the shifts after masking with `0x003f03f0`,. This result is united with the result of the first multiplication to get the correct output.

<pre>
|00-00-d6-d5-d4-d3-d2-d1|00-00-c4-c3-c2-c1-c8-c7|00-00-b2-b1-b8-b7-b6-b5|00-00-a8-a7-a6-a5-a4-a3|
</pre>

Now for the encoding itself! One approach would be to dump the content of the vector into a byte array and use scalar code to do the lookups just like the JDK implementation does, but this stage accounted for 45% of the execution time in the scalar implementation, so the encoding needs to use vector instructions too.

If base 64 used only characters in the range `[0, 64)`, the lookup would be expressible as a closed permutation of the indices, albeit a permutation too large for AVX2. Performing the lookup as a permutation isn't possible because several base 64 characters are larger than 64. However, the encoding character can be computed by adding an offset to the index, and there are only five distinct ranges. For each character within a contiguous range, the offset is the same, so there are only five possible offsets, so if a 3-bit value corresponding to an offset can be computed quickly from each 6-bit index, an offset vector can be looked up and simply added to the index vector. Then it's just a question of finding and tuning a reduction to offset key.

This should be obvious from this table. 

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed compact">
<thead><tr><th title="Field #1">Position</th>
<th title="Field #2">Character</th>
<th title="Field #3">Decimal</th>
<th title="Field #4">Offset</th>
<th title="Field #5">Reduced Nibble</th>
</tr></thead>
<tbody><tr>
<td align="right">0</td>
<td>A</td>
<td align="right">65</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">1</td>
<td>B</td>
<td align="right">66</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">2</td>
<td>C</td>
<td align="right">67</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">3</td>
<td>D</td>
<td align="right">68</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">4</td>
<td>E</td>
<td align="right">69</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">5</td>
<td>F</td>
<td align="right">70</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">6</td>
<td>G</td>
<td align="right">71</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">7</td>
<td>H</td>
<td align="right">72</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">8</td>
<td>I</td>
<td align="right">73</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">9</td>
<td>J</td>
<td align="right">74</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">10</td>
<td>K</td>
<td align="right">75</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">11</td>
<td>L</td>
<td align="right">76</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">12</td>
<td>M</td>
<td align="right">77</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">13</td>
<td>N</td>
<td align="right">78</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">14</td>
<td>O</td>
<td align="right">79</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">15</td>
<td>P</td>
<td align="right">80</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">16</td>
<td>Q</td>
<td align="right">81</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">17</td>
<td>R</td>
<td align="right">82</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">18</td>
<td>S</td>
<td align="right">83</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">19</td>
<td>T</td>
<td align="right">84</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">20</td>
<td>U</td>
<td align="right">85</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">21</td>
<td>V</td>
<td align="right">86</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">22</td>
<td>W</td>
<td align="right">87</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">23</td>
<td>X</td>
<td align="right">88</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">24</td>
<td>Y</td>
<td align="right">89</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">25</td>
<td>Z</td>
<td align="right">90</td>
<td align="right">65</td>
<td align="right">13</td>
</tr>
<tr>
<td align="right">26</td>
<td>a</td>
<td align="right">97</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">27</td>
<td>b</td>
<td align="right">98</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">28</td>
<td>c</td>
<td align="right">99</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">29</td>
<td>d</td>
<td align="right">100</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">30</td>
<td>e</td>
<td align="right">101</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">31</td>
<td>f</td>
<td align="right">102</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">32</td>
<td>g</td>
<td align="right">103</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">33</td>
<td>h</td>
<td align="right">104</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">34</td>
<td>i</td>
<td align="right">105</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">35</td>
<td>j</td>
<td align="right">106</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">36</td>
<td>k</td>
<td align="right">107</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">37</td>
<td>l</td>
<td align="right">108</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">38</td>
<td>m</td>
<td align="right">109</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">39</td>
<td>n</td>
<td align="right">110</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">40</td>
<td>o</td>
<td align="right">111</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">41</td>
<td>p</td>
<td align="right">112</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">42</td>
<td>q</td>
<td align="right">113</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">43</td>
<td>r</td>
<td align="right">114</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">44</td>
<td>s</td>
<td align="right">115</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">45</td>
<td>t</td>
<td align="right">116</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">46</td>
<td>u</td>
<td align="right">117</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">47</td>
<td>v</td>
<td align="right">118</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">48</td>
<td>w</td>
<td align="right">119</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">49</td>
<td>x</td>
<td align="right">120</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">50</td>
<td>y</td>
<td align="right">121</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">51</td>
<td>z</td>
<td align="right">122</td>
<td align="right">71</td>
<td align="right">0</td>
</tr>
<tr>
<td align="right">52</td>
<td>0</td>
<td align="right">48</td>
<td align="right">-4</td>
<td align="right">1</td>
</tr>
<tr>
<td align="right">53</td>
<td>1</td>
<td align="right">49</td>
<td align="right">-4</td>
<td align="right">2</td>
</tr>
<tr>
<td align="right">54</td>
<td>2</td>
<td align="right">50</td>
<td align="right">-4</td>
<td align="right">3</td>
</tr>
<tr>
<td align="right">55</td>
<td>3</td>
<td align="right">51</td>
<td align="right">-4</td>
<td align="right">4</td>
</tr>
<tr>
<td align="right">56</td>
<td>4</td>
<td align="right">52</td>
<td align="right">-4</td>
<td align="right">5</td>
</tr>
<tr>
<td align="right">57</td>
<td>5</td>
<td align="right">53</td>
<td align="right">-4</td>
<td align="right">6</td>
</tr>
<tr>
<td align="right">58</td>
<td>6</td>
<td align="right">54</td>
<td align="right">-4</td>
<td align="right">7</td>
</tr>
<tr>
<td align="right">59</td>
<td>7</td>
<td align="right">55</td>
<td align="right">-4</td>
<td align="right">8</td>
</tr>
<tr>
<td align="right">60</td>
<td>8</td>
<td align="right">56</td>
<td align="right">-4</td>
<td align="right">9</td>
</tr>
<tr>
<td align="right">61</td>
<td>9</td>
<td align="right">57</td>
<td align="right">-4</td>
<td align="right">10</td>
</tr>
<tr>
<td align="right">62</td>
<td>+</td>
<td align="right">43</td>
<td align="right">-19</td>
<td align="right">11</td>
</tr>
<tr>
<td align="right">63</td>
<td>/</td>
<td align="right">47</td>
<td align="right">-16</td>
<td align="right">12</td>
</tr>
</tbody></table>
</div>

The offset column is the value of the character minus the index, and the reduced nibble is a number computed by an efficient, if inelegant, sequence of vector operations that can be read about in the paper. Given that there are only five valid offsets, they could be specified by a three-bit value, and overspecified by a nibble, but a bit of redundancy allows a faster computation. The mapping is specified as follows: upper case letters to the number 13, lower case letters to zero, each number `i` to `i + 1`, and '+' and '/' to 11 and 12 respectively. These nibbles are then used as the input to a permutation using `vpshufb` to produce the appropriate offset to add to the index.

<pre>             
plus ------------------------------------------------------\         /------------------ forward slash
digits  -----------\***********************************\    \       /   /--------------- upper case
lower case -----\   \***********************************\    \     /   /   /***/-------- undefined 
Reduced Nibble [ 0,  1,  2,  3,  4,  5,  6,  7,  8,  9, 10,  11,  12, 13, 14, 15]
Offset         [71, -4, -4, -4, -4, -4, -4, -4, -4, -4, -4, -19, -16, 65,  0,  0]
</pre>

A call to `vpshufb` with a vector of reduced nibbles and the permutation above as input produces an offset vector which is added to the indexes to encode a vector of 6-bit values.

Would it be possible to implement a permutation like this in the Vector API? I expect this will be too complex to be expressed precisely because it works around and therefore embraces <a href="https://software.intel.com/sites/landingpage/IntrinsicsGuide/#text=_mm256_shuffle_epi8&expand=4754" rel="noopener" target="_blank">vpshufb</a> performing two independent 128-bit permutations, rather than a single 256-bit permutation. This could be achieved with two SSE 128-bit loads and permutes, but loading 256-bit vectors from pairs of 128-bit vectors is convoluted as things stand.

For the extraction step, I doubt the semantics of `_mm256_mulhi_epi16` or `_mm256_mullo_epi16` will ever be exposed to Java programmers, but it is possible to take the slow path and perform independent shifts. It just so happens that the calculation of the offset key relies on unsigned 8-bit arithmetic which does not exist in Java, but there are simpler but slower techniques to calculate the offset key. AVX2 is weird, with an abundance of unexpected capabilities alongside screaming feature gaps, and all the AVX2 code I read is teeming with ingenious hacks. I can imagine language designers being reticent to enshrine these peculiarities in a higher level language.

The real question is why bother? The fact that we use text so often moves the goalposts from copying memory to all of the complexity above. The fastest base 64 encoding is the one you don't do.

<blockquote>I highly recommend reading <a href="http://0x80.pl/notesen/" rel="noopener" target="_blank">Wojciech Mula's blog</a> if you are interested in what's possible with vectorisation.</blockquote>

<blockquote>John Rose wrote an interesting response to the paragraphs about the Vector API in this post <a href="http://mail.openjdk.java.net/pipermail/panama-dev/2018-August/002485.html" rel="noopener" target="_blank">here</a>.</blockquote>