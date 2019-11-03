---
title: "Multidimensional Switches"
layout: default
author: "Richard Startin"
date: 2019-09-01
---

I was reading my Twitter feed this morning when I noticed Brian Goetz talking about multidimensional switch expressions.
This would be an amazing feature for the Java language. I wonder, if the feature were to arrive in Java, which data structure could be used to implement it?
Ultimately, I think efficient multi-dimensional pattern matching requires multi-dimensional data structures.

What is a multi-dimensional switch expression? As a staple of functional programming, Scala has had these for years: the match expression.

```scala
def doIt(attr1: String, attr2: Int, attr3: String): Unit = 
    (attr1, attr2, attr3) match {
        case ("a1", 0, "c1") => action1()
        case ("a1", 1, "c1") => action2()
        case ("a2", 1, "c1") => action3()
        case ("a1", 0, "c2") => action4()
        case ("a1", 0, _)    => action5()
        case _               => defaultAction()
    }
```

If you don't know what the expression does, you can run it at [ScalaFiddle.io](https://scalafiddle.io/sf/kUArgNL/1).
There are a few things to note about this expression.
Firstly, it's intentionally simplified: it excludes case classes, type checks and conditional expressions.
Case classes are excluded as only syntactically related to what I want to write about; type checks and conditional expressions are relevant but I will follow up on these later. However, the expression deliberately includes overlapping cases, because the evaluation must choose the first case to match, in the order the statement is written (this is why the guard is always at the bottom). Whatever syntax we may end up getting in Java, I will assume the Scala function above would be expressible. 

While one might think the cascading nature of the expression makes an iterative evaluation over a tree-like data structure necessary, I think this can be implemented efficiently with overlapping bit masks, stored in hash tables.
I suspect that the data structure I am about to explain would enable much faster matching than a decision tree (and I have implemented it for higher level purposes). 

Four definitions are required:

 1. _dimensions_: the parameters.
 2. _attribute values_: the values of the parameters.
 3. _priorities_: when cases overlap, which takes precedence?
 4. _wildcards_: not all expressions constrain attribute values.

 The expression is static so the compiler knows that there are only three dimensions, six cases, and it also knows all the literal values involved.
 To represent the expression above, we need three dimensions; one for each parameter `attr1`, `attr2`, and `attr3`. For each dimension, we need a hash table mapping the known literal values to bit masks of the cases they relate to.
 The bits in each mask relate to the position of the case in the expression, and therefore its priority when there is overlap.
 This is important when there are multiple matches.

 By way of example, the expression above has the illustrated physical representation.

 ```
 index:
     attr1 -> { "a1" -> 0x11011, "a2" -> 0x100 }
     attr2 -> { 0 -> 0x11001, 1 -> 0x110 }
     attr3 -> { "c1" -> 0x111, 1 -> 0x1000, "*" -> 0x10000 }
     guard -> 0x100000
 table:
    [action1, action2, action3, action4, action5, defaultAction]

 ```

This representation consists of an index relating attribute-values with the priorities of each case separately for each attribute, and a table of pointers to the relevant routines.
There is also a guard, which is the bit mask of the guarded action (i.e. what happens if no other pattern is matched).

Since all of this information is available to the compiler and doesn't change at run time, I expect that the data structure outlined could be built at compile time (but I'm not a compiler developer).

How can it be used at run time?

Each attribute-value must be looked up in a hash table for each dimension of the index. 
If there are three attributes, this means three hash table lookups per match evaluation.
Sometimes masks will be found, because the programmer wrote at least one case matching the particular attribute-value, but there may also be wildcards, where the case does not depend on the value of the attribute.
The retrieved mask, and the wildcard, if either exist, must be united, since literal matches also match wildcards.
Once the masks have been retrieved for all dimensions, they can be intersected to find the cases which match all constraints.
It's possible that no cases match the input, so the guard mask with the position of the guard cases should be united with the result.
In general, the resulting bit mask can have several bits set, but since the bits correspond to priority, calculating the first bit of the mask, supported by the fast `tzcnt` instruction, gives the position of the highest priority case in the expression.
That is, the first case to match the input.
The guard bit mask has its only bit set at the last possible position, so never hides other cases.

Concretely, how would some values of tuples of `attr1`, `attr2`, and `attr3` be matched?

```
("a1", 0, "c1")

1. lookup mask for attr1="a1": 0x11011
    no wildcard
2. lookup mask for attr2=0: 0x11001
    no wildcard
3. lookup mask for attr3="c1": 0x111
    get wildcard 0x10000
    let mask = 0x111 | 0x10000 = 0x10111
4. intersect masks: 0x11011 & 0x11001 & 0x10111 = 0x10001
5. unite with guard: 0x10001 | 0x100000 = 0x100001
6. count trailing zeroes: 0
7. go to position 0 of table (action1)

("a1", 0, "foo")

1. lookup mask for attr1="a1": 0x11011
    no wildcard
2. lookup mask for attr2=0: 0x11001
    no wildcard
3. lookup mask for attr3="foo": 0x0
    get wildcard 0x10000
    let mask = 0x0 | 0x10000 = 0x10000
4. intersect masks: 0x11011 & 0x11001 & 0x10000 = 0x10000
5. unite with guard: 0x10000 | 0x100000 = 0x110000
6. count trailing zeroes: 4
7. go to position 4 of table (action5)

("lol", 42, "wtf")

1. lookup mask for attr1="lol": 0x0
    no wildcard
2. lookup mask for attr2=42: 0x0
    no wildcard
3. lookup mask for attr3="wtf": 0x0
    get wildcard 0x10000
    let mask = 0x0 | 0x10000 = 0x10000
4. intersect masks: 0x0 & 0x0 & 0x10000 = 0x0
5. unite with guard: 0x0 | 0x100000 = 0x100000
6. count trailing zeroes: 5
7. go to position 5 of table (defaultAction - the guard)
```

I avoided writing about type checking to make the example simple, but this is just another dimension, the values are the concrete types (or maybe the class words).
Scala supports constraining the value of an attribute value in a match case by adding an if statement after the case, typical use cases being requiring positive integers.
I wonder if Java will have these, but I hope so. I didn't avoid these because I don't think they can be modeled similarly: they can.
I implemented this data structure as [bitrules](https://github.com/richardstartin/bitrules) for pattern matching on much larger sets of rules than would be practical in a match expression.
In that project, I implemented numeric and range conditions in terms of sorted arrays of thresholds, rather than as a hash table, but the idea is virtually identical.
