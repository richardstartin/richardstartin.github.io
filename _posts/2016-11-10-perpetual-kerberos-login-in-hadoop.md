---
ID: 98
post_title: Perpetual Kerberos Login in Hadoop
author: Richard Startin
post_excerpt: ""
layout: post
permalink: >
  http://richardstartin.uk/perpetual-kerberos-login-in-hadoop/
published: true
post_date: 2016-11-10 20:56:13
---
Kerberos is the only real option for securing an Hadoop cluster. When deploying custom services into a cluster with Kerberos enabled, authentication can quickly become a cross-cutting concern.
<h4>Kerberos Basics</h4>
First, a brief introduction to basic Kerberos mechanisms. In each realm there is a <em>Key Distribution Centre</em> (KDC) which issues different types of tickets. A KDC has two services: the <em>Authentication Service</em> (AS) and the <em>Ticket Granting Service</em> (TGS). There are two ticket types issued: <em>Ticket Granting Tickets</em> (TGT) and <em>Service Tickets</em>. Every KDC has a special user called <em>krbtgt</em> and a service key derived from the password for the krbtgt account; a TGT is actually just a service ticket for the krbtgt account, encrypted with the krbtgt service key. The KDC has all the symmetric keys for all services and users in its realm.

The end goal of a user requesting a Kerberised service is to be able to present a service ticket obtained from the Ticket Granting Service to the Kerberised service in order to authenticate itself, but it needs to get a TGT and a TGS session key from the Authentication Service first. The sequence of requests and responses is as follows:
<ol>
	<li><strong>REQ_AS</strong>: The Client requests an initial TGT from the KDC's Authentication Service by passing its user key (the user key comes from a keytab file or a username and password). The presented key is checked against the client's symmetric key (the KDC has this encrypted with its own service key).</li>
	<li><strong>REP_AS</strong>: The Authentication Service issues a TGT which contains a TGS session key. The TGT has a lifetime and a renewable lifetime. Within the lifetime, the TGT can be cached and REQ_AS does not need to be made again: <em>TGT lookup does not need to happen on each service request. </em>The client creates an <em>authenticator. </em>The details of authenticator construction are too complicated to outline here. If a TGT is renewable, then only the TGS session key (not the TGT, which is large) need be refreshed periodically, and for each renewal the lifetime is reset.</li>
	<li><strong>REQ_TGS</strong>: Now the client has a TGS session key, it can request a service ticket from the TGS. The client must know the service name, and have a TGS session key and an authenticator. If no TGS session key is found, REQ_AS must be reissued. REQ_TGS must be performed for each service (if you need to access <a href="http://henning.kropponline.de/2016/02/21/secure-kafka-java-producer-with-kerberos/">Kafka</a> as well as HBase, you would need to do REQ_TGS twice, once for Kafka and once for HBase, though your TGT and TGS session key are good for both).</li>
	<li><strong>REP_TGS</strong>: The TGS has a local copy of the TGT associated with the TGS session key, which it checks against the authenticator and issues a service ticket. The service ticket is encrypted with the requested service's symmetric key. Finally the user has a service ticket.</li>
	<li><strong>REQ_APP</strong>: The client sends the service ticket to the service. The service decrypts the service ticket (it is encrypted by the TGS with the service's symmetric key.)</li>
	<li><strong>REP_APP (optional)</strong>: The client can request mutual authentication, in which case the service will respond with another ticket.</li>
</ol>
<h4>UserGroupInformation API</h4>
Kerberos is quite simple in Java if you have access to JAAS. Some of the newer Hadoop ecosystem projects do use it (e.g. Kafka, Solr) but if you are using HBase or HDFS you need to use UserGroupInformation. The only part of the Kerberos mechanism pertinent for most use cases is TGT acquisition; UserGroupInformation will handle the rest.

To get a TGT, you need a principal name and a keytab so UserGroupInformation can issue REQ_AS.

<code class="language-java">
UserGroupInformation ugi = UserGroupInformation.loginUserFromKeytabAndReturnUGI(clientPrincipalName, pathToKeytab);
UserGroupInformation.setLoginUser(ugi);
</code>

If your keytab is good, this will give you a TGT and a TGS session key. HBase and HDFS components will get the created UserGroupInformation from the static method <code class="language-java">UserGroupInformation.getLoginUser()</code>. In <a href="https://issues.apache.org/jira/browse/HADOOP-6656">HADOOP-6656</a> a background task was added to perform TGS session key renewal. This will keep you logged in until the renewable lifetime is exhausted, so long as renewable tickets are enabled in your KDC. When the renewable lifetime is exhausted, your application will not be able to authenticate.

To get around that, you can use UserGroupInformation to perform REQ_AS on a scheduled basis. This grants perpetuity.

<code class="language-java">
UserGroupInformation.getLoginUser().checkTGTAndReloginFromKeytab();
</code>

<h4>KerberosFacade</h4>
This can be done by a ScheduledExecutorService and wrapped up into a simple facade allowing you to login, logout, and execute actions as the logged in user, for as long as your service is up.

<code class="language-java">
public class KerberosFacade implements Closeable {

  private static final Logger LOGGER = LoggerFactory.getLogger(KerberosFacade.class);

  private final ScheduledExecutorService refresher;
  private final String keytab;
  private final String user;
  private final int requestTGTFrequencyHours;
  private volatile ScheduledFuture<?> renewal;
  private final AuthenticationFailureListener failureListener;

  public KerberosFacade(AuthenticationFailureListener failureListener,
                        String keytab,
                        String user,
                        int reloginScheduleHours) {
    this.failureListener = wrap(failureListener);
    this.keytab = keytab;
    this.user = user;
    this.requestTGTFrequencyHours = reloginScheduleHours;
    this.refresher = Executors.newSingleThreadScheduledExecutor();
  }

  public void login() throws IOException {
    UserGroupInformation loginUser =
         UserGroupInformation.loginUserFromKeytabAndReturnUGI(user, keytab)
    UserGroupInformation.setLoginUser(loginUser);
    this.renewal = refresher.scheduleWithFixedDelay(() -> {
      try {
        UserGroupInformation.getLoginUser()
                            .checkTGTAndReloginFromKeytab();
      } catch (Exception e) {
        onFailure(e);
      }
    }, requestTGTFrequencyHours, requestTGTFrequencyHours, TimeUnit.HOURS);
  }

  public void logout() {
    stopRefreshing();
    UserGroupInformation.setLoginUser(null);
  }

  public <T> T doAs(PrivilegedAction<T> action) {
    try {
      return UserGroupInformation.getCurrentUser()
                                 .doAs(action);
    } catch (IOException e) {
      onFailure(e);
      return null;
    }
  }

  public <T> T doAs(PrivilegedExceptionAction<T> action) throws PrivilegedActionException {
    try {
      return UserGroupInformation.getCurrentUser()
                                 .doAs(action);
    } catch (InterruptedException | IOException e) {
      onFailure(e);
      return null;
    }
  }

  @Override
  public void close() throws IOException {
    logout();
    refresher.shutdownNow();
  }

  private void stopRefreshing() {
    if (null != this.renewal) {
      this.renewal.cancel(true);
    }
  }

  protected void onFailure(Exception e) {
    failureListener.handle(this, e);
  }

  private static AuthenticationFailureListener wrap(AuthenticationFailureListener listener) {
    return (f, e) -> {
      LOGGER.error("Authentication Failure for " + f.user, e);
      if(null != listener) {
        listener.handle(f, e);
      }
    };
  }
}
</code>