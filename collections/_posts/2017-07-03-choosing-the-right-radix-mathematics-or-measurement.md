---
ID: 5730
post_title: 'Choosing the Right Radix: Measurement or Mathematics?'
author: Richard Startin
post_excerpt: ""
layout: post
permalink: >
  http://richardstartin.uk/choosing-the-right-radix-mathematics-or-measurement/
published: true
post_date: 2017-07-03 19:40:43
---
I recently wrote a <a href="http://richardstartin.uk/sorting-unsigned-integers-faster-in-java/" target="_blank" rel="noopener noreferrer">post</a> about radix sorting, and found that for large arrays of unsigned integers a handwritten implementation beats <code>Arrays.sort</code>. However, I paid no attention to the choice of radix and used a default of eight bits. It turns out this was a lucky choice: modifying my benchmark to parametrise the radix, I observed a maximum at one byte, regardless of the size of array.

Is this an algorithmic or technical phenomenon? Is this something that could have been predicted on the back of an envelope without running a benchmark? 

<h3>Extended Benchmark Results</h3>

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed" style="max-height:300px;">
    <thead>
    
        <th>Size</th>
        <th>Radix</th>
        <th>Score</th>
        <th>Score Error (99.9%)</th>
        <th>Unit</th>
    
    </thead>
    <tbody>
    <tr>
        <td>100</td>
        <td>2</td>
        <td>135.559923</td>
        <td>7.72397</td>
        <td>ops/ms</td>
    </tr>
    <tr>
        <td>100</td>
        <td>4</td>
        <td>262.854579</td>
        <td>37.372678</td>
        <td>ops/ms</td>
    </tr>
    <tr>
        <td>100</td>
        <td>8</td>
        <td>345.038234</td>
        <td>30.954927</td>
        <td>ops/ms</td>
    </tr>
    <tr>
        <td>100</td>
        <td>16</td>
        <td>7.717496</td>
        <td>1.144967</td>
        <td>ops/ms</td>
    </tr>
    <tr>
        <td>1000</td>
        <td>2</td>
        <td>13.892142</td>
        <td>1.522749</td>
        <td>ops/ms</td>
    </tr>
    <tr>
        <td>1000</td>
        <td>4</td>
        <td>27.712719</td>
        <td>4.057162</td>
        <td>ops/ms</td>
    </tr>
    <tr>
        <td>1000</td>
        <td>8</td>
        <td>52.253497</td>
        <td>4.761172</td>
        <td>ops/ms</td>
    </tr>
    <tr>
        <td>1000</td>
        <td>16</td>
        <td>7.656033</td>
        <td>0.499627</td>
        <td>ops/ms</td>
    </tr>
    <tr>
        <td>10000</td>
        <td>2</td>
        <td>1.627354</td>
        <td>0.186948</td>
        <td>ops/ms</td>
    </tr>
    <tr>
        <td>10000</td>
        <td>4</td>
        <td>3.620869</td>
        <td>0.029128</td>
        <td>ops/ms</td>
    </tr>
    <tr>
        <td>10000</td>
        <td>8</td>
        <td>6.435789</td>
        <td>0.610848</td>
        <td>ops/ms</td>
    </tr>
    <tr>
        <td>10000</td>
        <td>16</td>
        <td>3.703248</td>
        <td>0.45177</td>
        <td>ops/ms</td>
    </tr>
    <tr>
        <td>100000</td>
        <td>2</td>
        <td>0.144575</td>
        <td>0.014348</td>
        <td>ops/ms</td>
    </tr>
    <tr>
        <td>100000</td>
        <td>4</td>
        <td>0.281837</td>
        <td>0.025707</td>
        <td>ops/ms</td>
    </tr>
    <tr>
        <td>100000</td>
        <td>8</td>
        <td>0.543274</td>
        <td>0.031553</td>
        <td>ops/ms</td>
    </tr>
    <tr>
        <td>100000</td>
        <td>16</td>
        <td>0.533998</td>
        <td>0.126949</td>
        <td>ops/ms</td>
    </tr>
    <tr>
        <td>1000000</td>
        <td>2</td>
        <td>0.011293</td>
        <td>0.001429</td>
        <td>ops/ms</td>
    </tr>
    <tr>
        <td>1000000</td>
        <td>4</td>
        <td>0.021128</td>
        <td>0.003137</td>
        <td>ops/ms</td>
    </tr>
    <tr>
        <td>1000000</td>
        <td>8</td>
        <td>0.037376</td>
        <td>0.005783</td>
        <td>ops/ms</td>
    </tr>
    <tr>
        <td>1000000</td>
        <td>16</td>
        <td>0.031053</td>
        <td>0.007987</td>
        <td>ops/ms</td>
    </tr>
    </tbody>
</table>
</div>

<h3>Modeling</h3>

To model the execution time of the algorithm, we can write $latex t = f(r, n)$, where $latex n \in \mathbb{N}$ is the length of the input array, and $latex r \in [1, 32)$ is the size in bits of the radix. We can inspect if the model predicts non-monotonic execution time with a minimum (corresponding to maximal throughput), or if $latex t$ increases indefinitely as a function of $latex r$. If we find a plausible model predicting a minimum, temporarily treating $latex r$ as continuous, we can solve $latex \frac{\partial f}{\partial r}|_{n=N, r \in [1,32)} = 0$ to find the theoretically optimal radix. This pre-supposes we derive a non-monotonic model.

<h3>Constructing a Model</h4>

We need to write down an equation before we can do any calculus, which requires two dangerous assumptions.

<ol>
	<li>Each operation has the same cost, making the execution time proportional to the number of operation.</li>
	<li>The costs of operations do not vary as a function of $latex n$ or $latex r$.
</ol>

This means all we need to do is find a formula for the number of operations, and then vary $latex n$ and $latex r$. The usual pitfall in this approach relates to the first assumption, in that memory accesses are modelled as uniform cost; memory access can vary widely in cost ranging from registers to RAM on another socket. We are about to fall foul of both assumptions constructing an intuitive model of the algorithm's loop.

<code class="language-java">
        while (shift < Integer.SIZE) {
            Arrays.fill(histogram, 0);
            for (int i = 0; i < data.length; ++i) {
                ++histogram[((data[i] & mask) >> shift) + 1];
            }
            for (int i = 0; i < 1 << radix; ++i) {
                histogram[i + 1] += histogram[i];
            }
            for (int i = 0; i < data.length; ++i) {
                copy[histogram[(data[i] & mask) >> shift]++] = data[i];
            }
            for (int i = 0; i < data.length; ++i) {
                data[i] = copy[i];
            }
            shift += radix;
            mask <<= radix;
        }
</code>

The outer loop depends on the choice of radix while the inner loops depend on the size of the array and the choice of radix. There are five obvious aspects to capture:

<ul>
	<li>The first inner loop takes time proportional to $latex n$</li>
	<li>The third and fourth inner loops take time proportional to $latex n$</li>
	<li>We can factor the per-element costs of loops 1, 3 and 4 into a constant $latex a$</li>
        <li>The second inner loop takes time proportional to $latex 2^r$, modeled with by the term $latex b2^r$</li>	
        <li>The body of the loop executes $latex 32/r$ times</li>
</ul>

This can be summarised as the formula: 

$latex f(r, n) = 32\frac{(3an + b2^r)}{r}$

It was claimed the algorithm had linear complexity in $latex n$ and it only has a linear term in $latex n$. Good. However, the exponential $latex r$ term in the numerator dominates the linear term in the denominator, making the function monotonic in $latex r$. The model fails to predict the observed throughput maximising radix. <em>There are clearly much more complicated mechanisms at play than can be captured counting operations.</em>