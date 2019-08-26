---
title: Building a Bloom Filter from Scratch
layout: post

date: 2017-09-19
---

The Bloom filter is an interesting data structure for modelling approximate sets of objects. It can tell you with certainty that an object is not in a collection, but may give false positives. If you write Java for a living, I would not suggest you implement your own, because there is a perfectly good implementation in <a href="https://github.com/google/guava/blob/master/guava/src/com/google/common/hash/BloomFilter.java" target="_blank">Guava</a>. It can be illuminating to write one from scratch, however. 

#### Interface

You can do two things with a Bloom filter: put things in it, and check if the filter probably contains items. This leads to the following interface:

```java
public class BloomFilter<T> {
    void add(T value);

    boolean mightContain(T value);
}
```

#### Java Bloom Filter Implementation

A Bloom filter represents a set of objects quite succinctly as a bit array of finite length. Unlike a bitset, the bit array stores _hashes_ of the objects, rather than object identities. In practice, you need multiple hash functions, which, modulo the capacity of the bit array, will collide only with low probability. The more hashes you have, the slower insertions and look ups will be. There is also a space trade off for improved accuracy: the larger the array, the less likely collisions of hashes modulo the capacity will be.

Since you probably want to be able to control the hash functions you use, the interface `ToIntFunction` fits in nicely as the perfect abstraction. You can set this up simply with a builder.

```java
    public static <T> Builder<T> builder() {
        return new Builder<>();
    }


    public static class Builder<T> {
        private int size;
        private List<ToIntFunction<T>> hashFunctions;

        public Builder<T> withSize(int size) {
            assert Integer.bitCount(size) == 1; 
            this.size = size;
            return this;
        }

        public Builder<T> withHashFunctions(List<ToIntFunction<T>> hashFunctions) {
            this.hashFunctions = hashFunctions;
            return this;
        }

        public BloomFilter<T> build() {
            return new BloomFilter<>(new long[size], size, hashFunctions);
        }
    }

    private final long[] array;
    private final int size;
    private final List<ToIntFunction<T>> hashFunctions;

    public BloomFilter(long[] array, int logicalSize, List<ToIntFunction<T>> hashFunctions) {
        this.array = array;
        this.size = logicalSize;
        this.hashFunctions = hashFunctions;
    }

    private int mapHash(int hash) {
        return hash & (size - 1);
    }
```

#### Adding Values

To add a value, you need to take an object, and for each hash function hash it modulo the capacity of the bit array. Using a `long[]` as the substrate of the bit set you must locate the word each hash belongs to, and set the bit corresponding to the remainder of the hash modulo 64. You can do this quickly as follows:

```java
   public void add(T value) {
        for (ToIntFunction<T> function : hashFunctions) {
            int hash = mapHash(function.applyAsInt(value));
            array[hash >>> 6] |= 1L << hash;
        }
    }
```

Note that each bit may already be set.

#### Querying the bit set

To check if an object is contained in the bitset, you need to evaluate the hashes again, and find the corresponding words. You can return false if the intersection of the appropriate word and the bit corresponding to the remainder modulo 64 is zero. That looks like this:

```java
    public boolean mightContain(T value) {
        for (ToIntFunction<T> function : hashFunctions) {
            int hash = mapHash(function.applyAsInt(value));
            if ((array[hash >>> 6] & (1L << hash)) == 0) {
                return false;
            }
        }
        return true;
    }
```

Note that this absolutely does not mean the object is contained within the set, but you can get more precise results if you are willing to perform more hash evaluations, and if you are willing to use a larger bit array. Modeling the precise false positive rate is <a href="http://cglab.ca/~morin/publications/ds/bloom-submitted.pdf" target="_blank">not clear cut</a>.

<h3>BitFunnel</h3>

Just as is the case for bitmap indices, _bit slicing_ is a useful enhancement for Bloom filters, forming the basis of <a href="https://danluu.com/bitfunnel-sigir.pdf" target="_blank">BitFunnel</a>. In a follow up post I will share a simplified implementation of a bit sliced Bloom filter.
