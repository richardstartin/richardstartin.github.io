---
ID: 8287
post_title: 'How much Algebra does C2 Know? Part 2: Distributivity'
author: Richard Startin
post_excerpt: ""
layout: post
permalink: >
  http://richardstartin.uk/how-much-algebra-does-c2-know-part-2-distributivity/
published: true
post_date: 2017-08-18 19:43:10
---
In <a href="http://richardstartin.uk/how-much-algebra-does-c2-know-part-1-associativity/" target="_blank">part one</a> of this series of posts, I looked at how important associativity and independence are for fast loops. C2 seems to utilise these properties to generate unrolled and pipelined machine code for loops, achieving higher throughput even in cases where the kernel of the loop is 3x slower according to vendor advertised instruction throughputs. C2 has a weird and wonderful relationship with distributivity, and hints from the programmer can both and help hinder the generation of good quality machine code. 

<h3>Viability and Correctness</h3>

<a href="https://en.wikipedia.org/wiki/Distributive_property" target="_blank">Distributivity</a> is the simple notion of factoring out brackets. Is this, in general, a viable loop rewrite strategy? This can be utilised to transform the method <code>Scale</code> into <code>FactoredScale</code>, both of which perform floating point arithmetic:

<code class="language-java">
    @CompilerControl(CompilerControl.Mode.DONT_INLINE)
    @Benchmark
    public double Scale(DoubleData state) {
        double value = 0D;
        double[] data = state.data1;
        for (int i = 0; i < data.length; ++i) {
            value += 3.14159 * data[i];
        }
        return value;
    }

    @CompilerControl(CompilerControl.Mode.DONT_INLINE)
    @Benchmark
    public double FactoredScale(DoubleData state) {
        double value = 0D;
        double[] data = state.data1;
        for (int i = 0; i < data.length; ++i) {
            value += data[i];
        }
        return 3.14159 * value;
    }
</code>

Running the project at <a href="https://github.com/richardstartin/simdbenchmarks" target="_blank">github</a> with the argument <code>--include .*scale.*</code>, there may be a performance gain to be had from this rewrite, but it isn't clear cut:

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead>
<th>Benchmark</th>
<th>Mode</th>
<th>Threads</th>
<th>Samples</th>
<th>Score</th>
<th>Score Error (99.9%)</th>
<th>Unit</th>
<th>Param: size</th>
</thead>
<tbody><tr>
<td>FactoredScale</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">7.011606</td>
<td align="right">0.274742</td>
<td>ops/ms</td>
<td align="right">100000</td>
</tr>
<tr>
<td>FactoredScale</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.621515</td>
<td align="right">0.026853</td>
<td>ops/ms</td>
<td align="right">1000000</td>
</tr>
<tr>
<td>Scale</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">6.962434</td>
<td align="right">0.240180</td>
<td>ops/ms</td>
<td align="right">100000</td>
</tr>
<tr>
<td>Scale</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">0.671042</td>
<td align="right">0.011686</td>
<td>ops/ms</td>
<td align="right">1000000</td>
</tr>
</tbody></table>
</div>

With the real numbers it would be completely valid, but floating point arithmetic is not associative. Joseph Darcy explains why in this <a href="https://www.youtube.com/embed/qTKeU_3rhk4" rel="noopener" target="_blank">deep dive</a> on floating point semantics. Broken associativity of addition entails broken distributivity of any operation over it, so the two loops are not equivalent, and they give different outputs (e.g. 15662.513298516365 vs 15662.51329851632 for one sample input). The rewrite isn't correct even for floating point data, so it isn't an optimisation that could be applied in good faith, except in a very small number of cases. You have to rewrite the loop yourself and figure out if the small but inevitable differences are acceptable.

<h3>Counterintuitive Performance</h3>

Integer multiplication <em>is</em> distributive over addition, and we can check if C2 does this rewrite by running the same code with 32 bit integer values, for now fixing a scale factor of 10 (which seems like an innocuous value, no?) 

<code class="language-java">
    @CompilerControl(CompilerControl.Mode.DONT_INLINE)
    @Benchmark
    public int Scale_Int(IntData state) {
        int value = 0;
        int[] data = state.data1;
        for (int i = 0; i < data.length; ++i) {
            value += 10 * data[i];
        }
        return value;
    }

    @CompilerControl(CompilerControl.Mode.DONT_INLINE)
    @Benchmark
    public int FactoredScale_Int(IntData state) {
        int value = 0;
        int[] data = state.data1;
        for (int i = 0; i < data.length; ++i) {
            value += data[i];
        }
        return 10 * value;
    }
</code>

The results are fascinating:

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead>
<th>Benchmark</th>
<th>Mode</th>
<th>Threads</th>
<th>Samples</th>
<th>Score</th>
<th>Score Error (99.9%)</th>
<th>Unit</th>
<th>Param: size</th>
</thead>
<tbody><tr>
<td>FactoredScale_Int</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">28.339699</td>
<td align="right">0.608075</td>
<td>ops/ms</td>
<td align="right">100000</td>
</tr>
<tr>
<td>FactoredScale_Int</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">2.392579</td>
<td align="right">0.506413</td>
<td>ops/ms</td>
<td align="right">1000000</td>
</tr>
<tr>
<td>Scale_Int</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">33.335721</td>
<td align="right">0.295334</td>
<td>ops/ms</td>
<td align="right">100000</td>
</tr>
<tr>
<td>Scale_Int</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">2.838242</td>
<td align="right">0.448213</td>
<td>ops/ms</td>
<td align="right">1000000</td>
</tr>
</tbody>
</table>
</div>

The code is doing thousands more multiplications in less time when the multiplication is <em>not</em> factored out of the loop. So what the devil is going on? Inspecting the assembly for the faster loop is revealing

<div class="snippet-assembly">
<pre>
  0x000001c89e499400: vmovdqu ymm8,ymmword ptr [rbp+r13*4+10h]
  0x000001c89e499407: movsxd  r10,r13d       
  0x000001c89e49940a: vmovdqu ymm9,ymmword ptr [rbp+r10*4+30h]
  0x000001c89e499411: vmovdqu ymm13,ymmword ptr [rbp+r10*4+0f0h]
  0x000001c89e49941b: vmovdqu ymm12,ymmword ptr [rbp+r10*4+50h]
  0x000001c89e499422: vmovdqu ymm4,ymmword ptr [rbp+r10*4+70h]
  0x000001c89e499429: vmovdqu ymm3,ymmword ptr [rbp+r10*4+90h]
  0x000001c89e499433: vmovdqu ymm2,ymmword ptr [rbp+r10*4+0b0h]
  0x000001c89e49943d: vmovdqu ymm0,ymmword ptr [rbp+r10*4+0d0h]
  0x000001c89e499447: vpslld  ymm11,ymm8,1h  
  0x000001c89e49944d: vpslld  ymm1,ymm0,1h   
  0x000001c89e499452: vpslld  ymm0,ymm0,3h   
  0x000001c89e499457: vpaddd  ymm5,ymm0,ymm1 
  0x000001c89e49945b: vpslld  ymm0,ymm2,3h   
  0x000001c89e499460: vpslld  ymm7,ymm3,3h   
  0x000001c89e499465: vpslld  ymm10,ymm4,3h 
  0x000001c89e49946a: vpslld  ymm15,ymm12,3h
  0x000001c89e499470: vpslld  ymm14,ymm13,3h
  0x000001c89e499476: vpslld  ymm1,ymm9,3h  
  0x000001c89e49947c: vpslld  ymm2,ymm2,1h  
  0x000001c89e499481: vpaddd  ymm6,ymm0,ymm2   
  0x000001c89e499485: vpslld  ymm0,ymm3,1h     
  0x000001c89e49948a: vpaddd  ymm7,ymm7,ymm0   
  0x000001c89e49948e: vpslld  ymm0,ymm4,1h     
  0x000001c89e499493: vpaddd  ymm10,ymm10,ymm0
  0x000001c89e499497: vpslld  ymm0,ymm12,1h   
  0x000001c89e49949d: vpaddd  ymm12,ymm15,ymm0
  0x000001c89e4994a1: vpslld  ymm0,ymm13,1h   
  0x000001c89e4994a7: vpaddd  ymm4,ymm14,ymm0 
  0x000001c89e4994ab: vpslld  ymm0,ymm9,1h    
  0x000001c89e4994b1: vpaddd  ymm2,ymm1,ymm0  
  0x000001c89e4994b5: vpslld  ymm0,ymm8,3h    
  0x000001c89e4994bb: vpaddd  ymm8,ymm0,ymm11 
  0x000001c89e4994c0: vphaddd ymm0,ymm8,ymm8  
  0x000001c89e4994c5: vphaddd ymm0,ymm0,ymm3  
  0x000001c89e4994ca: vextracti128 xmm3,ymm0,1h
  0x000001c89e4994d0: vpaddd  xmm0,xmm0,xmm3   
  0x000001c89e4994d4: vmovd   xmm3,ebx         
  0x000001c89e4994d8: vpaddd  xmm3,xmm3,xmm0   
  0x000001c89e4994dc: vmovd   r10d,xmm3        
  0x000001c89e4994e1: vphaddd ymm0,ymm2,ymm2   
  0x000001c89e4994e6: vphaddd ymm0,ymm0,ymm3   
  0x000001c89e4994eb: vextracti128 xmm3,ymm0,1h
  0x000001c89e4994f1: vpaddd  xmm0,xmm0,xmm3   
  0x000001c89e4994f5: vmovd   xmm3,r10d        
  0x000001c89e4994fa: vpaddd  xmm3,xmm3,xmm0   
  0x000001c89e4994fe: vmovd   r11d,xmm3        
  0x000001c89e499503: vphaddd ymm2,ymm12,ymm12  
  0x000001c89e499508: vphaddd ymm2,ymm2,ymm0    
  0x000001c89e49950d: vextracti128 xmm0,ymm2,1h 
  0x000001c89e499513: vpaddd  xmm2,xmm2,xmm0    
  0x000001c89e499517: vmovd   xmm0,r11d         
  0x000001c89e49951c: vpaddd  xmm0,xmm0,xmm2    
  0x000001c89e499520: vmovd   r10d,xmm0         
  0x000001c89e499525: vphaddd ymm0,ymm10,ymm10  
  0x000001c89e49952a: vphaddd ymm0,ymm0,ymm3   
  0x000001c89e49952f: vextracti128 xmm3,ymm0,1h
  0x000001c89e499535: vpaddd  xmm0,xmm0,xmm3
  0x000001c89e499539: vmovd   xmm3,r10d   
  0x000001c89e49953e: vpaddd  xmm3,xmm3,xmm0   
  0x000001c89e499542: vmovd   r11d,xmm3        
  0x000001c89e499547: vphaddd ymm2,ymm7,ymm7   
  0x000001c89e49954c: vphaddd ymm2,ymm2,ymm0   
  0x000001c89e499551: vextracti128 xmm0,ymm2,1h
  0x000001c89e499557: vpaddd  xmm2,xmm2,xmm0 
  0x000001c89e49955b: vmovd   xmm0,r11d      
  0x000001c89e499560: vpaddd  xmm0,xmm0,xmm2 
  0x000001c89e499564: vmovd   r10d,xmm0      
  0x000001c89e499569: vphaddd ymm0,ymm6,ymm6   
  0x000001c89e49956e: vphaddd ymm0,ymm0,ymm3   
  0x000001c89e499573: vextracti128 xmm3,ymm0,1h
  0x000001c89e499579: vpaddd  xmm0,xmm0,xmm3   
  0x000001c89e49957d: vmovd   xmm3,r10d        
  0x000001c89e499582: vpaddd  xmm3,xmm3,xmm0   
  0x000001c89e499586: vmovd   r11d,xmm3        
  0x000001c89e49958b: vphaddd ymm2,ymm5,ymm5   
  0x000001c89e499590: vphaddd ymm2,ymm2,ymm0   
  0x000001c89e499595: vextracti128 xmm0,ymm2,1h
  0x000001c89e49959b: vpaddd  xmm2,xmm2,xmm0
  0x000001c89e49959f: vmovd   xmm0,r11d     
  0x000001c89e4995a4: vpaddd  xmm0,xmm0,xmm2
  0x000001c89e4995a8: vmovd   r10d,xmm0
  0x000001c89e4995ad: vphaddd ymm2,ymm4,ymm4 
  0x000001c89e4995b2: vphaddd ymm2,ymm2,ymm1
  0x000001c89e4995b7: vextracti128 xmm1,ymm2,1h
  0x000001c89e4995bd: vpaddd  xmm2,xmm2,xmm1
  0x000001c89e4995c1: vmovd   xmm1,r10d  
  0x000001c89e4995c6: vpaddd  xmm1,xmm1,xmm2    
  0x000001c89e4995ca: vmovd   ebx,xmm1          
</pre>
</div>

The loop is aggressively unrolled, pipelined, and vectorised. Moreover, the multiplication by ten results not in a multiplication but two left shifts (see <code>VPSLLD</code>) and an addition. Note that <code>x << 1 + x << 3 = x * 10</code> and C2 seems to know it; this rewrite can be applied because it can be proven statically that the factor is always 10. The "optimised" loop doesn't vectorise at all (and I have no idea why not - isn't this a bug? <a href="https://bugs.openjdk.java.net/browse/JDK-8188313" rel="noopener" target="_blank">Yes it is.</a>)

<div class="snippet-assembly">
<pre>
  0x000002bbebeda3c8: add     ebx,dword ptr [rbp+r8*4+14h]
  0x000002bbebeda3cd: add     ebx,dword ptr [rbp+r8*4+18h]
  0x000002bbebeda3d2: add     ebx,dword ptr [rbp+r8*4+1ch]
  0x000002bbebeda3d7: add     ebx,dword ptr [rbp+r8*4+20h]
  0x000002bbebeda3dc: add     ebx,dword ptr [rbp+r8*4+24h]
  0x000002bbebeda3e1: add     ebx,dword ptr [rbp+r8*4+28h]
  0x000002bbebeda3e6: add     ebx,dword ptr [rbp+r8*4+2ch]
  0x000002bbebeda3eb: add     r13d,8h           
  0x000002bbebeda3ef: cmp     r13d,r11d         
  0x000002bbebeda3f2: jl      2bbebeda3c0h      
  </pre>
</div>

This is a special case: data is usually dynamic and variable, so the loop cannot always be proven to be equivalent to a linear combination of bit shifts. The routine is compiled for all possible parameters, not just statically contrived cases like the one above, so you may never see this assembly in the wild. However, even with random factors, the slow looking loop is aggressively optimised in a way the hand "optimised" code is not:

<code class="language-java">
    @CompilerControl(CompilerControl.Mode.DONT_INLINE)
    @Benchmark
    public int Scale_Int_Dynamic(ScaleState state) {
        int value = 0;
        int[] data = state.data;
        int factor = state.randomFactor();
        for (int i = 0; i < data.length; ++i) {
            value += factor * data[i];
        }
        return value;
    }

    @CompilerControl(CompilerControl.Mode.DONT_INLINE)
    @Benchmark
    public int FactoredScale_Int_Dynamic(ScaleState state) {
        int value = 0;
        int[] data = state.data;
        int factor = state.randomFactor();
        for (int i = 0; i < data.length; ++i) {
            value += data[i];
        }
        return factor * value;
    }
</code>

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead>
<th>Benchmark</th>
<th>Mode</th>
<th>Threads</th>
<th>Samples</th>
<th>Score</th>
<th>Score Error (99.9%)</th>
<th>Unit</th>
<th>Param: size</th>
</thead>
<tbody><tr>
<td>FactoredScale_Int_Dynamic</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">26.100439</td>
<td align="right">0.340069</td>
<td>ops/ms</td>
<td align="right">100000</td>
</tr>
<tr>
<td>FactoredScale_Int_Dynamic</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">1.918011</td>
<td align="right">0.297925</td>
<td>ops/ms</td>
<td align="right">1000000</td>
</tr>
<tr>
<td>Scale_Int_Dynamic</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">30.219809</td>
<td align="right">2.977389</td>
<td>ops/ms</td>
<td align="right">100000</td>
</tr>
<tr>
<td>Scale_Int_Dynamic</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">2.314159</td>
<td align="right">0.378442</td>
<td>ops/ms</td>
<td align="right">1000000</td>
</tr>
</tbody>
</table>
</div>

Far from seeking to exploit distributivity to reduce the number of multiplication instructions, it seems to almost <em>embrace</em> the extraneous operations as metadata to drive optimisations. The assembly for <code>Scale_Int_Dynamic</code> confirms this (it shows vectorised multiplication, not shifts, <em>within</em> the loop):

<div class="snippet-assembly">
<pre>

  0x000001f5ca2fa200: vmovdqu ymm0,ymmword ptr [r13+r14*4+10h]
  0x000001f5ca2fa207: vpmulld ymm11,ymm0,ymm2   
  0x000001f5ca2fa20c: movsxd  r10,r14d          
  0x000001f5ca2fa20f: vmovdqu ymm0,ymmword ptr [r13+r10*4+30h]
  0x000001f5ca2fa216: vmovdqu ymm1,ymmword ptr [r13+r10*4+0f0h]
  0x000001f5ca2fa220: vmovdqu ymm3,ymmword ptr [r13+r10*4+50h]
  0x000001f5ca2fa227: vmovdqu ymm7,ymmword ptr [r13+r10*4+70h]
  0x000001f5ca2fa22e: vmovdqu ymm6,ymmword ptr [r13+r10*4+90h]
  0x000001f5ca2fa238: vmovdqu ymm5,ymmword ptr [r13+r10*4+0b0h]
  0x000001f5ca2fa242: vmovdqu ymm4,ymmword ptr [r13+r10*4+0d0h]
  0x000001f5ca2fa24c: vpmulld ymm9,ymm0,ymm2    
  0x000001f5ca2fa251: vpmulld ymm4,ymm4,ymm2    
  0x000001f5ca2fa256: vpmulld ymm5,ymm5,ymm2    
  0x000001f5ca2fa25b: vpmulld ymm6,ymm6,ymm2    
  0x000001f5ca2fa260: vpmulld ymm8,ymm7,ymm2    
  0x000001f5ca2fa265: vpmulld ymm10,ymm3,ymm2   
  0x000001f5ca2fa26a: vpmulld ymm3,ymm1,ymm2    
  0x000001f5ca2fa26f: vphaddd ymm1,ymm11,ymm11  
  0x000001f5ca2fa274: vphaddd ymm1,ymm1,ymm0    
  0x000001f5ca2fa279: vextracti128 xmm0,ymm1,1h 
  0x000001f5ca2fa27f: vpaddd  xmm1,xmm1,xmm0    
  0x000001f5ca2fa283: vmovd   xmm0,ebx          
  0x000001f5ca2fa287: vpaddd  xmm0,xmm0,xmm1    
  0x000001f5ca2fa28b: vmovd   r10d,xmm0         
  0x000001f5ca2fa290: vphaddd ymm1,ymm9,ymm9    
  0x000001f5ca2fa295: vphaddd ymm1,ymm1,ymm0    
  0x000001f5ca2fa29a: vextracti128 xmm0,ymm1,1h 
  0x000001f5ca2fa2a0: vpaddd  xmm1,xmm1,xmm0    
  0x000001f5ca2fa2a4: vmovd   xmm0,r10d         
  0x000001f5ca2fa2a9: vpaddd  xmm0,xmm0,xmm1    
  0x000001f5ca2fa2ad: vmovd   r11d,xmm0         
  0x000001f5ca2fa2b2: vphaddd ymm0,ymm10,ymm10  
  0x000001f5ca2fa2b7: vphaddd ymm0,ymm0,ymm1    
  0x000001f5ca2fa2bc: vextracti128 xmm1,ymm0,1h 
  0x000001f5ca2fa2c2: vpaddd  xmm0,xmm0,xmm1    
  0x000001f5ca2fa2c6: vmovd   xmm1,r11d         
  0x000001f5ca2fa2cb: vpaddd  xmm1,xmm1,xmm0    
  0x000001f5ca2fa2cf: vmovd   r10d,xmm1         
  0x000001f5ca2fa2d4: vphaddd ymm1,ymm8,ymm8    
  0x000001f5ca2fa2d9: vphaddd ymm1,ymm1,ymm0    
  0x000001f5ca2fa2de: vextracti128 xmm0,ymm1,1h 
  0x000001f5ca2fa2e4: vpaddd  xmm1,xmm1,xmm0    
  0x000001f5ca2fa2e8: vmovd   xmm0,r10d         
  0x000001f5ca2fa2ed: vpaddd  xmm0,xmm0,xmm1    
  0x000001f5ca2fa2f1: vmovd   r11d,xmm0         
  0x000001f5ca2fa2f6: vphaddd ymm0,ymm6,ymm6    
  0x000001f5ca2fa2fb: vphaddd ymm0,ymm0,ymm1    
  0x000001f5ca2fa300: vextracti128 xmm1,ymm0,1h 
  0x000001f5ca2fa306: vpaddd  xmm0,xmm0,xmm1    
  0x000001f5ca2fa30a: vmovd   xmm1,r11d         
  0x000001f5ca2fa30f: vpaddd  xmm1,xmm1,xmm0    
  0x000001f5ca2fa313: vmovd   r10d,xmm1         
  0x000001f5ca2fa318: vphaddd ymm1,ymm5,ymm5    
  0x000001f5ca2fa31d: vphaddd ymm1,ymm1,ymm0    
  0x000001f5ca2fa322: vextracti128 xmm0,ymm1,1h 
  0x000001f5ca2fa328: vpaddd  xmm1,xmm1,xmm0    
  0x000001f5ca2fa32c: vmovd   xmm0,r10d         
  0x000001f5ca2fa331: vpaddd  xmm0,xmm0,xmm1    
  0x000001f5ca2fa335: vmovd   r11d,xmm0         
  0x000001f5ca2fa33a: vphaddd ymm0,ymm4,ymm4    
  0x000001f5ca2fa33f: vphaddd ymm0,ymm0,ymm1    
  0x000001f5ca2fa344: vextracti128 xmm1,ymm0,1h 
  0x000001f5ca2fa34a: vpaddd  xmm0,xmm0,xmm1    
  0x000001f5ca2fa34e: vmovd   xmm1,r11d         
  0x000001f5ca2fa353: vpaddd  xmm1,xmm1,xmm0    
  0x000001f5ca2fa357: vmovd   r10d,xmm1         
  0x000001f5ca2fa35c: vphaddd ymm1,ymm3,ymm3    
  0x000001f5ca2fa361: vphaddd ymm1,ymm1,ymm7    
  0x000001f5ca2fa366: vextracti128 xmm7,ymm1,1h 
  0x000001f5ca2fa36c: vpaddd  xmm1,xmm1,xmm7   
  0x000001f5ca2fa370: vmovd   xmm7,r10d        
  0x000001f5ca2fa375: vpaddd  xmm7,xmm7,xmm1   
  0x000001f5ca2fa379: vmovd   ebx,xmm7         
</pre>
</div>

There are two lessons to be learnt here. The first is that what you see is not what you get. The second is about the correctness of asymptotic analysis. If hierarchical cache renders asymptotic analysis bullshit (linear time but cache friendly algorithms can, and do, outperform logarithmic algorithms with cache misses), optimising compilers render the field practically irrelevant.