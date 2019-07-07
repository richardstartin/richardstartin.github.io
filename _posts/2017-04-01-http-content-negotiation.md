---
ID: 2742
post_title: HTTP Content Negotiation
author: Richard Startin
post_excerpt: ""
layout: post
permalink: >
  http://richardstartin.uk/http-content-negotiation/
published: true
post_date: 2017-04-01 14:27:53
---
Ever had the situation where you've implemented a REST API, and then another team or potential customer comes along and asks if you could just change the serialisation format? Or maybe you are using a textual media type and want to experiment to see if performance would improve with a binary format? <strong>I see this done wrong all the time.</strong>

There is a mechanism for <em><a href="https://developer.mozilla.org/en-US/docs/Web/HTTP/Content_negotiation" target="_blank" rel="noopener noreferrer">content negotiation</a></em> built in to HTTP since the <a href="https://www.w3.org/Protocols/HTTP/1.1/draft-ietf-http-v11-spec-01" target="_blank" rel="noopener noreferrer">early days</a>. It's a very simple mechanism so this won't be a long post. There is a short Java example using Jackson and Jersey to allow parametric content negotiation to be performed transparently to both the server and client.
<h3>Never Ever Do This</h3>
One option would be to implement a completely new service layer for each content type you need to serve. This not only costs you time, and probably test coverage, but moving between serialisation formats as a client of your API will probably constitute a full-blown <em>migration</em>.<em> </em>Keeping the implementations synchronised will become difficult, and somebody needs to tell the new guy he needs to implement the change in the <em>JSON version </em>as well as the <em>SMILE version,</em> and if the <em>XML version </em>could be updated by the end of the week, that would be great.<em> </em>I have seen commercial products that have actually done this.
<h3>Don't Do This (Unless You've Already Done It)</h3>
Another option that I see in various APIs is using a query parameter for GET requests. This offends my sensibilities slightly, because it has the potential to conflate application and transport concerns, but it's not that bad<em>.</em> The SOLR REST API has a query parameter <em><a href="https://cwiki.apache.org/confluence/display/solr/Using+JavaScript" target="_blank" rel="noopener noreferrer">wt </a></em>which allows the client to choose between JSON and XML, for instance. It's not exactly cumbersome and the client can easily change the serialisation format by treating it as a concern of the application. But what if you want to query the API from a browser? Browsers speak HTTP <em>ex cathedra</em>, not the local patois your API uses. The browser will have to put up with whatever your defaults are, and hope it can consume that format. It's unnecessary complexity in the surface area of your API but it's quite common, and at least it isn't <em>weird.</em>
<h3>1996 Calling</h3>
All you have to do is set the <em>Accept </em>header of the request to the media type (for instance - <em><a href="http://richardstartin.uk/concise-binary-object-representation/">application/cbor</a>)</em> you want to consume in the response.  If the server can produce the media type, it will do so, and then set the <em>Content-Type </em>header on the response. If it can't produce the media type (and this should come out in integration testing) the server will respond with a 300 response code with textual content listing the supported media types that the client should choose from.
<h3>Content Negotiation with Jersey and Jackson JAX-RS providers</h3>
Jackson makes this very easy to do in Java. We want to be able to serialise the response below into a MIME type of the client's choosing - they can choose from JSON, XML, CBOR, SMILE and YAML. The response type produced is not constrained by annotations on the method; none of the formats need ever be formally acknowledged by the programmer and can be added or removed by modifying the application's classpath.

<code class="language-java">
@Path("content")
public class ContentResource {

  @GET
  public Response getContent() {
    Map<String, Object> content = new HashMap<>();
    content.put("property1", "value1");
    content.put("property2", 10);
    return Response.ok(content).build();
  }
}
</code>

There are Jackson JAX-RS providers included by the maven dependencies below. Their presence is transparent to the application and can be used via the standard JAX-RS Resource SPI. Handler resolution is implemented by a <a href="https://en.wikipedia.org/wiki/Chain-of-responsibility_pattern" target="_blank" rel="noopener noreferrer">chain-of-responsibility</a> where the first resource accepting the Accept header will serialise the body of the response and set the Content-Type header.

<code class="language-xml">
        <dependency>
            <groupId>com.fasterxml.jackson.jaxrs</groupId>
            <artifactId>jackson-jaxrs-json-provider</artifactId>
            <version>2.8.7</version>
        </dependency>

        <dependency>
            <groupId>com.fasterxml.jackson.jaxrs</groupId>
            <artifactId>jackson-jaxrs-xml-provider</artifactId>
            <version>2.8.7</version>
        </dependency>

        <dependency>
            <groupId>com.fasterxml.jackson.jaxrs</groupId>
            <artifactId>jackson-jaxrs-smile-provider</artifactId>
            <version>2.8.7</version>
        </dependency>

        <dependency>
            <groupId>com.fasterxml.jackson.jaxrs</groupId>
            <artifactId>jackson-jaxrs-cbor-provider</artifactId>
            <version>2.8.7</version>
        </dependency>

        <dependency>
            <groupId>com.fasterxml.jackson.jaxrs</groupId>
            <artifactId>jackson-jaxrs-yaml-provider</artifactId>
            <version>2.8.7</version>
        </dependency>
</code>

There's some simple coding to do to configure the Jersey resource and run it embedded with Jetty.

<code class="language-java">
public class ServerRunner {

  public static void main(String[] args) throws Exception {
    ResourceConfig config = new ResourceConfig();
    config.packages(true, "com.fasterxml.jackson.jaxrs");
    config.register(ContentResource.class);
    ServletHolder servletHolder = new ServletHolder(new ServletContainer(config));
    Server server = new Server(8080);
    ServletContextHandler handler = new ServletContextHandler(server, "/*");
    handler.addServlet(servletHolder, "/*");
    server.start();
    server.join();
  }
}
</code>

If you do this, then you can leave the decision up to your client and just add and remove resource provider jars from your classpath. A silver lining is that you can test the mechanism yourself from IntelliJ:

<img style="max-width: 90%; margin: 5px; overflow: scroll;" src="http://richardstartin.uk/wp-content/uploads/2017/11/accept.png" alt="accept" />

<img style="max-width: 90%; margin: 5px; overflow: scroll;" src="http://richardstartin.uk/wp-content/uploads/2017/11/response.png" alt="response" />

And you can get non-technical users to check from a browser:

<img style="max-width: 90%; margin: 5px; overflow: scroll;" src="http://richardstartin.uk/wp-content/uploads/2017/11/broswer.png" alt="browser" />