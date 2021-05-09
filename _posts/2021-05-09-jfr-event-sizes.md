---
title: JFR Event Sizes
layout: post
tags: tracing
date: 2021-05-09
---

For the last few years it has been possible to write custom events to JFR files, but I didn't get around to using it until recently.
I am lucky to have colleagues who know lots about JFR's implementation details, and I have gleaned a couple of nuggets by osmosis. 
This post is about the consequences of one such detail which I can't find written down anywhere, which can help design events for smaller recording sizes.

It's mentioned in a [post](http://hirt.se/blog/?p=1239) by Marcus Hirt that integers are [LEB128 encoded](https://en.wikipedia.org/wiki/LEB128), but I can't find reference to this fact anywhere else on the first page of Google's search results.
There are two LEB128 encoding formats - signed and unsigned - and JFR uses the unsigned format, which is more commonly referred to as _varint encoding_.
Varints are really simple, and compress small positive numbers very well. 
I've written about them before [here](https://richardstartin.github.io/posts/dont-use-protobuf-for-telemetry#aside-on-varints).
This just means that depending on how you design your events, they may compress well or not so well.
How pronounced is this effect if you produce lots of events?

> This post could be reduced to "try to design JFR events for small positive numeric values where possible".  

1. TOC 
{:toc}
### Empty events

Firstly, what does an event cost, roughly, before you put any data in it?
JFR will let you create empty events.

```java
import jdk.jfr.*;

@Name("EmptyEvent")
@Label("EmptyEvent")
@Description("Empty Event")
@Category("Custom")
@StackTrace(false)
public class EmptyEvent extends Event {}
```

With the loop below in `main` (note that you should probably wrap this in `shouldCommit()` in real code)

```java
for (int i = 0; i < 100_000; ++i) {
  new EmptyEvent().commit();
}
```

I get a recording size of 1.4MB vs 0.2MB for a recording where the events aren't committed but I attempt to prevent the code from being eliminated:

```java
int x = 0;
for (int i = 0; i < 100_000; ++i) {
  x ^= System.identityHashCode(new EmptyEvent());
}
System.err.println(x);
```

This suggests each empty event is about 12 bytes.
Since running different code will change the rest of the recording, this size is probably not precise, but it seems reasonable looking at the event browser:

![Empty Events](/assets/2021/05/jfr-event-sizes/empty_events.PNG)

There is a thread name which is probably derived from the thread id (but the actual name is stored in the constant pool for the recording), a start time, a duration, and an end time probably derived from the duration and the start time.
If all of these fields are varint encoded, then a small thread id and a zero duration will need a byte each, leaving ten bytes for the start time (and anything else not visualised).

> Erik Gahlin [notes](https://twitter.com/ErikGahlin/status/1391486342220197893) that there is an event type and a size field.

Trying to increase the size of the duration field is more error prone because it takes 100 seconds to run and there is more extraneous recording activity.
Comparing recording sizes for the two loops below, I get a 2MB recording when the event is committed, and 0.47MB when it isn't, which suggests each event requires between 15 and 16 bytes. 
Since 1ms expressed in nanoseconds requires 20 bits, so the duration has 44 leading zeros, and the varint length of a number `x` can be expressed as `ceil((63 - numberOfLeadingZeros(x)) / 7)`, the durations need 4 bytes each.
This strengthens my confidence in my first guess at the structure of the events.

```java
for (int i = 0; i < 100_000; ++i) {
  EmptyEvent event = new EmptyEvent();
  event.begin();
  Thread.sleep(1);
  event.end();
  event.commit();
}

int x = 0;
for (int i = 0; i < 100_000; ++i) { 
  EmptyEvent event = new EmptyEvent();
  event.begin();
  Thread.sleep(1);
  event.end();
  x ^= System.identityHashCode(event);
}
System.err.println(x);
```

12 bytes per instantaneous event and 16 bytes for millisecond durations is really quite decent compared to some observability data representations.

### Durations or Instants?

Let's say you want to record readings from some kind of clock in JFR events - assuming you care about recording size - should you record absolute or relative measurements?
Assuming the measurements are monotonic, relative events win because they're obviously smaller values:

```java
@Name("InstantEvent")
@Label("InstantEvent")
@Description("Event with an instant")
@Category("Custom")
@StackTrace(false)
public class InstantEvent extends Event {

  @Label("Instant")
  private final long instant;

  public InstantEvent(long instant) {
    this.instant = instant;
  }
}

@Name("DurationEvent")
@Label("DurationEvent")
@Description("Event with a duration")
@Category("Custom")
@StackTrace(false)
public class DurationEvent extends Event {

  @Label("CustomDuration")
  private final long customDuration;

  public DurationEvent(long customDuration) {
    this.customDuration = customDuration;
  }
} 
``` 

You may want to record CPU time on a thread, but here I'm recording snapshots of `System.currentTimeMillis()` spaced one millisecond apart because I couldn't be bothered to contrive CPU bound work. 

```java
for (int i = 0; i < 100_000; ++i) {
  new InstantEvent(System.currentTimeMillis()).commit();
  Thread.sleep(1);
}

long last = System.currentTimeMillis();
for (int i = 0; i < 100_000; ++i) {
  long millis = System.currentTimeMillis();
  new DurationEvent(millis - last).commit();
  last = millis;
  Thread.sleep(1);
}
```

This makes a considerable difference to recording size - 2.4MB vs 1.9MB or 5 bytes per event.

### Choosing Default Values

Let's say a feature is disabled, so you don't record one of the values in your events and need a default value.
There are a few obvious choices for default values of integers - 0, `Long.MIN_VALUE`, -1, but for JFR events choosing a negative value sucks.

```java    
for (int i = 0; i < 100_000; ++i) {
  new InstantEvent(0).commit();
}
```

Produces a 1.5MB recording, but making the default value negative increases the size of the recording to 2.3MB, an increase of 8 bytes per event.
```java
for (int i = 0; i < 100_000; ++i) {
  new InstantEvent(Long.MIN_VALUE).commit();
}
``` 

### Flags

Let's say your events have various boolean attributes attached to them. 
A bitmask works better than boolean fields, and ordering flags so commonly set flags are in the low bits helps.

```java
@Name("BooleanFlagsEvent")
@Label("Boolean Flags")
@Description("Event with four boolean flags.")
@Category("Custom")
@StackTrace(false)
public class BooleanFlagsEvent extends Event {


  @Label("A")
  private final boolean isA;
  @Label("B")
  private final boolean isB;
  @Label("C")
  private final boolean isC;
  @Label("D")
  private final boolean isD;


  public BooleanFlagsEvent(boolean isA, boolean isB, boolean isC, boolean isD) {
    this.isA = isA;
    this.isB = isB;
    this.isC = isC;
    this.isD = isD;
  }
}
```

```java
@Name("BitMaskEvent")
@Label("BitMaskEvent")
@Description("Event with a bitmask.")
@Category("Custom")
@StackTrace(false)
public class BitMaskEvent2 extends Event {

  private static final int A = 2;
  private static final int B = 4;
  private static final int C = 8;
  private static final int D = 1;


  @Label("ABCD")
  int mask;

  public BitMaskEvent2(boolean isA, boolean isB, boolean isC, boolean isD) {
    this.mask = (isA ? A : 0) | (isB ? B : 0) | (isC ? C : 0) | (isD ? D : 0);
  }
}
```

Again, inferred from recording 100k events, choosing a bitmask over booleans reduces the space requirement by three bytes per event, at the cost of a loss of usability in JMC (if you are consuming the data programmatically then this is less concerning):

![Booleans](/assets/2021/05/jfr-event-sizes/booleans.PNG)
![Bitmask](/assets/2021/05/jfr-event-sizes/bitmask.PNG)

It goes without saying that putting commonly set flags in the low bits helps control size if there are more than seven flags.
  




