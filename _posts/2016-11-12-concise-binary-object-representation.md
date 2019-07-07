---
title: "Concise Binary Object Representation"
layout: post
theme: minima
date: 2016-11-12
---

Concise Binary Object Representation ([CBOR]("http://cbor.io/)) defined by [RFC 7049](https://tools.ietf.org/html/rfc7049) is a binary, typed, self describing serialisation format. In contrast with JSON, it is binary and distinguishes between different sizes of primitive type properly. In contrast with Avro and Protobuf, it is self describing and can be used without a schema. It goes without saying for all binary formats: in cases where data is overwhelmingly numeric, both parsing time and storage size are far superior to JSON. For textual data, payloads are also typically smaller with CBOR.

#### The Type Byte
The first byte of every value denotes a type. The most significant three bits denote the major type (for instance byte array, unsigned integer). The last five bits of the first byte denote a minor type (float32, int64 and so on.) This is useful for type inference and validation. For instance, if you wanted to save a BLOB into HBase and map that BLOB to a spark SQL Row, you can map the first byte of each field value to a Spark DataType. If you adopt a schema on read approach, you can validate the supplied schema against the type encoding in the CBOR encoded blobs. The major types and some interesting minor types are enumerated below but see the [definitions](https://tools.ietf.org/html/rfc7049#section-2.1) for more information.

- 0:  unsigned integers
- 1:  negative integers
- 2:  byte strings, terminated by 7_31
- 3:  UTF-8 text, terminated by 7_31
- 4:  arrays, terminated by 7_31
- 5:  maps, terminated by 7_31
- 6:  tags, (0: timestamp strings, 1: unix epoch longs, 2: big integers...)
- 7:  floating-point numbers, simple ubiquitous values (20: False, 21: True, 22: Null, 23: Undefined, 26: float, 27: double, 31: stop byte for indefinite length fields (maps, arrays etc.))
#### Usage

In Java, CBOR is supported by Jackson and can be used as if it is JSON. It is available in

```xml
<dependency>
    <groupId>com.fasterxml.jackson.dataformat</groupId>
    <artifactId>jackson-dataformat-cbor</artifactId>
    <version>2.8.4</version>
</dependency>
```

Wherever you would use an ObjectMapper to work with JSON, just use an ObjectMapper with a CBORFactory instead of the default JSONFactory.

```java
ObjectMapper mapper = new ObjectMapper(new CBORFactory());
```

Jackson integrates CBOR into JAX-RS seamlessly via

```java
<dependency>
    <groupId>com.fasterxml.jackson.jaxrs</groupId>
    <artifactId>jackson-jaxrs-cbor-provider</artifactId>
    <version>2.8.4</version>
</dependency>
```

If a JacksonCBORProvider is registered in a Jersey ResourceConfig ([a one-liner](https://richardstartin.github.io/posts/http-content-negotiation)), then any resource method annotated as `@Produces("application/cbor")`, or any HTTP request with the Accept header set to _"application/cbor"_ will automatically serialise the response as CBOR.

~~Jackson deviates from the specification slightly by promoting floats to doubles (despite parsing floats properly it post-processes them as doubles)~~, [Jackson recognises floats properly as of 2.8.6](https://github.com/FasterXML/jackson-dataformats-binary/issues/32) and distinguishes between longs and ints correctly so long as `CBORGenerator.Feature.WRITE_MINIMAL_INTS` is disabled on the writer.

In javascript, [cbor.js](https://github.com/paroga/cbor-js) can be used to deserialise CBOR, though loss of browser native support for parsing is a concern. It would be interesting to see some benchmarks for typical workloads to evaluate the balance of the cost of javascript parsing versus the benefits of reduced server side cost of generation and reduced message size. Again, for large quantities of numeric data this is more likely to be worthwhile than with text.

#### Comparison with JSON - Message Size

Textual data is slightly smaller when represented as CBOR as opposed to JSON. Given the interoperability that comes with JSON, it is unlikely to be worth using CBOR over JSON for reduced message size.

Large arrays of doubles are a lot smaller in CBOR. Interestingly, large arrays of small integers may actually be smaller as text than as binary; it takes only two bytes to represent 10 as text, whereas it takes four bytes in binary. Outside of the range of -99 to 999 this is no longer true, but might be a worthwhile economy for large quantities of survey results.

JSON and CBOR message sizes for messages containing mostly textual, mostly integral and mostly floating point data are benchmarked for message size at [github](https://github.com/richardstartin/cbor-benchmark/blob/master/src/test/java/cbor/CborMessageSize.java). The output is as follows:

```
CBOR, Integers: size=15122B
JSON, Integers: size=6132B
CBOR, Doubles: size=27122B
JSON, Doubles: size=54621B
CBOR, Text: size=88229B
JSON, Text: size=116565B
```
#### Comparison with JSON - Read/Write Performance

Using Jackson to benchmark the size of the messages is not really a concern since it implements each specification; the output and therefore size should have been the same no matter which library produced the messages. Measuring read/write performance of a specification is difficult because only the implementation can be measured. It may well be the case that either JSON or CBOR can be read and written faster by another implementation than Jackson (though I expect Jackson is probably the fastest for either format). In any case, measuring Jackson CBOR against Jackson JSON seems fair. I benchmarked JSON vs CBOR writes using the Jackson implementations of each format and JMH. The code for the benchmark is at [github](https://github.com/richardstartin/cbor-benchmark/blob/master/src/test/java/cbor/CborJsonBenchmark.java)

The results are as below. CBOR has significantly higher throughput for both read and write.

<div class="table-holder">
<table class="table table-bordered table-hover table-condensed">
<thead>
<th>Benchmark</th>
<th>Mode</th>
<th>Count</th>
<th>Score</th>
<th>Error</th>
<th>Units</th>
</thead>
<tbody>
<tr>
<td>readDoubleDataCBOR</td>
<td>thrpt</td>
<td>5</td>
<td>12.230</td>
<td>±1.490</td>
<td>ops/ms</td>
</tr>
<tr>
<td>readDoubleDataJSON</td>
<td>thrpt</td>
<td>5</td>
<td>0.913</td>
<td>±0.046</td>
<td>ops/ms</td>
</tr>
<tr>
<td>readIntDataCBOR</td>
<td>thrpt</td>
<td>5</td>
<td>16.033</td>
<td>±3.185</td>
<td>ops/ms</td>
</tr>
<tr>
<td>readIntDataJSON</td>
<td>thrpt</td>
<td>5</td>
<td>8.400</td>
<td>±1.219</td>
<td>ops/ms</td>
</tr>
<tr>
<td>readTextDataCBOR</td>
<td>thrpt</td>
<td>5</td>
<td>15.736</td>
<td>±3.729</td>
<td>ops/ms</td>
</tr>
<tr>
<td>readTextDataJSON</td>
<td>thrpt</td>
<td>5</td>
<td>1.065</td>
<td>±0.026</td>
<td>ops/ms</td>
</tr>
<tr>
<td>writeDoubleDataCBOR</td>
<td>thrpt</td>
<td>5</td>
<td>26.222</td>
<td>±0.779</td>
<td>ops/ms</td>
</tr>
<tr>
<td>writeDoubleDataJSON</td>
<td>thrpt</td>
<td>5</td>
<td>0.930</td>
<td>±0.022</td>
<td>ops/ms</td>
</tr>
<tr>
<td>writeIntDataCBOR</td>
<td>thrpt</td>
<td>5</td>
<td>31.095</td>
<td>±2.116</td>
<td>ops/ms</td>
</tr>
<tr>
<td>writeIntDataJSON</td>
<td>thrpt</td>
<td>5</td>
<td>33.512</td>
<td>±9.088</td>
<td>ops/ms</td>
</tr>
<tr>
<td>writeTextDataCBOR</td>
<td>thrpt</td>
<td>5</td>
<td>31.338</td>
<td>±4.519</td>
<td>ops/ms</td>
</tr>
<tr>
<td>writeTextDataJSON</td>
<td>thrpt</td>
<td>5</td>
<td>1.509</td>
<td>±0.245</td>
<td>ops/ms</td>
</tr>
<tr>
<td>readDoubleDataCBOR</td>
<td>avgt</td>
<td>5</td>
<td>0.078</td>
<td>±0.003</td>
<td>ms/op</td>
</tr>
<tr>
<td>readDoubleDataJSON</td>
<td>avgt</td>
<td>5</td>
<td>1.123</td>
<td>±0.108</td>
<td>ms/op</td>
</tr>
<tr>
<td>readIntDataCBOR</td>
<td>avgt</td>
<td>5</td>
<td>0.062</td>
<td>±0.008</td>
<td>ms/op</td>
</tr>
<tr>
<td>readIntDataJSON</td>
<td>avgt</td>
<td>5</td>
<td>0.113</td>
<td>±0.012</td>
<td>ms/op</td>
</tr>
<tr>
<td>readTextDataCBOR</td>
<td>avgt</td>
<td>5</td>
<td>0.058</td>
<td>±0.007</td>
<td>ms/op</td>
</tr>
<tr>
<td>readTextDataJSON</td>
<td>avgt</td>
<td>5</td>
<td>0.913</td>
<td>±0.240</td>
<td>ms/op</td>
</tr>
<tr>
<td>writeDoubleDataCBOR</td>
<td>avgt</td>
<td>5</td>
<td>0.038</td>
<td>±0.004</td>
<td>ms/op</td>
</tr>
<tr>
<td>writeDoubleDataJSON</td>
<td>avgt</td>
<td>5</td>
<td>1.100</td>
<td>±0.059</td>
<td>ms/op</td>
</tr>
<tr>
<td>writeIntDataCBOR</td>
<td>avgt</td>
<td>5</td>
<td>0.031</td>
<td>±0.002</td>
<td>ms/op</td>
</tr>
<tr>
<td>writeIntDataJSON</td>
<td>avgt</td>
<td>5</td>
<td>0.029</td>
<td>±0.004</td>
<td>ms/op</td>
</tr>
<tr>
<td>writeTextDataCBOR</td>
<td>avgt</td>
<td>5</td>
<td>0.032</td>
<td>±0.003</td>
<td>ms/op</td>
</tr>
<tr>
<td>writeTextDataJSON</td>
<td>avgt</td>
<td>5</td>
<td>0.676</td>
<td>±0.044</td>
<td>ms/op</td>
</tr>
</tbody>
</table>
</div>

The varying performance characteristics of media types/serialisation formats based on the predominant data type in a message make proper [HTTP content negotiation](https://richardstartin.github.io/posts/http-content-negotiation) important. It cannot be known in advance when writing a server application what the best content type is, and it should be left open to the client to decide.
