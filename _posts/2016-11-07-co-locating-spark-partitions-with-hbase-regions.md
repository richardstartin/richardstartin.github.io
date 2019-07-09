---
title: "Co-locating Spark Partitions with HBase Regions"
layout: post
date: 2016-11-07
---
HBase scans can be accelerated if they start and stop on a single region server. IO costs can be reduced further if the scan is executed on the same machine as the region server. This article is about extending the Spark RDD abstraction to load an RDD from an HBase table so each partition is co-located with a region server. This pattern could be adopted to read data into Spark from other sharded data stores, whenever there is a metadata protocol available to dictate partitioning.

The strategy involves creating a custom implementation of the Spark class RDD, which understands how to create partitions from metadata about HBase regions. To read data from HBase, we want to execute a scan on a single region server, and we want to execute on the same machine as the region to minimise IO. Therefore we need the start key, stop key, and hostname for each region associated with each Spark partition.

```java
public class HBasePartition implements Partition {

  private final String regionHostname;
  private final int partitionIndex;
  private final byte[] start;
  private final byte[] stop;

  public HBasePartition(String regionHostname, int partitionIndex, byte[] start, byte[] stop) {
    this.regionHostname = regionHostname;
    this.partitionIndex = partitionIndex;
    this.start = start;
    this.stop = stop;
  }

  public String getRegionHostname() {
    return regionHostname;
  }

  public byte[] getStart() {
    return start;
  }

  public byte[] getStop() {
    return stop;
  }

  @Override
  public int index() {
    return partitionIndex;
  }
}
```

The HBase interface RegionLocator, which can be obtained from a Connection instance, can be used to build an array of HBasePartitions. It aids efficiency to check if it is possible to skip each region entirely, if the supplied start and stop keys do not overlap with its extent.

```java
public class HBasePartitioner implements Serializable {

  public Partition[] getPartitions(byte[] table, byte[] start, byte[] stop) {
    try(RegionLocator regionLocator = ConnectionFactory.createConnection().getRegionLocator(TableName.valueOf(table))) {
      List<HRegionLocation> regionLocations = regionLocator.getAllRegionLocations();
      int regionCount = regionLocations.size();
      List<Partition> partitions = Lists.newArrayListWithExpectedSize(regionCount);
      int partition = 0;
      for(HRegionLocation regionLocation : regionLocations) {
        HRegionInfo regionInfo = regionLocation.getRegionInfo();
        byte[] regionStart = regionInfo.getStartKey();
        byte[] regionStop = regionInfo.getEndKey();
        if(!skipRegion(start, stop, regionStart, regionStop)) {
          partitions.add(new HBasePartition(regionLocation.getHostname(),
                                            partition++,
                                            max(start, regionStart),
                                            min(stop, regionStop)));
        }
      }
      return partitions.toArray(new Partition[partition]);
    }
    catch (IOException e) {
      throw new RuntimeException("Could not create HBase region partitions", e);
    }
  }

  private static boolean skipRegion(byte[] scanStart, byte[] scanStop, byte[] regionStart, byte[] regionStop) {
    // check scan starts before region stops, and that the scan stops before the region starts
    return min(scanStart, regionStop) == regionStop || max(scanStop, regionStart) == regionStart;
  }

  private static byte[] min(byte[] left, byte[] right) {
    if(left.length == 0) {
      return left;
    }
    if(right.length == 0) {
      return right;
    }
    return Bytes.compareTo(left, right) < 0 ? left : right;   }   private static byte[] max(byte[] left, byte[] right) {     if(left.length == 0) {       return right;     }     if(right.length == 0) {       return left;     }     return Bytes.compareTo(left, right) >= 0 ? left : right;
  }
}
```

Finally, we can implement an RDD specialised for executing HBasePartitions. We want to exploit the ability to choose or influence where the partition is executed, so need access to a Scala RDD method getPreferredLocations. This method is not available on JavaRDD, so we are forced to do some Scala conversions. The Scala/Java conversion work is quite tedious but necessary when accessing low level features on a Java-only project.

```java
public class HBaseRDD<T> extends RDD<T> {

  private static <T> ClassTag<T> createClassTag(Class>T> klass) {
    return scala.reflect.ClassTag$.MODULE$.apply(klass);
  }

  private final HBasePartitioner partitioner;
  private final String tableName;
  private final byte[] startKey;
  private final byte[] stopKey;
  private final Function<Result, T> mapper;

  public HBaseRDD(SparkContext sparkContext,
                  Class<T> klass,
                  HBasePartitioner partitioner,
                  String tableName,
                  byte[] startKey,
                  byte[] stopKey,
                  Function<Result, T> mapper) {
    super(new EmptyRDD<>(sparkContext, createClassTag(klass)), createClassTag(klass));
    this.partitioner = partitioner;
    this.tableName = tableName;
    this.startKey = startKey;
    this.stopKey = stopKey;
    this.mapper = mapper;
  }

  @Override
  public Iterator<T> compute(Partition split, TaskContext context) {
    HBasePartition partition = (HBasePartition)split;
    try(Connection connection = ConnectionFactory.createConnection()) {
      Scan scan = new Scan()
                      .setStartRow(partition.getStart())
                      .setStopRow(partition.getStop())
                      .setCacheBlocks(false);
      Table table = connection.getTable(TableName.valueOf(tableName));
      ResultScanner scanner = table.getScanner(scan);
      return JavaConversions.asScalaIterator(
              StreamSupport.stream(scanner.spliterator(), false).map(mapper).iterator()
      );
    }
    catch (IOException e) {
      throw new RuntimeException("Region scan failed", e);
    }
  }

  @Override
  public Seq<String> getPreferredLocations(Partition split) {
    Set<String> locations = ImmutableSet.of(((HBasePartition)split).getRegionHostname());
    return JavaConversions.asScalaSet(locations).toSeq();
  }

  @Override
  public Partition[] getPartitions() {
    return partitioner.getPartitions(Bytes.toBytes(tableName), startKey, stopKey);
  }
}
```

As far as the interface of this class is concerned, it's just normal Java, so it can be used from a more Java-centric Spark project, despite using some Scala APIs under the hood. We could achieve similar results with mapPartitions, but would have less control over partitioning and co-location.
