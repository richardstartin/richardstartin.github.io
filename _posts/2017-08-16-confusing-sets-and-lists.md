---
ID: 8070
post_title: Confusing Sets and Lists
author: Richard Startin
post_excerpt: ""
layout: post
permalink: >
  http://richardstartin.uk/confusing-sets-and-lists/
published: true
post_date: 2017-08-16 10:25:31
---
I have often seen the roles of lists and sets confused. An application can be brought to its knees - that is, cease to deliver commercial value - if <code>List.contains</code> is called frequently enough on big enough lists. And then there is the workaround... When I moved over to Java from C++ several years ago, it seemed utterly crazy that there was even a <code>Collection</code> interface - <em>exactly</em> what Scott Meier's <em>Effective STL</em> said not to do. I still think it's crazy. Sets and lists cannot be substituted, and when you add up the marginal costs, as well as the costs of any compensatory workarounds, confusing them is responsible for a lot of performance bugs. As an application developer, it is part of your job to choose. Here are a few simple examples of when to use each collection type.

<h3>Contains</h3>
<blockquote>Is an element in the collection?</blockquote>
Never ever do this with a <code>List</code>. This operation is often referred to as being O(n). Which means in your worst case will touch every element in the list (technically, at least once). You have a choice between <code>HashSet</code> and a <code>TreeSet</code>, and both have costs and benefits.

If you choose a <code>HashSet</code>, your best case is O(1): you evaluate a hash code, take its modulus with respect to the size of an array, and look up a bucket containing only one element. The worst case occurs with a degenerate hash code which maps all elements to the same bucket. This is again O(n): you probe a linked list testing each element for equality. On average you get something between these two cases and it depends on the uniformity of your hash code implementation.

If you choose a <code>TreeSet</code> you get a worst case O(log n): this is effectively just a binary search through the nodes in a red black tree. Performance is limited by the cost of the comparator, and suffers systematically from cache misses for large sets (like any kind of pointer chasing, branch prediction and prefetching is difficult if not impossible).

If you're working with numbers, and small to medium collections, a sorted primitive array may be the best approach, so long as it fits in cache. If you're working with integers, you can do this in constant time in the worst case by using a <code>BitSet</code>.

<h3>Select</h3>
<blockquote>What is the value of the element at a given index with respect to a sort order?</blockquote>
This is an obvious use case for a <code>List</code>: it's O(1) - this is just a lookup at an array offset.

You couldn't even write the code with a <code>HashSet</code> without copying the data into an intermediate ordered structure, at which point you would probably think again. You see this sort of thing done in code written by inexpensive programmers at large outsourcing consultancies, who were perhaps just under unreasonable pressure to deliver to arbitrary deadlines.

<code>SortedSet</code>, and anything conceptually similar, is the wrong data structure for this operation. The only way to compute this is O(n): you iterate through the set incrementing a counter until you reach the index, and then return the element you've iterated to. If you reach the end of the set, you throw. If you do this a lot, you'll notice.

<h3>Rank</h3>
<blockquote>How many predecessors does an element have with respect to a sort order?</blockquote>

Another classic operation for <code>List</code>, so long as you keep it sorted. Use <code>Collections.binarySearch</code> to find the index of the element in the collection with complexity O(log n). This is its rank. If you can get away with it, primitive arrays will be much better here, especially if they are small enough to fit in cache.

Once again, there are creativity points available for the solution involving a <code>HashSet</code>, and they do exist in the wild, but a clean looking solution is at least <em>possible</em> with a <code>SortedSet</code>. However, it involves an iteration with another check against an incrementing counter. It's O(n) and if you do it a lot, you'll blow your performance profile, so use a sorted list instead.

<h3>What if you had the source code?</h3>

Is this fundamental or just a limitation of the Collections framework? Maybe if you had the source code you could just make these data structures optimal for every use case, without having to choose the right one? Not without creating a Frankenstein, and not without a <em>lot</em> of memory. Optimisation isn't free.