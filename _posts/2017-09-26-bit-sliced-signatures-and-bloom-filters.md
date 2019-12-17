---
title: "Bit-Sliced Signatures and Bloom Filters"
layout: default
redirect_from:
  - /bit-sliced-signatures-and-bloom-filters/
date: 2017-09-26
---

While the inverted index is a familiar indexing structure for many with a casual interest in information retrieval, the concept of a <em>document signature</em> may not be. The idea seems to have a long history, having been popular until it lost favour in the late 90s, owing to file sizes and performance empirically inferior to inverted indices. However, there has been new research into the use of signatures for search problems in the last decade, for instance, <a href="https://arxiv.org/pdf/1204.5373.pdf" target="_blank">TopSig</a>, and they are an important building block of the <a href="https://danluu.com/bitfunnel-sigir.pdf" target="_blank">BitFunnel</a> data structure. 

### Information Retrieval with Signatures

An `m` bit signature of a document consists of a bit array of fixed length `m` containing the (not guaranteed to be disjoint) union of the signatures of the terms found in the document. The signature of a term `t` is the `m` bit array with each `j`th bit set where `j = hash(k, t) mod m`, for each of `k` hash functions. This is obviously a Bloom filter by another name. <a href="https://richardstartin.github.io/posts/building-a-bloom-filter-from-scratch/" target="_blank">In a recent post I noted that a Bloom filter's behaviour can be implemented efficiently in less than ten lines of Java code</a>.

In an information retrieval setting, a document signature would be computed for each document in a corpus by tokenising each document and building a Bloom filter from the extracted terms. To retrieve the documents matching a given query, the query signature (which is the union of the signatures of the query's terms) is computed. In what I will call the <em>signature scan</em> phase of the retrieval, the document signatures are iterated over; each document being included if its signature contains all the bits in the query signature. The result set will contain false positives but should also be quite small, so a cheap filter for correctness is executed after the signature scan is complete. 

While the hash function and ordering of the documents could be controlled creatively to cut down the number of signatures to be inspected for a given query, this approach is obviously inefficient, despite the appeal of low level bit-wise instructions. What happens when there are several billion documents in a corpus?

### Parallelism and Bit-Slicing

Threads and SIMD instructions could be thrown at the signature scan to speed it up, but one approach to parallelising the retrieval is to increase the number of documents represented by each processed word. If there are `n` documents with `m` bit signatures, the signature list is an `n * m` bit matrix. Its transpose, an `m * n` bit matrix, is referred to as a bit sliced signature. When querying the bit sliced signature, only the rows specified in the query need be accessed and intersected, and each word represents the presence of a term in up to 64 documents. This is a very old technique - the <a href="https://www.researchgate.net/publication/220515739_Signature_Files_An_Access_Method_for_Documents_and_Its_Analytical_Performance_Evaluation" target="_blank">the earliest formulation of a variant of this data structure I could find</a>, where it was referred to as _superimposed coding_, was published in 1984, but references implementations from the 60s. An <a href="http://www.cs.cmu.edu/~christos/PUBLICATIONS.OLDER/edbt94.pdf" target="_blank">accessible evaluation</a> was published in 1994. 

### Java Implementation

An implementation of such a structure for an immutable corpus is trivial but informative. Typically terms will be strings but needn't be, whereas documents can be reduced to a set of terms. Using `ToIntFunction` to abstract hash functions again, we just need to map all term-document tuples into the bits of a `long[][]`. When querying the structure, we need to map the query's terms into a sorted sequence of integers, determining which rows of the bit matrix to access.

On the way in, rather than using the hash functions to compute the bit to set (this is constant for each document), the row index is calculated. For each term, for each hash function, the appropriate row index is calculated and the document's bit is set in the corresponding array. Clean Java would do this outside of the constructor, of course.

```java
public class BitSlicedSignature<D extends Supplier<Set<T>>, T, Q extends Set<T>> {


    private final long[][] bitMatrix;
    private final int width;
    private final int height;
    private final List<ToIntFunction<T>> hashFunctions;

    public BitSlicedSignature(List<D> documents,
                              List<ToIntFunction<T>> hashFunctions,
                              int height) {
        this.hashFunctions = hashFunctions;
        this.width = (documents.size() + 63) / 64;
        this.height = height;
        this.bitMatrix = new long[height][width];
        int docIndex = 0;
        for (D doc : documents) {
            int docWordIndex = docIndex >> 6;
            long docWord = 1L << docIndex;
            for (T term : doc.get()) {
                for (ToIntFunction<T> hash : hashFunctions) {
                    int row = mapHash(hash.applyAsInt(term));
                    bitMatrix[row][docWordIndex] |= docWord;
                }
            }
            ++docIndex;
        }
    }

    private int mapHash(int hash) {
        return Math.abs(hash % height);
    }
}
```

To query the structure, the query is mapped into row indices and the corresponding rows are intersected word by word, matching document IDs are emitted lazily as an `IntStream`. The appeal of doing this lazily is that we should expect there to be a lot of documents, this way the bit-wise intersections can be done in chunks as and when the caller wants more documents. This can be achieved with the help of two utility methods:

```java
    public IntStream query(Q query) {
        int[] rows = query.stream()
                          .flatMapToInt(t -> hashFunctions.stream().mapToInt(h -> mapHash(h.applyAsInt(t))))
                          .distinct()
                          .toArray();
        return IntStream.range(0, width).flatMap(i -> bitsOf(intersection(rows, i), i));
    }

    private long intersection(int[] rows, int offset) {
        long word = -1L;
        for (int i = 0; i < rows.length && word != 0; ++i) {
            word &= bitMatrix[rows[i]][offset];
        }
        return word;
    }

    private static IntStream bitsOf(long word, int offset) {
        return IntStream.range(0, Long.SIZE)
                        .filter(i -> (1L << i & word) != 0)
                        .map(i -> Long.SIZE * offset + i);
    }
```

As you can probably see, you can leave vast swathes of the `long[][]` untouched, assuming the query is for a small number of terms. A more sophisticated implementation might partition the documents into several bit matrices.

### Shortcomings

There are some obvious problems with this data structure. Firstly, a `long[][]` uses the same amount of memory whether its bits are set or not. What happens when you have some small documents and lots of terms? You have a column in the bit matrix where most of the bits are zero - it's likely that a compressed bit set would be preferable. Similarly with very common terms you will have long horizontal runs of set bits.

Even worse, what happens when a term is very rare? If you are providing a search service, it's likely you only ever need to provide a page of results at a time. If the term is rare enough, you may need to scan the entire row to fill a page, which could take a long time. To get around that, BitFunnel uses bit-sliced _block signatures_, which I will write about in the next post.
