---
title: "Microsecond Latency Rules Engine with RoaringBitmap"
layout: post

date: 2017-04-08
---

Implementing a rules engine can shorten development time and remove a lot of tedious if statements from your business logic. Unfortunately they are almost always slow and often bloated. Simple rules engines can be implemented by assigning integer salience to each line in a truth table, with rule resolution treated as an iterative intersection of ordered sets of integers. Implemented in terms of sorted sets, it would be remiss not to consider [RoaringBitmap](https://github.com/RoaringBitmap/RoaringBitmap) for the engine's core. The code is at [github](https://github.com/richardstartin/rst).

#### Classification Table and Syntax

This rules engine builds on the simple idea of a truth table usually used to teach predicate logic and computer hardware. Starting with a table and some attributes, interpreting one attribute as a classification, we get a list of rules. It is trivial to load such a table from a database. Since classifications can overlap, we prioritise by putting the rules we care about most - or the most salient rules - at the top of the table. When multiple rules match a fact, we take the last in the set ordered by salience. So we don't always have to specify all of the attributes to get a classification, we can rank attributes by their importance left to right, where it's required that all attributes to the left of a specified attribute are also specified when matching a fact against a rule set.

It's possible to define rules containing wildcards. Wildcard rules will match any query (**warning**: if these are marked as high salience they will hide more specific rules with lower salience). It's also possible to specify a prefix with a wildcard, which will match any query that matches at least the prefix.

Below is an example table consisting of rules for classification of regional English accents by phonetic feature.

|thought|cloth|lot|palm|plant|bath|trap|accent|
|--- |--- |--- |--- |--- |--- |--- |--- |
|/ɔ/|/ɒ/|/ɑ/|/ɑː/|/ɑː/|/ɑː/|/æ/|Received Pronunciation (UK)|
|/ɔ/|/ɔ/|/ɑ/|/ɑ/|/æ/|/æ/|/æ/|Georgian (US)|
|/ɑ/|/ɑ/|/ɑ/|/ɑ/|/æ/|/æ/|/æ/|Canadian|
|*|*|/ɑ/|/ɑ/|/æ/|/æ/|/æ/|North American|
|*|*|*|*|*|*|/æ/|Non Native|
|*|*|*|*|*|*|*|French|


In the example above, the vowel sounds used in words differentiating speakers of several English accents are configured as a classification table. The accent column is the classification of any speaker exhibiting the properties specified in the six leftmost columns. UK Received Pronunciation is the most specific rule and has high salience, whereas various North American accents differ from RP in their use of short _A_ vowels. A catch all for North American accents would wild card the sounds in _thought_ and _caught_ (contrast Boston pronunciations with Texas). So long as _trap_ has been pronounced with a short _A_ (which all English speakers do), and no other rule would recognise the sounds used in the first six words, the rule engine would conclude the speaker is using English as a second language. If not even the word trap is recognisable, then the speaker is probably unintelligible, or could be French. 

#### Implementation

A rule with a given salience can be represented by creating a [bitmap index](https://richardstartin.github.io/posts/how-a-bitmap-index-works) on salience by the attribute values of the rules. For instance, to store the rule `{foo, bar} -> 42`, with salience 10, create a bitmap index on the first attribute of the rule, and set the 10th bit of the "foo" bitmap; likewise for the "bar" bitmap of the second index. Finding rules which match both attributes is a bitwise intersection, and since we rank by salience, the rule that wins is the first in the set. An obvious choice for fast ordered sets is RoaringBitmap.

[RoaringBitmap consists of containers](https://richardstartin.github.io/posts/a-quick-look-at-roaringbitmap/), which are fast, cache-friendly sorted sets of integers, and can contain up to 2^16 shorts. In RoaringBitmap, containers are indexed by keys consisting of the most significant 16 bits of the integer. For a rules engine, if you have more than 2^16 rules you have a much bigger problem anyway, so a container could index all the rules you could ever need, so RoaringBitmap itself would be overkill. While RoaringBitmap indexes containers by shorts (it does so for the sake of compression), we can implement wildcard and prefix matching by associating containers with Strings rather than shorts. As the core data structure of the rules engine, a RoaringBitmap _container_ is placed at each node of an Apache commons `PatriciaTrie`. It's really that simple - see the source at [github](https://github.com/richardstartin/rst/blob/master/src/main/java/com/openkappa/rst/Classifier.java).

When the rules engine is queried, a set consisting of all the rules that match is intersected with the container found at the node in the trie matching the value specified for each attribute. When more than one rule matches, the rule with the highest salience is accessed via the Container.first() method, [one of the features I have contributed to RoaringBitmap](https://github.com/RoaringBitmap/RoaringBitmap/pull/148). See example usage at [github](https://github.com/richardstartin/rst/blob/master/src/test/java/com/openkappa/rst/ClassifierTest.java).

 

 
