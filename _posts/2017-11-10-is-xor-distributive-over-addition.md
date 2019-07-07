---
ID: 9957
post_title: Is XOR Distributive over Addition?
author: Richard Startin
post_excerpt: ""
layout: post
permalink: >
  http://richardstartin.uk/is-xor-distributive-over-addition/
published: true
post_date: 2017-11-10 18:50:11
---
Google search console has become a thing of mild interest to me since I moved my website and Google forgot about my content. Impressions - search terms that match your site but don't lead to a click - are full of fascinating false positives. I looked at some of my impressions. These search terms are:

<img src="http://richardstartin.uk/wp-content/uploads/2017/11/searchterms-197x300.png" alt="is xor associative over addition?" width="197" height="300" class="alignnone size-medium wp-image-9958" />

The highlighted term "is xor distributive over addition" jumped out at me.  

Since multiplication obviously does distribute over addition (ignoring overflow), it's perhaps a reasonable question to ask. To disprove this proposition, it is enough to find a single counterexample (not hard, and much quicker than a google search) but it's more interesting to find a constructive class of counterexamples. I thought of a few strategies to disprove this, other than picking random numbers and checking, that I thought were worth writing down. 

Tangentially, on the topic of Google relevance, this search term had nothing to do with this blog until this post, but when I search for topics I think my posts <em>are</em> related to, I can't find them. I expect not to be seeing "is xor distributive over addition" in the search console in future.

<h4>Complement Argument</h4>

Would XOR distribute over the addition of a number and its logical complement? We would have that <code language="java">y ^ (x + ~x) = y ^ x + y ^ ~x</code> for any <code language="java">y</code>. Then we have <code language="java">y ^ -1 = ~y = y ^ x + y ^ ~x</code>. So based on the assumption of distributivity, <code language="java">y ^ x + y ^ ~x</code> must have none of the bits from <code language="java">y</code>. We have a contradiction because it is clear that all of the bits in <code language="java">y ^ x + y ^ ~x</code> are set.

<h4>Left Shift Argument</h4>

Addition causes digits to carry left when the bits in the same position are both set, so <code language="java">x + x</code> is equivalent to <code language="java">x << 1</code> (ignoring overflow). If, for any integer <code language="java">y</code>, we had that <code language="java">y ^ (x + x) = y ^ x + y ^ x</code> we can find constraints on this identity by considering either the rightmost unset bit or the leftmost set bit of <code language="java">x</code> in isolation. Considering the rightmost set bit at position <code language="java">p</code>: this bit is set on the LHS of this identity if and only if it is unset in <code language="java">y</code>. On the RHS, it is set iff its leftmost neighbour at position <code language="java">p-1</code> is unset in <code language="java">y</code>, because we shift <code language="java">y ^ x</code> to the left. So we can construct counterexamples whenever <code language="java">p</code> and <code language="java">p-1</code> differ, and the proposition is not generally true.