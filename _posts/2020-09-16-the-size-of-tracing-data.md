---
title: The Size of Tracing Data
layout: post
tags: tracing
date: 2020-09-16
image: /assets/2020/09/06/the-size-of-tracing-data/histo.png
---

Tracing is an invaluable technique for capturing data about rare events.
Based on a heuristic that you as the application developer likely knows best, you wrap interesting sections of code with the following:

```java
long start = System.nanoTime();
doStuff();
long duration = System.nanoTime() - start;
report(TIMER_NAME, duration);
``` 

Wrapping a contended lock in this fashion can be especially revealing.
The majority of the data captured will be garbage, but this will capture outliers in a way a profiler won't.
Imagine capturing it all, naïvely, as a stream of named durations.
Assuming a zero overhead storage format, this will cost `8 + TIMER_NAME.length()` bytes per row.
The timer name is almost certainly representable in ASCII, so requires one byte per character, but will probably be "fully qualified" and quite long, say 50 characters.
If you record 20,000 of these per second, you will generate roughly 1.1MB/s.
You can be smarter and dictionary encode the metric names (replace them with an integer encoding) and even using a naïve 4 bytes per name gets you down to 235KB/s, but 156KB/s is the floor.
This is quite a lot of data, and it's just for one traced function.

An obvious solution is to use a histogram, which requires quantisation into time buckets, for instance [HdrHistogram](http://hdrhistogram.org/).
In practice, the majority of measurements will fall into relatively few time buckets, and at some point there will be no more allocation at all, except for the occasional snapshot of the histogram.
It's possible to use fewer bits for the boring measurements than for the outliers.
In the usual case, the buckets covering commonly observed values sharing integer prefixes, with very low counts in buckets containing extreme values.
This allows for prefix compression - for instance see the [packed variant of HdrHistogram](https://github.com/HdrHistogram/HdrHistogram/blob/master/src/main/java/org/HdrHistogram/PackedConcurrentHistogram.java). 
[DDSketches](https://github.com/DataDog/sketches-java/blob/master/src/main/java/com/datadoghq/sketch/ddsketch/DDSketch.java) collapses common buckets and uses an interpolation function to produce approximate quantiles with low error.

To demonstrate the benefits to be reaped by exploiting properties of the data ensemble, I simulated accesses to a lock from 20000 competing requests.

```java
  private static double generatePoisson(double rate) {
    return (-1.0 / rate) * Math.log(ThreadLocalRandom.current().nextDouble());
  }

  private static double generateLogNormal(double mean, double stdDev) {
    return Math.exp(ThreadLocalRandom.current().nextGaussian() * stdDev + mean);
  }

  private static long toDuration(double rv) {
    return Math.max(0, (long) rv);
  }

  private static long[] generateDurations(int count,
                                          double frequentRate,
                                          double frequentMean,
                                          double frequentStdDev,
                                          double infrequentRate,
                                          double infrequentMean,
                                          double infrequentStdDev) {
    long[] durations = new long[count];
    double nextFrequent = generatePoisson(frequentRate);
    double nextInfrequent = generatePoisson(infrequentRate);
    int counter = 0;
    while (counter < durations.length) {
      double rv;
      if (nextFrequent < nextInfrequent) {
        rv = generateLogNormal(frequentMean, frequentStdDev);
        nextFrequent += generatePoisson(frequentRate);
      } else {
        rv = generateLogNormal(infrequentMean, infrequentStdDev);
        nextInfrequent += generatePoisson(infrequentRate);
      }
      durations[counter++] = toDuration(rv);
    }
    return durations;
  }
```

The lock is frequently uncontended.
Uncontended accesses, which themselves have lognormally distributed durations, arrive as a poisson process with high intensity.
Contended accesses arrive less frequently as a poisson process with lower intensity, and the durations (i.e. including time waiting for the lock) have lognormal distribution with higher mean and variance.

Here is a visualisation of the distribution

![Distribution](/assets/2020/09/06/the-size-of-tracing-data/histo.png)

And the very useful print-out provided by HdrHistogram.

```
       Value     Percentile TotalCount 1/(1-Percentile)

       2.000 0.000000000000      19761           1.00
       2.000 0.100000000000      19761           1.11
       2.000 0.200000000000      19761           1.25
       2.000 0.300000000000      19761           1.43
       2.000 0.400000000000      19761           1.67
       2.000 0.500000000000      19761           2.00
       2.000 0.550000000000      19761           2.22
       2.000 0.600000000000      19761           2.50
       2.000 0.650000000000      19761           2.86
       2.000 0.700000000000      19761           3.33
       2.000 0.750000000000      19761           4.00
       2.000 0.775000000000      19761           4.44
       2.000 0.800000000000      19761           5.00
       2.000 0.825000000000      19761           5.71
       2.000 0.850000000000      19761           6.67
       2.000 0.875000000000      19761           8.00
       2.000 0.887500000000      19761           8.89
       2.000 0.900000000000      19761          10.00
       2.000 0.912500000000      19761          11.43
       2.000 0.925000000000      19761          13.33
       2.000 0.937500000000      19761          16.00
       2.000 0.943750000000      19761          17.78
       2.000 0.950000000000      19761          20.00
       2.000 0.956250000000      19761          22.86
       2.000 0.962500000000      19761          26.67
       2.000 0.968750000000      19761          32.00
       2.000 0.971875000000      19761          35.56
       2.000 0.975000000000      19761          40.00
       2.000 0.978125000000      19761          45.71
       2.000 0.981250000000      19761          53.33
       2.000 0.984375000000      19761          64.00
       2.000 0.985937500000      19761          71.11
       2.000 0.987500000000      19761          80.00
   10495.000 0.989062500000      19782          91.43
   15711.000 0.990625000000      19813         106.67
   19055.000 0.992187500000      19844         128.00
   21631.000 0.992968750000      19860         142.22
   23087.000 0.993750000000      19875         160.00
   25231.000 0.994531250000      19891         182.86
   26431.000 0.995312500000      19907         213.33
   28399.000 0.996093750000      19922         256.00
   30111.000 0.996484375000      19930         284.44
   31407.000 0.996875000000      19938         320.00
   33407.000 0.997265625000      19946         365.71
   35743.000 0.997656250000      19954         426.67
   36895.000 0.998046875000      19961         512.00
   37663.000 0.998242187500      19965         568.89
   40095.000 0.998437500000      19969         640.00
   40863.000 0.998632812500      19973         731.43
   45087.000 0.998828125000      19977         853.33
   48351.000 0.999023437500      19981        1024.00
   48895.000 0.999121093750      19983        1137.78
   49247.000 0.999218750000      19985        1280.00
   50239.000 0.999316406250      19987        1462.86
   51519.000 0.999414062500      19989        1706.67
   53407.000 0.999511718750      19991        2048.00
   53599.000 0.999560546875      19992        2275.56
   57087.000 0.999609375000      19993        2560.00
   58911.000 0.999658203125      19994        2925.71
   59071.000 0.999707031250      19995        3413.33
   60767.000 0.999755859375      19996        4096.00
   60767.000 0.999780273438      19996        4551.11
   66815.000 0.999804687500      19997        5120.00
   66815.000 0.999829101563      19997        5851.43
   66879.000 0.999853515625      19998        6826.67
   66879.000 0.999877929688      19998        8192.00
   66879.000 0.999890136719      19998        9102.22
   67583.000 0.999902343750      19999       10240.00
   67583.000 0.999914550781      19999       11702.86
   67583.000 0.999926757813      19999       13653.33
   67583.000 0.999938964844      19999       16384.00
   67583.000 0.999945068359      19999       18204.44
   68095.000 0.999951171875      20000       20480.00
   68095.000 1.000000000000      20000
```


```java
    long[] durations = generateDurations(20000, 0.9, 1.0, 0.01, 0.01, 10.0, 0.5);

    DDSketch denseDDSketch = DDSketch.fast(0.001);
    DDSketch sparseDDSketch = DDSketch.memoryOptimal(0.001);
    PackedHistogram packedHistogram = new PackedHistogram(30 * 1000_000_000L, 3);
    Histogram histogram = new Histogram(30 * 1000_000_000L, 3);

    for (long duration : durations) {
      denseDDSketch.accept(duration);
      sparseDDSketch.accept(duration);
      packedHistogram.recordValue(duration);
      histogram.recordValue(duration);
    }
```

To evaluate the true cost of this data, you need to serialize it, and whilst HdrHistogram supports this, DDSketch doesn't (yet?), so I compared the in memory footprints using JOL as a comparable proxy.
DDSketch's Java implementation is still in its early days and isn't optimal (the sparse implementation is backed by a `NavigableMap<Integer, Long>`...), but it still does a lot better than the naïve array of durations.
The sizes below ignore any labeling/names.


| Storage                   |    Total Size (KB) |
|---------------------------|--------------------|
| HdrHistogram (dense)      |     209            |
| Array                     |     156            |
| DDSketch (dense)          |     61             |
| DDSketch (sparse)         |     41             |
| HdrHistogram (sparse)     |     3              |

There is no such thing as a free lunch: histograms lose information about when the events occurred.
If you want to change the tracing function to record the start time as follows

```java
long epochStart = MILLISECONDS.toNanos(System.currentTimeMillis());
long epochStartNanoTime = System.nanoTime();
...
long start = System.nanoTime();
doStuff();
long duration = System.nanoTime() - start;
report(TIMER_NAME, (start - epochStartNanoTime), duration);
``` 

Then histograms are no longer an option, but it doesn't need to take 268KB, and ensemble properties can be exploited to reduce the size.
First of all, the timestamps are monotonic, and can be represented by offsets relative to the start of an epoch.
Then, these offsets are themselves monotonic.
Further, if we can guarantee the epochs are shorter than 46 days, the offsets need at most 32 bits, and can be cast to `int`  
Over 99% of the durations were uncontended accesses, and are virtually the same value, then there's less than 1% long durations.
Even the long durations don't need 64 bits each, and can be safely cast to `int`.

[JavaFastPFOR](https://github.com/lemire/JavaFastPFor) is capable of exploiting these patterns so you can capture all the data without it getting too big.


```java
    int[][] durationsWithStartTimes = generateDurationsWithStartTimes(20000, 0.9, 1.0, 0.01, 0.01, 10.0, 0.5);
    IntegratedIntCompressor compressor = new IntegratedIntCompressor();
    int[] compressedDurations = compressor.compress(durationsWithStartTimes[0]);
    int[] compressedStartTimes = compressor.compress(durationsWithStartTimes[1]);
```

This is cheating in the kind of way you can cheat when you're close to the problem.
If you're tracing lock accesses, it's perfectly reasonable to assume everything takes less than 4 billion nanoseconds.
For the naïve baseline, we can employ the same trick for the durations, but without a frame of reference, 64 bits are required for each of the timestamps.
To record a second's worth of data at 20K requests per second, the space required is


|   Storage                       |    Total Size (KB)     |
|---------------------------------|------------------------|
| long durations, long timestamps |    312                 |
| int durations, long timestamps  |    274                 |
| FastPFOR                        |    56                  |

Having a frame of reference just makes such a difference to this kind of data.

Next time, we'll take a look at the spatial overhead imposed by the open tracing standard opentelemetry!



  


