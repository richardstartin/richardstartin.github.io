---
ID: 10000
title: Beware Collection Factory Methods
author: Richard Startin
post_excerpt: ""
layout: post
redirect_from:
  - /beware-collection-factory-methods/
published: true
date: 2017-11-19 20:24:39
tags: java analysis
---
I saw an interesting tweet referencing a <a href="https://github.com/google/guava/issues/1268" rel="noopener" target="_blank">Github issue</a> where the impact of including an (in my view) unnecessary implementation of the `List` interface impacted inlining decisions, causing 20x degradation in throughput. Guava's `ImmutableList` is my favourite class to seek and destroy because of the way it is often used - it tends to be associated with unnecessary copying where encapsulation would be a better solution. I had assumed performance gains won from finding and deleting all the instances of `ImmutableList` had been thanks to relieving the garbage collector from medieval torture. The performance degradation observed in the benchmark is caused by use of `ImmutableList`, along with all its subclasses, alongside `ArrayList`, making calls to `List` <em>bimorphic</em> at best, causing the JIT compiler to generate slower code. I may have inadvertently profited from better inlining in the past simply by removing as many `ImmutableList`s as possible!

This post doesn't go into any details about the various mechanisms of method dispatch, and if you want to understand the impact of polymorphism on inlining, bookmark Aleksey Shipilev's authoritative <a href="https://shipilev.net/blog/2015/black-magic-method-dispatch/" rel="noopener" target="_blank">post</a> and read it when you have some time to really concentrate.

Without resorting to using `LinkedList`, is it possible to contrive cases in Java 9 where performance is severely degraded by usages of `Collections.unmodifiableList` and `List.of` factory methods? Along with `ArrayList`, these are random access data structures so this should highlight the potential performance gains inlining can give.

The methodology is very simple: I randomly vary the `List` implementation and plug it into the same algorithm. It is cruder than you would see in Aleksey Shipilev's post because I've targeted only the <strong>worst case</strong> by creating equal bias between implementations. Aleksey demonstrates that inlining decisions are statistical and opportunistic (the JIT can guess and later deoptimise), and if 90% of your call sites dispatch to the same implementation, it doesn't matter as much as when the choice is made uniformly. It will vary from application to application, but it could easily be as bad as the case I present if `List` is used polymorphically.

I created five benchmarks which produce the same number, the same way. Three of these benchmarks only ever call into a single implementation of `List` and will be inlined monomorphically, to avoid bias, the result is XOR'd with a call to `ThreadLocalRandom.current().nextInt()` because the other benchmarks need this. One benchmark only ever calls into `List.of` and `ArrayList`, then one benchmark randomly chooses a list for each invocation. The difference is stark. You can really screw up performance by making the methods on `List` megamorphic.

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
<td>sumLength_ArrayList</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">55.785270</td>
<td align="right">3.218552</td>
<td>ops/us</td>
</tr>
<tr>
<td>sumLength_Factory</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">58.565918</td>
<td align="right">2.852415</td>
<td>ops/us</td>
</tr>
<tr>
<td>sumLength_Random2</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">35.842255</td>
<td align="right">0.684658</td>
<td>ops/us</td>
</tr>
<tr>
<td>sumLength_Random3</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">11.177564</td>
<td align="right">0.080164</td>
<td>ops/us</td>
</tr>
<tr>
<td>sumLength_Unmodifiable</td>
<td>thrpt</td>
<td>1</td>
<td align="right">10</td>
<td align="right">51.776108</td>
<td align="right">3.751297</td>
<td>ops/us</td>
</tr>
</tbody></table>
</div>

```java
@State(Scope.Thread)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
public class MegamorphicList {

    private List<String>[] strings;

    @Setup(Level.Trial)
    public void init() {
        strings = new List[]{getArrayList(6), getFactoryList6(), getUnModifiableList(6)};
    }

    @Benchmark
    public int sumLength_ArrayList(Blackhole bh) {
        List<String> list = strings[0];
        int blackhole = 0;
        for (int i = 0; i < list.size(); ++i) {
            blackhole += list.get(i).length();
        }
        return blackhole ^ ThreadLocalRandom.current().nextInt(3);
    }


    @Benchmark
    public int sumLength_Factory() {
        List<String> list = strings[1];
        int blackhole = 0;
        for (int i = 0; i < list.size(); ++i) {
            blackhole += list.get(i).length();
        }
        return blackhole ^ ThreadLocalRandom.current().nextInt(3);
    }


    @Benchmark
    public int sumLength_Unmodifiable() {
        List<String> list = strings[2];
        int blackhole = 0;
        for (int i = 0; i < list.size(); ++i) {
            blackhole += list.get(i).length();
        }
        return blackhole ^ ThreadLocalRandom.current().nextInt(3);
    }

    @Benchmark
    public int sumLength_Random2() {
        List<String> list = strings[ThreadLocalRandom.current().nextInt(2)];
        int blackhole = 0;
        for (int i = 0; i < list.size(); ++i) {
            blackhole += list.get(i).length();
        }
        return blackhole;
    }

    @Benchmark
    public int sumLength_Random3() {
        List<String> list = strings[ThreadLocalRandom.current().nextInt(3)];
        int blackhole = 0;
        for (int i = 0; i < list.size(); ++i) {
            blackhole += list.get(i).length();
        }
        return blackhole;
    }

    private List<String> getUnModifiableList(int size) {
        return Collections.unmodifiableList(getArrayList(size));
    }


    private List<String> getFactoryList6() {
        return List.of(randomString(),
                       randomString(),
                       randomString(),
                       randomString(),
                       randomString(),
                       randomString()
                );
    }


    private List<String> getArrayList(int size) {
        List<String> list = new ArrayList<>();
        for (int i = 0; i < size; ++i) {
            list.add(randomString());
        }
        return list;
    }


    private String randomString() {
        return new String(DataUtil.createByteArray(ThreadLocalRandom.current().nextInt(10, 20)));
    }

}
```

Since writing this post, I have been challenged on whether this result is due to failure to inline or not. This can be easily verified by setting the following JVM arguments to print compilation:

<pre>
-XX:+PrintCompilation -XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining
</pre>

You will see the `ArrayList` and `ListN` get inlined quickly in isolation:

<pre>
\-> TypeProfile (19810/19810 counts) = java/util/ArrayList
@ 27   java.util.ArrayList::get (15 bytes)   inline (hot)
...
\-> TypeProfile (363174/363174 counts) = java/util/ImmutableCollections$ListN
@ 24   java.util.ImmutableCollections$ListN::get (17 bytes)   inline (hot)
</pre>


However, the call remains virtual (and not inlined) when three or more implementations are present:

<pre>
@ 30   java.util.List::get (0 bytes)   virtual call
</pre>

I didn't even bother to use factory methods with different arity, because three is the magic number. Syntactic sugar is nice, but use them with caution.
