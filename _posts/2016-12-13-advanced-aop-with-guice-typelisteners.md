---
title: Advanced AOP with Guice Type Listeners
layout: post
published: true
post_date: 2016-12-13
---

There are cross-cutting concerns, or _aspects_, in any non-trivial program. These blocks of code tend to be repetitive, unrelated to business logic, and don't lend themselves to being factored out. If you have ever added the same statement at the start of several methods, you have encountered an aspect. For instance, audit, instrumentation, authentication, authorisation could all be considered aspects. If you'd use a sledgehammer to crack a walnut, Spring can help you with AOP by using proxies. Guice can also perform AOP out of the box allowing you to bind implementations of [MethodInterceptor](http://aopalliance.sourceforge.net/doc/org/aopalliance/intercept/MethodInterceptor.html). In fact, [tutorials](http://musingsofaprogrammingaddict.blogspot.co.uk/2009/01/guice-tutorial-part-2-method.html) were being written about doing that before I wrote my first line of Java. However, it gets more complicated when you need a separate (potentially stateful) interceptor per usage of an annotation, making it infeasible to bind the interceptor statically. If only you could bind the interceptor dynamically, when the intercepted type is first requested, it would be so easy to do. This is exactly what the interface [TypeListener](https://google.github.io/guice/api-docs/latest/javadoc/index.html?com/google/inject/spi/TypeListener.html) allows.

TypeListener is a simple interface with a single method

```java
  <I> void hear(TypeLiteral<I> type, TypeEncounter<I> encounter);
```

This method gets invoked the first time a type requested for injection is encountered. At this point you can introspect the `TypeLiteral` and bind a new `MethodInterceptor` instance to the `TypeEncounter`. The mechanics of detecting and binding requested interception is common, so factor it out into a base listener class, deferring creation of the `MethodInterceptor` until later.

```java
abstract class MethodInterceptorBinder implements TypeListener {

    @Override
    public <T> void hear(TypeLiteral<T> literal, TypeEncounter<T> encounter) {
        Arrays.stream(literal.getRawType().getDeclaredMethods())
              .filter(m -> !m.isSynthetic())
              .forEach(m -> bindInterceptor(m, encounter));
    }

    private void bindInterceptor(Method method, TypeEncounter<?> encounter) {
        final MethodInterceptor interceptor = getInterceptor(method);
        if (interceptor != null) {
            encounter.bindInterceptor(Matchers.only(method), interceptor);
        }
    }

    protected abstract MethodInterceptor getInterceptor(Method method);
}
```

Suppose we would like to audit calls to a method, associating an audit topic with each method. Then we can just extend `MethodInterceptorBinder` as below, and bind the listener in a module somewhere. Every method annotated for audit will be audited, and audited separately.

```java
public class AuditBinder extends MethodInterceptorBinder {

  private final Auditor auditor;

  public AuditBinder(Auditor auditor) {
      this.auditor = auditor;
  }

  @Override
  protected MethodInterceptor getInterceptor(Method method) {
      Audited audited = method.getAnnotation(Audited.class);
      return null != audited ?
             new AuditingInterceptor(auditor, audited.topic()) :
             null;
  }
}

public class AuditModule extends AbstractModule {

  private final Auditor auditor;

  public AuditModule(Auditor auditor) {
    this.auditor = auditor;
  }

  @Override
  protected void configure() {
    bindListener(Matchers.any(), new AuditBinder(auditor));
  }
}
```
