---
ID: 9769
post_title: Blocked Signatures
author: Richard Startin
post_excerpt: ""
layout: post
permalink: >
  http://richardstartin.uk/blocked-signatures/
published: true
post_date: 2017-09-30 20:42:34
---
The interesting thing about <a href="https://danluu.com/bitfunnel-sigir.pdf" target="_blank">BitFunnel</a>, the search architecture used by Bing, is its unorthodoxy; it revisits many ideas ignored by contemporary search technologies. The paper's references go back to the 80s, when one million records was considered an enormous database. Something about this appeals to me, that there might be long forgotten ideas waiting to be reinterpreted and recombined in the context of modern micro-architectures. 

<a href="http://richardstartin.uk/bit-sliced-signatures-and-bloom-filters/" rel="noopener" target="_blank">A bit-sliced signature arrangement</a> reduces the number of words which must be processed to evaluate a query, but it's not enough for BitFunnel's purposes. The last piece of background in the BitFunnel paper is <em>blocked signatures</em>, which are discussed in the 1990 paper <em>A signature file scheme based on multiple organizations for indexing very large text databases</em> by Kent, Sacks-Davis, Ramamohanarao (KS-DR). Blocked signatures further reduce the amount of processing per query, at what can be an acceptable false positive rate. In this post I aim to piece their data structure together in modern Java.

<h3>Formulation</h3>

The goal is to map documents into blocks consisting of a fixed number of documents (referred to as the <em>blocking factor</em> in the BitFunnel paper) so only bit sliced block signatures need be stored, where a block signature is a bloom filter of the terms in a block of documents. There are a variety of ways of doing this but they all start with assigning an integer label to each document prior to block assignment. This topic is covered at length in KS-DR.

The most obvious technique is to assign contiguous ranges of document IDs to blocks of size <code language="java">N</code>, that is the function <code language="java">i -> Math.floorDiv(i, N)</code>. This is only useful if blocks of document signatures are also stored, acting as a top level index into those document signatures. Physically, there is a block index, which is the bit sliced signature of the terms in each block, and separate blocks of document signatures, again bit sliced by term. Queries can be evaluated by constructing a bloom filter from the query's terms, specifying a set of bit slices in the block index to inspect and intersect. The result of the intersection gives the IDs of the document signature blocks to query. This is like a two level tree, and is better than a signature scan over all the document signatures, but why not just bit slice the document signatures? For rare terms, once a block is located, it does cut down the number of words in each slice to be intersected. However, the real problem with this technique, besides storage, is the cost of a false match at the block level: it results in a document level query, touching <code language="java">N</code> bits, but yields nothing. The BitFunnel blocked signatures generalise this two level hierarchical arrangement for multiple levels.

This post goes on a tangent from BitFunnel here, focusing on the ideas put forward in KS-DR. An alternative is to choose a number <code language="java">M > N</code> <a href="http://mathworld.wolfram.com/RelativelyPrime.html" rel="noopener" target="_blank">coprime</a> to <code language="java">C</code>, an estimate of the capacity of the index, and use the function <code language="java">i -> Math.floorDiv(M * i % C, N)</code> to permute records prior to blocking, then make a copy of the block index for each of several values of <code language="java">M</code>. If you choose, say, two values of <code language="java">M</code>, when evaluating queries, you can map the query terms and get the matching blocks from each representation as before. There is no need for a document level query or storage though. If you have a bitmap of the document IDs (not the signatures) for each block, you can intersect the document bitmaps to get the document IDs matching the query (with false positives, the number of which reduces with the number of copies). In the KS-DR paper, this bitmap I assume the existence of is actually computed on the fly via an expensive reverse mapping with the help of a lookup table.

<h3>Java Implementation</h3>

The code is very similar to the bit sliced signature code, because a significant part of querying is a bit sliced lookup of block IDs, which requires storage of a bit matrix. The major difference is the requirement for block assignment and ultimately block intersection. I encapsulate this in a <code language="java">BlockSet</code> which contains <code language="java">Block</code>s and is responsible for block assignment and intersection.

Details of block creation (blocking factor, bit matrix dimensions, hashing policy) can be hidden behind a supplier interface.

<code class="language-java">
public class BlockFactory<D extends Supplier<Set<T>> & IntSupplier, T, Q extends Set<T>> implements Supplier<Block<D, T, Q>> {

    private final List<ToIntFunction<T>> hashes;
    private final int blockingFactor;
    private final int blockCapacity;

    public BlockFactory(List<ToIntFunction<T>> hashes, int blockingFactor, int blockCapacity) {
        this.hashes = hashes;
        this.blockingFactor = blockingFactor;
        this.blockCapacity = blockCapacity;
    }

    @Override
    public Block<D, T, Q> get() {
        return new Block<>(blockingFactor, blockCapacity, hashes);
    }
}
</code>

This gives us blocks, which is really just a wrapper around a bit matrix of terms and a bit set of document IDs. It can do three things
<ol>
<li>Index a document, this requires that it knows the blocking factor (the number of blocks it can index), the hash functions and the bloom filter size.</li>
<li>Check if the block might contain at least one document matching all the terms</li>
<li>Share its document IDs</li>
</ol>

The code looks quite similar to my previous bit sliced signature implementation.

<code class="language-java">
public class Block<D extends Supplier<Set<T>> & IntSupplier, T, Q extends Set<T>> {

    private final BitSet documentIds;
    private final long[][] bitMatrix;
    private final int capacity;
    private final List<ToIntFunction<T>> hashFunctions;
    private int docIndex = 0;

    public Block(int blockingFactor, int capacity, List<ToIntFunction<T>> hashFunctions) {
        assert Integer.bitCount(capacity) == 1;
        this.documentIds = new BitSet();
        this.bitMatrix = new long[capacity >> 6][blockingFactor];
        this.capacity = capacity;
        this.hashFunctions = hashFunctions;
    }

    public void add(D doc) {
        int docIndex = this.docIndex++;
        int docWordIndex = docIndex >>> 6;
        long docWord = 1L << docIndex;
        mapTerms(doc.get()).forEach(r -> bitMatrix[r][docWordIndex] |= docWord);
        documentIds.set(doc.getAsInt());
    }

    public void contribute(BitSet result) {
        result.or(documentIds);
    }

    public boolean matches(Q query) {
        int[] rows = mapTerms(query).distinct().toArray();
        return IntStream.range(0, capacity >> 6)
                        .filter(i -> hasMatch(rows, i))
                        .findFirst()
                        .isPresent();
    }

    private boolean hasMatch(int[] rows, int offset) {
        long word = 0L;
        for (int i = 0; i < rows.length && word == 0; ++i) {
            word |= bitMatrix[rows[i]][offset];
        }
        return word != 0;
    }

    private IntStream mapTerms(Set<T> terms) {
        return terms.stream().flatMapToInt(t -> hashFunctions.stream().mapToInt(f -> mapHash(f.applyAsInt(t))));
    }

    private int mapHash(int hash) {
        return hash & -hash & (capacity - 1);
    }
}
</code>

Now a level up. A <code language="java">BlockIndex</code> has a <code language="java">BlockSet</code> for each relatively prime factor. When evaluating a query, it passes the query to each of its <code language="java">BlockSet</code>s, retrieving all blocks which probably match the query. 

<code class="language-java">
public class BlockSet<D extends Supplier<Set<T>> & IntSupplier, T, Q extends Set<T>> {

    private final Block[] blocks;
    private final Supplier<Block<D, T, Q>> newBlock;
    private final int blockingFactor;
    private final int estimatedCapacity;
    private final int prime;

    public BlockSet(Supplier<Block<D, T, Q>> newBlock, int blockingFactor, int estimatedCapacity, int prime) {
        assert Integer.bitCount(blockingFactor) == 1 && Integer.bitCount(estimatedCapacity) == 1;
        this.newBlock = newBlock;
        this.blocks = new Block[estimatedCapacity/blockingFactor];
        for (int i = 0; i < blocks.length; ++i) {
            blocks[i] = newBlock.get();
        }
        this.blockingFactor = blockingFactor;
        this.estimatedCapacity = estimatedCapacity;
        this.prime = prime;
    }

    public void add(D doc) {
        int blockIndex = blockIndex(doc.getAsInt());
        Block<D, T, Q> block = (Block<D, T, Q>)blocks[blockIndex];
        block.add(doc);
    }

    public BitSet query(Q query) {
        BitSet result = new BitSet();
        Arrays.stream(blocks)
              .filter(b -> b.matches(query))
              .forEach(b -> b.contribute(result));
        return result;
    }

    private int blockIndex(int value) {
        return ((value * prime) & (estimatedCapacity - 1)) / blockingFactor;
    }
}
</code>

With a <code language="java">BlockIndex</code> as the tip of an iceberg - it just needs to intersect the bit sets of document IDs.

<code class="language-java">
public class BlockIndex<D extends Supplier<Set<T>> & IntSupplier, T, Q extends Set<T>> {

    private final List<BlockSet<D, T, Q>> blockSets;

    public BlockIndex(List<BlockSet<D, T, Q>> blockSets) {
        this.blockSets = blockSets;
    }

    public IntStream query(Q query) {
        BitSet result = null;
        for (BlockSet<D, T, Q> blockSet : blockSets) {
            BitSet docIds = blockSet.query(query);
            if (null == result) {
                result = docIds;
            } else {
                result.and(docIds);
            }
        }
        return null == result ? IntStream.of() : result.stream();
    }
}
</code>

This code is obviously experimental, but a problem with it as it stands is memory consumption with the temporary bit sets. A better, but less Java 8+ compliant bit set is <a href="http://richardstartin.uk/a-quick-look-at-roaringbitmap/" rel="noopener" target="_blank">RoaringBitmap</a>.

<h3>Blocked Signatures in BitFunnel</h3>

Blocked Signatures are a very old idea, naturally it is reported that there are a few innovations in the BitFunnel data structure. BitFunnel uses multiple levels with blocking factors, each of which must be a proper power of 2, rather than multiple factors coprime to estimated capacity at the same level. Each level has <code language="java">rank = log(blockingFactor)</code>. The effect in BitFunnel is having several levels of blocking density. Blocks from different levels can be intersected efficiently by transforming dense blocks to rank zero (the least dense representation) prior to intersection.