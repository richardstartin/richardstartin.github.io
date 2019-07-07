---
title: "HBase Connection Management"
date: 2016-11-05
---
I have built several web applications recently using Apache HBase as a backend data store. This article addresses some of the design concerns and approaches made in efficiently managing HBase connections.

One of the first things I noticed about the HBase client API was how long it takes to create the connection. HBase connection creation is effectively Zookeeper based service discovery. Once the connection is created, the end client will know where all the region servers are, and which region server is serving which key space. All of this takes time, so it's advisable not to connect too often.

At first I only created the connection once, when I started the web application. This is very simple and is fine for most use cases.

```java
public static void main(String[] args) throws Exception {
        Configuration configuration = HBaseConfiguration.create();
        Connection connection = ConnectionFactory.createConnection(configuration);
}
```

This approach is great unless there is the requirement to proxy your end user when querying HBase. If Apache Ranger is enabled on your HBase cluster, proxying your users allows it to apply user specific authorisation to the query, rather than to your web application service user. This poses a few constraints: the most relevant being that you need to create a connection per user so you can't just connect when you start your application any more.

#### Proxy Users
I needed to proxy users and minimise connection creation, so I built a connection pool class which, given a user principal, creates a connection as the user. I used Guava's loading cache to handle cache eviction and concurrency. Guava's cache also has a very useful eviction listener, which allows the connection to be closed when evicted from the cache.

In order to get the user proxying working, the UserGroupInformation for the web application service principal itself is required (see [http://richardstartin.uk/perpetual-kerberos-login-in-hadoop/](here)), and you need to have successfully authenticated your user (I used SPNego to do this). The Hadoop class UserProvider is then used to create a proxy user. Your web application service principal also needs to be configured as a proxying user in core-site.xml, which you can manage via tools like Ambari.

```java
public class ConnectionPool implements Closeable {

  private static final Logger LOGGER = LoggerFactory.getLogger(ConnectionPool.class);
  private final Configuration configuration;
  private final LoadingCache<String, Connection> cache;
  private final ExecutorService threadPool;
  private final UserProvider userProvider;
  private volatile boolean closed = false;
  private final UserGroupInformation loginUser;

  public ConnectionPool(Configuration configuration, UserGroupInformation loginUser) {
    this.loginUser = loginUser;
    this.configuration = configuration;
    this.userProvider = UserProvider.instantiate(configuration);
    this.threadPool = Executors.newFixedThreadPool(50, new ThreadFactoryBuilder().setNameFormat("hbase-client-connection-pool").build());
    this.cache = createCache();
  }

  public Connection getConnection(Principal principal) throws IOException {
    return cache.getUnchecked(principal.getName());
  }

  @Override
  public void close() throws IOException {
    if(!closed) {
      closed = true;
      cache.invalidateAll();
      cache.cleanUp();
      connectionThreadPool.shutdown();
    }
  }

  private Connection createConnection(String userName) throws IOException {
      UserGroupInformation proxyUserGroupInformation = UserGroupInformation.createProxyUser(userName, loginUser);
      return ConnectionFactory.createConnection(configuration, threadPool, userProvider.create(proxyUserGroupInformation));
  }

  private LoadingCache<String, Connection> createCache() {
    return CacheBuilder.newBuilder()
                       .expireAfterAccess(10, TimeUnit.MINUTES)
            .<String, Connection>removalListener(eviction -> {
              Connection connection = eviction.getValue();
              if(null != connection) {
                try {
                  connection.close();
                } catch (IOException e) {
                  LOGGER.error("Connection could not be closed for user=" + eviction.getKey(), e);
                }
              }
            })
            .maximumSize(100)
            .build(new CacheLoader<String, Connection>() {
              @Override
              public Connection load(String userName) throws Exception {
                LOGGER.info("Create connection for user={}", userName);
                return createConnection(userName);
              }
            });
  }
}
```

One drawback of this approach is that the user experiences a slow connection the first time they query the server or any time after their connection has been evicted from the cache. They will also observe a lag if you are sharding your application behind a load balancer without sticky sessions. If you use a round robin strategy connection creation costs will be incurred whenever there is a new instance/user combination route.
