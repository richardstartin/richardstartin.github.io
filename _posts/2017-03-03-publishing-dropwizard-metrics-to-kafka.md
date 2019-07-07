---
title: "Publishing Dropwizard Metrics to Kafka"
layout: post
theme: jekyll-theme-slate
date: 2017-03-03
---

This post is about combining [Dropwizard metrics](http://metrics.dropwizard.io) with [Kafka](https://kafka.apache.org) to create self instrumenting applications producing durable streams of application metrics, which can be processed (and re-processed) in many ways. The solution is appealing because Kafka is increasingly popular, and therefore likely to be available infrastructure, and Dropwizard metrics likewise, being leveraged by many open source frameworks with many plugins for common measurements such as [JVM](http://metrics.dropwizard.io/3.2.0/manual/jvm.html) and [web applications](http://metrics.dropwizard.io/3.2.0/manual/servlet.html) metrics.

#### DropWizard

Dropwizard metrics allows you to create application metrics as an aspect of your application quickly. An application instrumented  with Dropwizard consists of a [`MetricRegistry`](http://metrics.dropwizard.io/3.1.0/apidocs/com/codahale/metrics/MetricRegistry.html) - basically an in memory key-value store of the state of named metrics - and one or more Reporters. There are several built in reporters including [`ConsoleReporter`](http://metrics.dropwizard.io/3.1.0/apidocs/com/codahale/metrics/ConsoleReporter.html), [`CsvReporter`](http://metrics.dropwizard.io/3.1.0/apidocs/com/codahale/metrics/CsvReporter.html), [`GangliaReport`](http://metrics.dropwizard.io/3.1.0/apidocs/com/codahale/metrics/ganglia/GangliaReporter.html) and [`GraphiteReporter`](http://metrics.dropwizard.io/3.1.0/apidocs/com/codahale/metrics/graphite/GraphiteReporter.html) (the Ganglia and Graphite reporters require that you are actually running these services). An unofficial reporter designed for Ambari Metrics is hosted [here](https://github.com/joshelser/dropwizard-hadoop-metrics2).  Nobody really wants to work with JMX anymore, but, just in case you're working with prehistoric code, there _is_ also a [`JmxReporter`](http://metrics.dropwizard.io/3.1.0/apidocs/com/codahale/metrics/JmxReporter.html) available out of the box. Reporters are very loosely coupled with instrumentation cut points throughout your code, so it's very easy to change a reporting strategy. Instrumenting an application manually is extremely simple - you just can't go wrong following the [getting started page](http://metrics.dropwizard.io/3.2.0/getting-started.html) - and there are several annotation based mechanisms for instrumenting methods; for instance there are numerous integrations to be found on Github for frameworks like Spring. Indeed, I wrote my own annotation binding using Guice type listeners on a recent project, which was certainly easy enough (using techniques in this post on [type listeners](https://richardstartin.github.io/posts/advanced-aop-with-guice-typelisteners)).

#### Kafka

The only work that needs to be done is to extend the Reporter mechanism to use Kafka as a destination. Despite being fast, the real beauty of writing metrics to Kafka is that you can do what you want with them afterwards. If you want to replicate them real time onto ZeroMQ topics, you can do that just as easily as you can run Spark Streaming or a scheduled Spark Batch job over your application metrics. If you're building your own monitoring dashboard, you could imagine having a real time latest value, along with hourly or daily aggregations. In fact you can process the metrics at whatever frequency you wish within Kafka's retention period. I truly believe your application metrics belong<em> </em>in Kafka, at least in the short term.

#### Extending ScheduledReporter

The basic idea is to extend ScheduledReporter composing a KafkaProducer. ScheduledReporter is unsurprisingly invoked repeatedly at a specified rate. On invocation, the idea is to loop through all gauges, meters, timers, and so on, serialise them (there may be a performance boost available from [CBOR](https://richardstartin.github.io/posts/concise-binary-object-representation)), and send them to Kafka via the KafkaProducer on a configurable topic. Then wherever in your application you would have created, say, an [`Slf4jReporter`](http://metrics.dropwizard.io/3.1.0/apidocs/com/codahale/metrics/Slf4jReporter.html), just create a KafkaReporter instead.

#### Code

To begin, add the following Maven coordinates to your project's pom:

```xml
        <dependency>
            <groupId>io.dropwizard.metrics</groupId>
            <artifactId>metrics-core</artifactId>
            <version>3.2.0</version>
        </dependency>
        <dependency>
             <groupId>org.apache.kafka</groupId>
             <artifactId>kafka-clients</artifactId>
             <version>0.10.2.0</version>
        </dependency>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.8.6</version>
        </dependency>
```

Whether you like them or not, all metrics reporters come with builders, so to be consistent you need to implement one. The builder needs to collect some details about Kafka so it knows where to send the metrics. The reporter is going to be responsible for creating a format in this example, but that can be factored out, in which case it would need to be exposed on the builder. In common with all reporters, there are configuration parameters relating to default units etc. which must be exposed for the sake of consistency.

```java
public static class KafkaReporterBuilder {

    private final MetricRegistry registry;
    private final KafkaProducer<String, byte[]> producer;
    private final String topic;
    private String name = "KafkaReporter";
    private TimeUnit timeUnit = TimeUnit.MILLISECONDS;
    private TimeUnit rateUnit = TimeUnit.SECONDS;
    private ObjectMapper mapper;

    public KafkaReporterBuilder(MetricRegistry registry,
                                KafkaProducer<String, byte[]> producer,
                                String topic) {
      this.registry = registry;
      this.producer = producer;
      this.topic = topic;
    }

    public KafkaReporterBuilder withName(String name) {
      this.name = name;
      return this;
    }

    public KafkaReporterBuilder withTimeUnit(TimeUnit timeUnit) {
      this.timeUnit = timeUnit;
      return this;
    }

    public KafkaReporterBuilder withRateUnit(TimeUnit rateUnit) {
      this.rateUnit = rateUnit;
      return this;
    }

    public KafkaReporterBuilder withMapper(ObjectMapper mapper) {
      this.mapper = mapper;
      return this;
    }

    public KafkaReporter build() {
      return new KafkaReporter(registry,
                               name,
                               MetricFilter.ALL,
                               rateUnit,
                               timeUnit,
                               mapper == null ? new ObjectMapper() : mapper,
                               topic,
                               producer);
    }
  }
```

Here we will use the metric name as the key of the message, this is because we need all messages of the same metric to go to the same partition to guarantee chronological order. Here we take a KafkaProducer with String keys and byte[] values - the name will be the key, the serialised metric will be the value. It's better for testability to defer the construction of the KafkaProducer to the caller, so the producer can be mocked, but KafkaProducers are really easy to construct from properties files, for instance see the [JavaDoc](https://kafka.apache.org/090/javadoc/org/apache/kafka/clients/producer/KafkaProducer.html).

The next step is to implement the reporter.

```java
public class KafkaReporter extends ScheduledReporter {

  private final KafkaProducer<String, byte[]> producer;
  private final ObjectMapper mapper;
  private final String topic;

  protected KafkaReporter(MetricRegistry registry,
                          String name,
                          MetricFilter filter,
                          TimeUnit rateUnit,
                          TimeUnit durationUnit,
                          ObjectMapper mapper,
                          String topic,
                          KafkaProducer<String, byte[]> producer) {
    super(registry, name, filter, rateUnit, durationUnit);
    this.producer = producer;
    this.mapper = mapper;
    this.topic = topic;
  }

  @Override
  public void report(SortedMap<String, Gauge> gauges,
                     SortedMap<String, Counter> counters,
                     SortedMap<String, Histogram> histograms,
                     SortedMap<String, Meter> meters,
                     SortedMap<String, Timer> timers) {
    report(gauges);
    report(counters);
    report(histograms);
    report(meters);
    report(timers);
  }

  private void report(SortedMap<String, ?> metrics) {
    metrics.entrySet()
           .stream()
           .map(kv -> toRecord(kv.getKey(), kv.getValue(), this::serialise))
           .forEach(producer::send);
  }

  private <T> ProducerRecord<String, byte[]> toRecord(String metricName, T metric, Function<T, byte[]> serialiser) {
    return new ProducerRecord<>(topic, metricName, serialiser.apply(metric));
  }

  private byte[] serialise(Object value) {
    try {
      return mapper.writeValueAsBytes(value);
    } catch(JsonProcessingException e) {
      throw new RuntimeException("Value not serialisable: " + value, e);
    }
  }
}
```

To use it to publish all application metrics to Kafka in CBOR format, once every five seconds:

```java
    MetricRegistry registry = ...
    Properties kafkaProperties = ...
    KafkaProducer<String, byte[]> producer = new KafkaProducer<>(properties);
    KafkaReporter reporter = new KafkaReporter.KafkaReporterBuilder(registry, producer, "topic")
            .withMapper(new ObjectMapper(new CBORFactory()))
            .build();
    reporter.start(5, TimeUnit.SECONDS);
    ...
    reporter.stop();
```
