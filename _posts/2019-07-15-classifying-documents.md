---
title: "Classifying Documents"
layout: post
date: 2019-07-15
tags: java pattern-matching
---

This article describes the design of [bitrules](https://github.com/richardstartin/multi-matcher), a reasonably efficient data structure for applying large sets of simple rules to documents.
This sort of problem comes up all the time in data driven systems, where documents need to be introspected to determine what to do in some next step.
This could be as simple as needing to tag data, deciding what kinds of discounts to apply to an order, or determining what kinds of financial risks apply to a trade in the planning stage of a risk calculation.

These rules tend to be expressed in terms of literal equality and range operators, and logical conjuction.
One approach might be to load a list of definitions of such rules from a database or a file and generate a predicate for each line definition.
These rules could be represented by functions which could be used to map the elements of the input, which is assumed to be a `Stream<T>`.

```java
public interface Rule<T, C> {

    boolean matches(T value);

    C classification();
}
```

Applying the rules is very easy, and if there is overlap the first rule to match is chosen.

```java
public class Classifier<T, C> {

    private final List<Rule<T, C>> rules;

    public Optional<C> classifiy(T value) {
        for (Rule<T, C> rule : rules) {
            if (rule.matches(value)) {
                return Optional.of(rule.classification());
            }
        }
        return Optional.empty();
    }
}
```

The worst case complexity of this algorithm is linear in the number of rules, so we should expect the runtime to be the sum product of the cost of each rule and the number of rules.
When at least one rule matches, the loop exits early, but whenever no matching rules are found, we get the worst case.
With a handful of rules, this hardly matters, but there is a limit on the number of rules that can be added to the system without degrading performance significantly.

How can we do better?
The answer lies in the structure of the rules themselves.
The first thing to notice is that many rule sets contain repetition, for example, there may be several rules containing the same constraint `productType = "electronics"`.
If this is the case, it seems wasteful to represent or apply this constraint more than once.
The rules may not be independent: if we have rules with constraints `price < 200` and `price < 300`, then whenever the first constraint is satisfied, so is the second, so it can be eliminated.

To represent this as a data structure, each rule is assigned an integer identity, which can be used to track the dependent conditions for the rule to fire.
Constraints are extracted from the rules and grouped by attribute and relation.
The rules below (notice that the rules don't all have the same attributes) can be grouped:


 ```sql
 productType = "electronics" and price < 200 and quantity > 10 -> "class1"
 productType = "electronics" and price < 300 -> "class2"
 productType = "books" and quantity = 1 -> "class3"
 ```

 ```json
 {
    "classifications" : [ "class1", "class2", "class3" ],
    "constraints" : [
        {
            "name" : "productType",
            "operators" : [
                "equals" : {
                    "electronics" : [0, 1],
                    "books" : [2],
                    "*" : []
                }
            ]
        },
        {
            "name" : "price",
            "operators" : [
                "lessThan" : {
                    200 : [0],
                    300 : [1],
                    "*" : [2]
                }
            ]
        },
        {
            "name" : "quanity",
            "operators" : [
                "greaterThan" : {
                    10 : [0],
                    "*" : [1, 2]
                },
                "equals" : {
                    1 : [2],
                    "*" : [0, 1]
                }
            ]
        }
    ]
 }
 ```

Whenever an attribute/relation pair do not constrain a rule, the rule is added to the "wildcard" for the pair.
This structure means that we could have as many rules as we like, and if several of the rules apply to "electronics" products, there will only ever be one "electronics" attribute, along with a list of the rules partially satisfied by the constraint.
This might save a little bit of space, but really this structure dictates the evaluation algorithm, which tries to do as little work as possible, and will check the product type of the input document at most once.

The algorithm starts by assuming that the document satisfies all rules, and works through the constraints to figure out which rules still match after applying the constraint to the data found in the document.

```java
  // see MaskedClassifier
  private MaskType match(Input value) {
    MaskType context = mask.clone();
    Iterator<Matcher<Input, MaskType>> it = rules.iterator();
    while (it.hasNext() && !context.isEmpty()) {
      context = it.next().match(value, context);
    }
    return context;
  }

```

The rules that could still match the document at any point during evaluation are represented as a bitset, starting off as a contiguous range `[0, numRules)`. For each constraint, the value of the relevant attribute is read from the document.
The attribute value is used to locate the associated bitset of rule identities (a map lookup for discrete constraints or a binary search for range constraints), and united with the wildcards.
This bitset is then intersected with the rules which already match, and if it becomes empty, the evaluation terminates.
If the bitset is non empty by the end of the evaluation, it contains the identities of the rules which match the document.
When there is overlap, and only one value is required, it is now just a case of assigning salience to the rules by assigning higher priority rules lower identities, and taking the first bit in the set.

All of the above assumes that the only logical conjugation is intersection, and a single rule containing a union cannot be expressed this way.
However, rules containing unions can be split into two smaller rules, and there is no limitation that the classifications must be unique; both branches of the union can result in the same classification.

By way of example, the evaluation would follow this sequence for the following document:

```json
{
  "productType" : "electronics",
  "quantity": 2,
  "price": 199
}

```

```
1. assume all rules match
rules = {0, 1, 2}
2. get the "productTypes" equality constraint,
   a) get the "electronics" bitset
   b) get the wildcard
   eliminates rule 2
rules = rules & {0, 1} | {} = {0, 1}
3. get the price less than constraints
   a) get all bitsets such that 199 < threshold
   b) get the wildcard
   does not eliminate any rules, but we had to check
rules = rules & {0} | {1} | {2} = {0, 1}
4. get the quantity constraints
    a) get the greater than constraint
        i) get all bitsets for thresholds where 2 > threshold (there are none)
        ii) get the wildcard
    b) get the equality constraint
        i) get the bitset where quantity == 1 (there isn't one)
        ii) get the wildcard
    c) intersect each result with the existing results independently
rules = ({0, 1} & ({} | {1, 2})) & ({0, 1} & ({} | {0, 1})) = {1}
5. get the classification at index 1 of the array ("class1")
```

This rule set and example can be run in Java as follows:

```java
    // declare a schema, associating attribute accessors with some kind of key (a string here)
    Schema<String, Foo> schema = Schema.<String, Foo>create()
            .withAttribute("productType", Foo::getProductType)
            .withAttribute("qty", Foo::getQuantity)
            .withAttribute("price", Foo::getPrice);
    // build the classifier from the rules and the schema
    ImmutableClassifier<Foo, String> classifier = ImmutableClassifier.<String, Foo, String>builder(schema).build(
            Arrays.asList(
              MatchingConstraint.<String, String>anonymous()
                      .eq("productType", "electronics")
                      .gt("qty", 10)
                      .lt("price", 200)
                      .classification("class1")
                      .build(),
              MatchingConstraint.<String, String>anonymous()
                      .eq("productType", "electronics")
                      .lt("price", 300)
                      .classification("class2")
                      .build(),
              MatchingConstraint.<String, String>anonymous()
                      .eq("productType", "books")
                      .eq("qty", 1)
                      .classification("class3")
                      .build()
            ));
    assertEquals("class2", classifier.classification(new Foo("electronics", 2, 199)).orElse("none"));
```

Most of the operations outlined above are hashmap lookups and bitset intersections, which are cheap.
However, the range lookups include binary search to find the first threshold which the numeric value would satisfy, and then iterates over the remaining unbreached thresholds, doing a bitset union for each threshold.
Bitset unions are not as cheap as intersections because they tend to increase size, and all of these unions can be precomputed once all thresholds are known, at the cost of some memory to store the precomputed bitsets.
As the classifier is being built, all inverted rule sets are accumulated verbatim, as in the JSON example above. Before the classifier, which is immutable, is built, each constraint matcher is "frozen".
Freezing the matcher triggers a recursive optimisation pass where each node in the tree can optimise its structure if necessary.
In the case of numeric range attributes, for each threshold, the bitset associated with any dominated threshold is united.
This has a cost in RAM footprint, and works better with a small number of thresholds. After freezing, the structure with range predicates looks like the following:

 ```json
 {
    "classifications" : [ "class1", "class2", "class3" ],
    "constraints" : [
        {
            "name" : "productType",
            "operators" : [
                "equals" : {
                    "electronics" : [0, 1],
                    "books" : [2],
                    "*" : []
                }
            ]
        },
        {
            "name" : "price",
            "operators" : [
                "lessThan" : {
                    200 : [0],
                    300 : [0, 1],
                    "*" : [2]
                }
            ]
        },
        {
            "name" : "quantity",
            "operators" : [
                "greaterThan" : {
                    10 : [0],
                    "*" : [1, 2]
                },
                "equals" : {
                    1 : [2],
                    "*" : [0, 1]
                }
            ]
        }
    ]
 }
 ```

This is all quite a lot more complicated than a simple list of predicates - is it worth it? Probably.
I have used this in the past to great effect, applying thousands of classification rules to documents in the order of small microseconds per document per thread.
There's more I would like to do with this idea though: I would like to plug the constraint matching into a streaming JSON parser, allowing for the classification of arbitrary JSON without materialisation.






