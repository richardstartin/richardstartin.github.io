---
title: Don't use Protobuf for Telemetry
layout: post
tags: tracing
date: 2020-12-29
---

Protobuf needs no introduction, but this post argues that you shouldn't use it for telemetry.
The basic premise of this post is that a good telemetry library needs to be lightweight to avoid perturbing the application; inefficient diagnostics is self-defeating.
The post doesn't argue to never use Protobuf, but that the trade-off made by the _wire-format_ itself, as opposed to any existing implementation, are unlikely to work for lightweight message senders.

## Protobuf-java is a little heavy 

A few months ago I needed to become familiar with the Protobuf wire-format for a proof of concept.
The motivation for digging in to the wire-format, rather than just using `protobuf-java`, was the dimensions of the library, which I would need to bundle in an agent:

```shell script
$ stat -c %s protobuf-java-3.14.0.jar
1672950

$ jar -tf protobuf-java-3.14.0.jar | grep '.class' | wc -l
669
```

Just depending on the library adds 1.6MB and nearly 700 classes before you even generate your own message classes.
Since the deployment in question was an agent which can't assume the presence of Protobuf at runtime, there is no way to avoid bundling the extra 1.6MB.
Since the aforementioned agent implements _ClassLoader isolation_ to avoid interfering with application class loading, even if `protobuf-java` _is_ present at runtime, the classes would need to be loaded again by an isolated `ClassLoader`, which consumes metaspace unnecessarily.

A tracer only needs to _produce_ messages, so not all of those 669 classes (which doesn't include your own generated classes) will get loaded, but a lot of them do.
Having since implemented library-neutral Protobuf serialisation in DataDog's [sketches-java](https://github.com/DataDog/sketches-java), I have a reasonable [point of comparison](https://github.com/DataDog/sketches-java/blob/master/src/jmh/java/com/datadoghq/sketch/ddsketch/benchmarks/Serialize.java) to show how many classes get loaded in a write-only context:

```java
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@BenchmarkMode(Mode.AverageTime)
public class Serialize extends BuiltSketchState {

  @Benchmark
  public byte[] serialize() {
    return sketch.serialize().array();
  }

  @Benchmark
  public byte[] toProto() {
    return DDSketchProtoBinding.toProto(sketch).toByteArray();
  }
}
```

Each method produces identical bytes, and the purpose of the benchmark above is to compare speeds.
For the record, the hand-written method `serialize` above is roughly 10x faster than using `protobuf-java`, but it's not the point of this post. 
By running the benchmark for a single warmup iteration each, with the argument `-jvmArgumentsPrepend: -verbose:class`, the classes which are loaded are logged, which I captured in separate files.
276 more classes are loaded when using `protobuf-java`:

```shell script
$ wc -l serialize.log 
1400 serialize.log
$ wc -l to_proto.log 
1676 to_proto.log
```

If you work at a large organisation which has entirely embraced Protobuf, I would not suggest worrying about 1.6MB or a few hundred loaded classes; these costs quickly amortise as you use the library for more features.
However, your resource budget for a diagnostic agent which tells you what your application is doing and how it's performing should be tiny, and I'm not sure `protobuf-java` can be made to fit in to it, given the isolation constraints for agents outlined above.

## Length delimiters are costly to produce

This meant that I needed to implement my own (which is a lot easier than it sounds if you haven't done this sort of thing before) so I had to read the only documentation there is on [encoding](https://developers.google.com/protocol-buffers/docs/encoding), which is frustratingly incomplete.
I couldn't get the formatter I had written based on my first reading of this document to produce valid protobuf because I had skim-read the section on embedded messages, and because it includes a design decision that would never have occurred to me.
When I went back and read it again I was surprised to find that embedded messages are length-prefixed, but the length prefix is varint encoded, which means you don't know how many bytes you need for the length until you've done the serialisation, and it's recursive.

Length prefixes aren't unusual in binary formats: BSON documents are prefixed by the size in bytes, meaning sub-documents need to be serialised recursively before their lengths can be written.
BSON makes this easy by not compressing the document length so you just leave 4 bytes for the length and come back and fill it in when popping document contexts ([it can add up to a significant portion of your database though](https://richardstartin.github.io/posts/shrinking-bson-documents)).
Msgpack, for example, _does_ apply prefix compression of embedded element lengths (e.g. maps and arrays) but the length is a count of the elements, not the number of serialised bytes, which makes streaming serialisation a lot easier.  
Protobuf does both, and, consequentially, there's no way to make producing nested Protobuf messages particularly efficient.
I abandoned the proof of concept when I found that a streaming zero-allocation msgpack codec I had written was around 6x faster than either `protobuf-java` or a handwritten Protobuf codec for messages with nesting.
Since I couldn't remove the nesting in the messages I needed to produce, I blamed the wire-format and moved on.    

People who actually know Protobuf already know this (it's literally written in the encoding manual), and understand the benefit to readers dual to this cost (e.g. implementing partial deserialisation is easy, easy to skip over sections of the message), but lots of people don't seem to understand the cost model the wire-format imposes.
If they did, there would probably be a lot less nesting in Protobuf as used in the wild.

This more or less concludes my argument against using Protobuf for telemetry: if you find for yourself that producing Protobuf messages is costly, it's not even a case of a third party library making the wrong trade-offs for your application; it's the wire-format itself at fault.
If you want to ship telemetry data out of an application and aim to minimise the impact on the application, even if you implement your own zero-allocation, micro-optimised, codec, you shouldn't choose Protobuf.

This is a good opportunity to segue into describing the wire-format for Protobuf 3, filling in a couple of the gaps in [Google's encoding document](https://developers.google.com/protocol-buffers/docs/encoding), but read the official document if you want to write your own.

## Notes on the wire format

Protobuf's wire format is really simple: it's just a list of tagged key-value pairs. 
Since readers have a schema to refer to, ambiguity is permissible and advantageous.
The logical structure of a Protobuf message is as below, with each tag followed by some bytes associated with the tag.

```
tag1:value1, tag3:value2, tag2:value3, ...
```

Here is a pseudo-Backus-Naur form of the wire format.

```
body 	         ::= 	tagged_value*
tagged_value     ::=    tag value
tag              ::=    varint((field_number << 3) | wire_type)
wire_type        ::=    VARINT | FIXED_64 | GROUP_BEGIN | GROUP_END | FIXED_32
VARINT           ::=    0
FIXED_64         ::=    1
LENGTH_DELIMITED ::=    2
GROUP_BEGIN      ::=    3 (deprecated)
GROUP_END        ::=    4 (deprecated)
FIXED_32         ::=    5
value            ::=    varint | double | length_delimited | float
length_delimited ::=    varint(N) byte{N}
```

Each data item has a tag, which contains the field number (as defined in the .proto file) and one of the four wire types still in use in Protobuf 3.
The tag is constructed by shifting the field number left by three bits and combining with the wire type, and then _varint-encoded_ so it takes up less space.
Since there are only three bits for the wire type, there can only ever be eight wire types, and two have already been wasted on group begin and end markers (I don't know the story behind these).
Given that `FIXED_32=5` with only two possible wire types left, I imagine that there were some tense meetings before deciding to add it. 

The terminology above is my own, but notice that there are no terms like `repeated`, `oneof`, or `message`.
This is because they don't exist at this level. 
`message` is just a length delimiter followed by some more protobuf, preceded by a `LENGTH_DELIMITED` tag; the schema has the necessary information to read the raw bytes.
`repeated` fields come in two kinds: packed and not packed. 
Packed `repeated` fields are indistinguishable from a `message` or a `string` on the wire.
`repeated` fields which aren't packed are a list of tag-values with the same field number and the element type in each tag, and they don't need to be contiguous within the message.
Incidentally, writers aren't obliged not to repeat non-`repeated` fields, and as there is nothing to distinguish these fields over the wire, readers are obliged to take the _last value_ for a non-`repeated` field (which makes some of the partial deserialisers I've seen illegal).

`FIXED_32` and `FIXED_64` are just IEEE floating point numbers, but all integers, which includes booleans, are _varint_ encoded, which has the basic effect of removing leading zeros in order to save space.
Starting with the least significant bits, seven bits are taken at a time from the integer until no bits remain, and all but the last byte have their most significant bit set.
This allows the parser to detect the end of an integer by looking for a byte with the MSB unset. 
Whilst this saves space, it makes reserving space for lengths not yet known problematic.

> `map<T, U>` can be encoded as if it were a `repeated message` with the key of proto type `T` in field position 1, and the value of proto type `U` in field position 2.
>  That is, for each entry in the map, a tag with the field number `x` of the map field and `LENGTH_DELIMITED` wire type, followed by the same protobuf as would be generated from: 
>```
>message {
>  T key = 1;
>  U value = 2;
>}
>``` 

## Aside on Varints 

Varints are probably the most interesting thing about Protobuf, and I stumbled upon some simple tricks to produce more efficiently than is done in other Java libraries I looked at.
This is what it looks like in `protobuf-java`'s `CodedOutputStream` (see [source](https://github.com/protocolbuffers/protobuf/blob/5b232b8ecbce13286be09e703997e887ae0d464d/java/core/src/main/java/com/google/protobuf/CodedOutputStream.java#L1397-L1424))

```java
    @Override
    public final void writeUInt64NoTag(long value) throws IOException {
      if (HAS_UNSAFE_ARRAY_OPERATIONS && spaceLeft() >= MAX_VARINT_SIZE) {
        while (true) {
          if ((value & ~0x7FL) == 0) {
            UnsafeUtil.putByte(buffer, position++, (byte) value);
            return;
          } else {
            UnsafeUtil.putByte(buffer, position++, (byte) (((int) value & 0x7F) | 0x80));
            value >>>= 7;
          }
        }
      } else {
        try {
          while (true) {
            if ((value & ~0x7FL) == 0) {
              buffer[position++] = (byte) value;
              return;
            } else {
              buffer[position++] = (byte) (((int) value & 0x7F) | 0x80);
              value >>>= 7;
            }
          }
        } catch (IndexOutOfBoundsException e) {
          throw new OutOfSpaceException(
              String.format("Pos: %d, limit: %d, len: %d", position, limit, 1), e);
        }
      }
    }
``` 

Ignoring all of the boilerplate to do with detecting whether `Unsafe` is available, this reduces to a loop with a data dependency:

```java
    while (true) {
        if ((value & ~0x7FL) == 0) {
          buffer[position++] = (byte) value;
          return;
        } else {
          buffer[position++] = (byte) (((int) value & 0x7F) | 0x80);
          value >>>= 7;
        }
      }
``` 

Data dependencies are generally bad in CPU bound loops, such as if you have a reasonably large packed array of some integer type, perhaps if you are encoding some kind of histogram.  
You can actually write this much more efficiently without using `Unsafe` by turning this in to a counted loop, which you can do by computing the number of leading zeros and dividing by 7:

```java
    int varIntLength(long value) {
      return (63 - Long.numberOfLeadingZeros(value)) / 7;
    }
```

`Long.numberOfLeadingZeros` is a HotSpot intrinsic which is compiled to a single instruction - `lzcnt` on x86 and `clz` on ARM - which is really fast.
Happily, negative proper fractions round to zero.
Integer divisions are really expensive, but the JIT compiler won't actually emit a divide instruction for this code.
Even so, this can be sped up a little more by precomputing the lengths and just looking them up.

```java
    private static final int[] VAR_INT_LENGTHS = new int[65];

    static {
        for (int i = 0; i <= 64; ++i) {
            VAR_INT_LENGTHS[i] = (63 - i) / 7;
        }
    }

    int varIntLength(long value) {
        return VAR_INT_LENGTHS[Long.numberOfLeadingZeros(value)];
    }
```

This leads to a simple counted loop, which leads to better code generation:

```java
    private void writeVarInt(int offset, long value) {
        int length = varIntLength(value);
        for (int i = 0; i < length; ++i) {
            buffer[offset + i] = ((byte) ((value & 0x7F) | 0x80));
            value >>>= 7;
        }
        buffer[offset + i] = (byte) value;
    }
```

I found that this performs similarly for short varints (tags are typically very short varints, so it's an important case to consider), but for larger numbers the counted loop performs much better. 

## Recommendations

Protobuf's strength lies in its interface definition language, which makes communication between components owned by different teams easy, but it wasn't designed for performance.
The generated Java code is generally OK, if a little bloated, and you'll probably find it allocates a lot, but it has to, because of the wire format.
If you have a low latency or low overhead use case, Protobuf may not be the right choice.
If the ability to declare interfaces and generate compliant services and clients trumps performance, you can improve performance by removing any nesting you don't need.
I really don't think Protobuf is the right choice for telemetry because perfect telemetry would have no overhead whatsoever, which is impossible, but, ultimately, every cycle used or byte allocated is stolen from the host application.    







