---
title: Depending on Implementation Details is Bad Engineering 
layout: post
date: 2020-02-25
tags: java
image: 
---

In any performance sensitive system, it is often tempting to break through component boundaries to avoid costs associated with modularity.
When you are responsible for both sides of the boundary, this is just technical debt: for a performance gain, or even a quick feature, you might pay in development time in the future.
The risks inherent in the tradeoff are best assessed by those close to the broken boundary, by the engineers who know the system well and can predict its propensity to change.
However, when you don't own both sides of the boundary, I think making this tradeoff is just irresponsible; it is bad engineering.

Nowhere is this more obvious than in the Java ecosystem, particularly in relation to `sun.misc.Unsafe`, which only really exists for expert usage within the JDK, but was not encapsulated properly.
There are compelling reasons to resort to `sun.misc.Unsafe`:

* The `ByteBuffer` abstraction, the only supported API for off-heap memory allocation, has obvious feature gaps and defects. Here is a select few. 
  * It has relative and absolute operations, but absolute get and put were only added in JDK13; [JDK-5029431](https://bugs.openjdk.java.net/browse/JDK-5029431) was resolved 15 years after creation.
  * The API is stateful and requires cloning and slicing with relative operations, often leading to allocations which can't be eliminated, which conflicts with going off heap in the first place.
  * There is no supported way to unmap a mapped `ByteBuffer` until it is garbage collected, which causes all kinds of problems in the absence of garbage collection: running out of file handles, impossible to delete mapped files on Windows...
* Bounds checks on arrays and `ByteBuffer`s, which are there to keep programs safe by throwing exceptions instead of performing illegal memory accesses, sometimes don't get eliminated by the compiler where most programmers could reason that they aren't necessary. Using `sun.misc.Unsafe` makes them go away (along with safety). However, this should be the JIT compiler's job.
* Prior to JDK9 (and the introduction of `MethodHandles byteArrayViewVarHandle` in [JEP 193](https://openjdk.java.net/jeps/193)) there was no API to reinterpret elements of a `byte[]` as wider integral types, and assembling, say, a `long` from eight `byte`s is relatively costly.
* There was the ability to define classes, removed in JDK11 ([JDK-8202999](https://bugs.openjdk.java.net/browse/JDK-8202999)), replaced by `MethodHandles.Lookup.defineClass`.
* Various very low level concurrency primitives which very few people know how to use properly (though some do) are available and enable exotic concurrent data structures.

The intent behind every usage of `sun.misc.Unsafe` is completely understandable: features not possible without `sun.misc.Unsafe` are possible; performance not possible without `sun.misc.Unsafe` is possible.
However, I think consciously going through the ceremony of breaking in via reflection and accessing `sun.misc.Unsafe` is actually bad engineering, because it leads to the creation of features for which maintenance cannot be guaranteed.
You _must_ know that when you use it, you are using an unsupported API, that it can be taken away in the future, and have no guarantee that it won't be taken away.
Moreover, not every usage of `sun.misc.Unsafe` I have seen uses the best algorithm or data structure; paying attention to computer science fundamentals is usually much more effective. 

Inevitably, JDK engineers wanted to change and encapsulate `sun.misc.Unsafe`, which would break many libraries, disincentivising its unilateral removal. 
Usage of `sun.misc.Unsafe` is so widespread, that as part of [JEP 260](https://openjdk.java.net/jeps/260), accessibility to `sun.misc.Unsafe` was preserved, delegating to `jdk.internal.misc.Unsafe`, but deprecating all functionality for which replacements exist.
Yet, if you look on GitHub, you will see that libraries are now breaking in to `jdk.internal.misc.Unsafe`, for instance in [Byte Buddy](https://github.com/raphw/byte-buddy/blob/d9a5b3af63d12730c39d15ea6830933383c648d4/byte-buddy-dep/src/main/java/net/bytebuddy/dynamic/loading/ClassInjector.java#L1884) or [Netty](https://github.com/netty/netty/blob/4.1/common/src/main/java/io/netty/util/internal/PlatformDependent0.java#L332).
This practice leads to the accumulation of leverage, making it problematic to refactor `jdk.internal.misc.Unsafe`, in case some widely used library depends on it and might break.

I would like to see libraries advertise to their users, as an attribute of quality along with test coverage and other metrics, whether they can guarantee that their library is really future proof.
That is, that their library does not depend on implementation details, won't cause issues when updating or otherwise changing JDK version, and they can guarantee that the library will work on any future version of the JDK.
For me, this would be a very positive attribute of a library.
If this means performance penalties, and it often will, then Java can enjoy a reputation as a slow language.

It occurs to me that this is all a little sanctimonious; I have made great use of many libraries which depend on `sun.misc.Unsafe`, and it's such a pragmatic thing for a library author to do.
I just think that making do with hacks like `sun.misc.Unsafe` is the wrong thing to do because it changes the incentives for improvement; working around inferior APIs reduces pressure for their replacement. 

A better approach would be to vote with one's feet and just not use Java; if there is no API fit for a given purpose, use more suitable platforms until there is a proper alternative, and tell people about it.
Migrate away from using or providing services related to Java, until or unless the platform provides suitable APIs.
I think it's fine to say that Java should not be used for a certain problem, and this is better than to provide an ultimately flaky solution.
Whilst it is a testament to the commitment and tenacity of various library authors prepared to resort to hacks to create possibilities, sometimes it is better for a feature not to exist if its maintenance cannot be guaranteed.

> If you're reading this, don't miss [The Official JVM Performance League Table](/posts/official-jvm-performance-league-table)!

