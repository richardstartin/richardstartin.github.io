---
ID: 3196
post_title: >
  Microsecond Latency Rules Engine with
  RoaringBitmap
author: Richard Startin
post_excerpt: ""
layout: post
permalink: >
  http://richardstartin.uk/fast-and-simple-rules-engine-with-roaringbitmap/
published: true
post_date: 2017-04-08 11:39:06
---
Implementing a rules engine can shorten development time and remove a lot of tedious if statements from your business logic. Unfortunately they are almost always slow and often bloated. Simple rules engines can be implemented by assigning integer salience to each line in a truth table, with rule resolution treated as an iterative intersection of ordered sets of integers. Implemented in terms of sorted sets, it would be remiss not to consider <a href="https://github.com/RoaringBitmap/RoaringBitmap" target="_blank">RoaringBitmap</a> for the engine's core. The code is at <a href="https://github.com/richardstartin/rst" target="_blank">github</a>.
<h3>Classification Table and Syntax</h3>
This rules engine builds on the simple idea of a truth table usually used to teach predicate logic and computer hardware. Starting with a table and some attributes, interpreting one attribute as a classification, we get a list of rules. It is trivial to load such a table from a database. Since classifications can overlap, we prioritise by putting the rules we care about most - or the most salient rules - at the top of the table. When multiple rules match a fact, we take the last in the set ordered by salience. So we don't always have to specify all of the attributes to get a classification, we can rank attributes by their importance left to right, where it's required that all attributes to the left of a specified attribute are also specified when matching a fact against a rule set.

It's possible to define rules containing wildcards. Wildcard rules will match any query (<strong>warning</strong>: if these are marked as high salience they will hide more specific rules with lower salience). It's also possible to specify a prefix with a wildcard, which will match any query that matches at least the prefix.

Below is an example table consisting of rules for classification of regional English accents by phonetic feature.

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
English Accent Rules
<thead>
<th>thought</th>
<th>cloth</th>
<th>lot</th>
<th>palm</th>
<th>plant</th>
<th>bath</th>
<th>trap</th>
<th>accent</th>
</thead>
<tbody>
<tr><td>/ɔ/</td><td>/ɒ/</td><td>/ɑ/</td><td>/ɑː/</td><td>/ɑː/</td><td>/ɑː/<td>/æ/</td><td>Received Pronunciation (UK)</td></tr>
<tr><td>/ɔ/</td><td>/ɔ/</td><td>/ɑ/</td><td>/ɑ/</td><td>/æ/</td><td>/æ/<td>/æ/</td><td>Georgian (US)</td></tr>
<tr><td>/ɑ/</td><td>/ɑ/</td><td>/ɑ/</td><td>/ɑ/</td><td>/æ/</td><td>/æ/<td>/æ/</td><td>Canadian</td></tr>
<tr><td>*</td><td>*</td><td>/ɑ/</td><td>/ɑ/</td><td>/æ/</td><td>/æ/<td>/æ/</td><td>North American</td></tr>
<tr><td>*</td><td>*</td><td>*</td><td>*</td><td>*</td><td>*<td>/æ/</td><td>Non Native</td></tr>
<tr><td>*</td><td>*</td><td>*</td><td>*</td><td>*</td><td>*<td>*</td><td>French</td></tr>
</tbody>
</table> 
</div>

In the example above, the vowel sounds used in words differentiating speakers of several English accents are configured as a classification table. The accent column is the classification of any speaker exhibiting the properties specified in the six leftmost columns. UK Received Pronunciation is the most specific rule and has high salience, whereas various North American accents differ from RP in their use of short <em>A</em> vowels. A catch all for North American accents would wild card the sounds in <em>thought</em> and <em>caught</em> (contrast Boston pronunciations with Texas). So long as <em>trap</em> has been pronounced with a short <em>A</em> (which all English speakers do), and no other rule would recognise the sounds used in the first six words, the rule engine would conclude the speaker is using English as a second language. If not even the word trap is recognisable, then the speaker is probably unintelligible, or could be French. 

<h3>Implementation</h3>
A rule with a given salience can be represented by creating a <a href="http://richardstartin.uk/how-a-bitmap-index-works/" target="_blank">bitmap index</a> on salience by the attribute values of the rules. For instance, to store the rule <code language="java">{foo, bar} -> 42</code>, with salience 10, create a bitmap index on the first attribute of the rule, and set the 10th bit of the "foo" bitmap; likewise for the "bar" bitmap of the second index. Finding rules which match both attributes is a bitwise intersection, and since we rank by salience, the rule that wins is the first in the set. An obvious choice for fast ordered sets is RoaringBitmap.

<a href="http://richardstartin.uk/a-quick-look-at-roaringbitmap/" target="_blank">RoaringBitmap consists of containers</a>, which are fast, cache-friendly sorted sets of integers, and can contain up to 2^16 shorts. In RoaringBitmap, containers are indexed by keys consisting of the most significant 16 bits of the integer. For a rules engine, if you have more than 2^16 rules you have a much bigger problem anyway, so a container could index all the rules you could ever need, so RoaringBitmap itself would be overkill. While RoaringBitmap indexes containers by shorts (it does so for the sake of compression), we can implement wildcard and prefix matching by associating containers with Strings rather than shorts. As the core data structure of the rules engine, a RoaringBitmap <em>container</em> is placed at each node of an Apache commons PatriciaTrie. It's really that simple - see the source at <a href="https://github.com/richardstartin/rst/blob/master/src/main/java/com/openkappa/rst/Classifier.java" target="_blank">github</a>.

When the rules engine is queried, a set consisting of all the rules that match is intersected with the container found at the node in the trie matching the value specified for each attribute. When more than one rule matches, the rule with the highest salience is accessed via the Container.first() method, <a href="https://github.com/RoaringBitmap/RoaringBitmap/pull/148" target="_blank">one of the features I have contributed to RoaringBitmap</a>. See example usage at <a href="https://github.com/richardstartin/rst/blob/master/src/test/java/com/openkappa/rst/ClassifierTest.java" target="_blank">github</a>.

 

 