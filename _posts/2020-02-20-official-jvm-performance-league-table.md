---
title: The Official JVM Performance League Table 
layout: post
date: 2020-02-20
tags: java
image: /assets/2020/02/official-jvm-performance-league-table/JVMPerformance_by_handle.png
---

It occurred to me that bloggers might be motivated to improve the quality of their writing if there were some kind of KPI they could chase.
No such thing exists for blog posts, especially not those predominantly about software performance and Java, so I thought about creating one myself.
I came up with something, and I'm proud to share my methodology in this post.   

1. TOC 
{:toc}

### Methodology

As an unbiased estimator of quality, I decided to look at the tweets from the _"Official Twitter channel for JVM performance news from the #Java community"_, the Twitter account [JVMPerformance](https://twitter.com/JVMPerformance).

![Ionut Balosin](/assets/2020/02/official-jvm-performance-league-table/jvmperformance.PNG "Ionut Balosin")

Since it's _official_, I imagine it's operated by one of Oracle's employees, and is unbiased.
Perhaps I could use these tweets to rank content: really good content should show up here a lot, and bad or irrelevant content should not.

The tweets tend to include at least one URL and at least one twitter handle, so if I can extract all the tweets, group them by handle and group them by domain, then I might have myself a league table!

### Implementation

Doing this exercise was a fun but quick foray into the Twitter API.
The first thing you need to do is _apply_ for access to the API, at which point Twitter will ask you what you want to do with the data.
I explained that I wanted to create an unbiased league table of JVM performance content from tweets and they haven't revoked my access yet!
They will give you an API key and secret key, and let you generate an access token and secret. 
Keep these safe!

There is a great library called [tweepy](https://www.tweepy.org/) which is incredibly easy to use, which allows downloading things like user timelines.
See my script for generating the league table [here](https://github.com/richardstartin/tweet_aggregator/blob/master/tweets.py)!

Most of these tweets contain one handle and one link, and they simply contribute to the rankings through a group by on handle or domain.
Some links are obfuscated via _bit.ly_ (though, for some reason, only for the domain [ionutbalosin.com](https://ionutbalosin.com "Ionut Balosin")) but these can be resolved by following the redirect.
Some tweets contain no handle, these go to the "no mentions" bucket.
Similarly, some tweets contain no link;  these go to the "no link" bucket. 

### Results!

Here's the [raw data](https://github.com/richardstartin/tweet_aggregator/blob/master/JVMPerformance.csv) I extracted in CSV format!

Firstly, let's look at the distinct count by handle (number of mentions, higher is better). 
This is how many times an account has been mentioned, it adds up to more than the number of tweets: one mention, one point.

![JVMPerformance tweets by handle](/assets/2020/02/official-jvm-performance-league-table/JVMPerformance_by_handle.png "Ionut Balosin")

<div class="table-holder" markdown="block">

|handle             |count                                                                                                                                                                                                                                                                           |
|-------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|java               |21                                                                                                                                                                                                                                                                                 |
|graalvm            |9                                                                                                                                                                                                                                                                                  |
|ionutbalosin       |8                                                                                                                                                                                                                                                                                  |
|OpenJDK            |7                                                                                                                                                                                                                                                                                  |
|OracleCodeOne      |7                                                                                                                                                                                                                                                                                  |
|Devoxx             |6                                                                                                                                                                                                                                                                                  |
|InfoQ              |6                                                                                                                                                                                                                                                                                  |
|kcpeppe            |5                                                                                                                                                                                                                                                                                  |
|kuksenk0           |5                                                                                                                                                                                                                                                                                  |
|cl4es              |5                                                                                                                                                                                                                                                                                  |
|cliff_click        |5                                                                                                                                                                                                                                                                                  |
|no mentions        |5                                                                                                                                                                                                                                                                                  |
|shipilev           |5                                                                                                                                                                                                                                                                                  |
|jpbempel           |5                                                                                                                                                                                                                                                                                  |
|mon_beck           |4                                                                                                                                                                                                                                                                                  |
|nitsanw            |4                                                                                                                                                                                                                                                                                  |
|heinzkabutz        |4                                                                                                                                                                                                                                                                                  |
|fosdem             |4                                                                                                                                                                                                                                                                                  |
|AndreiPangin       |4                                                                                                                                                                                                                                                                                  |

</div>

Well, [@java](https://twitter.com/java) is used a bit like a hashtag, [@graalvm](https://twitter.com/graalvm) is a JVM implementation, so maybe we can discount those, but Ionut Balosin ([@ionutbalosin](https://twitter.com/ionutbalosin "Ionut Balosin")) is doing really well: ahead of [@OpenJDK](https://twitter.com/openjdk), and several conferences.
Well done, Ionut! 
Have some virtual credit.
If we scroll down a bit further through the list we find some highly accomplished people, such as Cliff Click.

What about by domain? Here, redirects have been followed, and the domain has been extracted from the URL.

<div class="table-holder" markdown="block">

|domain             |count                                                                                                                                                                                                                                                                           |
|-------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|youtube.com        |51                                                                                                                                                                                                                                                                                 |
|youtu.be           |18                                                                                                                                                                                                                                                                                 |
|infoq.com          |7                                                                                                                                                                                                                                                                                  |
|ionutbalosin.com   |5                                                                                                                                                                                                                                                                                  |
|no link            |4                                                                                                                                                                                                                                                                                  |
|fosdem.org         |3                                                                                                                                                                                                                                                                                  |
|github.com         |2                                                                                                                                                                                                                                                                                  |
|shipilev.net       |2                                                                                                                                                                                                                                                                                  |
|researchgate.net   |2                                                                                                                                                                                                                                                                                  |
|cl4es.github.io    |2                                                                                                                                                                                                                                                                                  |
|cr.openjdk.java.net|2                                                                                                                                                                                                                                                                                  |
|pingtimeout.fr     |2                                                                                                                                                                                                                                                                                  |
|pangin.pro         |2                                                                                                                                                                                                                                                                                  |
|batey.info         |1                                                                                                                                                                                                                                                                                  |
|blog.oio.de        |1                                                                                                                                                                                                                                                                                  |
|hirt.se            |1                                                                                                                                                                                                                                                                                  |
|groups.google.com  |1                                                                                                                                                                                                                                                                                  |
|blog.openj9.org    |1                                                                                                                                                                                                                                                                                  |
|blogs.oracle.com   |1                                                                                                                                                                                                                                                                                  |
|docs.oracle.com    |1                                                                                                                                                                                                                                                                                  |

</div>

Well, the top two are the same thing, and [infoq.com](https://infoq.com) hosts a lot of great content, but then here's [ionutbalosin.com](https://ionutbalosin.com "Ionut Balosin"), Ionut Balosin's website, doing incredibly well again, with more than double the number of posts of the next personal blog, [shipilev.net](https://shipilev.net).

Here's a bar chart (number of links, higher is better).

![JVMPerformance tweets by URL](/assets/2020/02/official-jvm-performance-league-table/JVMPerformance_by_url.png "Ionut Balosin")

 





