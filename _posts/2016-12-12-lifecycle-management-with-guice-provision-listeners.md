---
title: "Lifecycle Management with Guice Provision Listeners"
layout: post
theme: minima
date: 2016-12-12
---

Typically in a Java web application you will have services with resources which need lifecycle management - at the very least closing gracefully at shutdown. If you'd use a sledgehammer to crack a walnut, there's Spring, which will do this for you with init and destroy methods. I'll explain why I dislike Spring in another post. You could also add a shutdown hook to every class you implement, but this is repetitive and what happens if you extend a class which already has its own shutdown hook? I like [Guice](https://github.com/google/guice) as a DI framework because it is minimal, type-safe, interoperates with [JSR-330]https://matthiaswessendorf.wordpress.com/2010/01/19/dependency-injection-the-jsr-330-way/), but it doesn't contain lifecycle management functionality. Since Guice 4.0, this has been very easy to add as a DIY add-on using a [ProvisionListener](https://google.github.io/guice/api-docs/latest/javadoc/index.html?com/google/inject/spi/ProvisionListener.html).

The `ProvisionListener` interface has a single method `void onProvision(ProvisionInvocation provisionInvocation)` which gets called each time an object is created. This is your chance to check if the instance needs closing and if the instance should live for the entire application lifetime. For the sake of simplicity, this listener just checks if the instance implements an interface, and that the provision is eager or a singleton, but you can execute arbitrary java code here to do something more sophisticated.

```java
public class CloseableListener implements ProvisionListener {

    private final LifeCycleObjectRepository repo;

    public CloseableListener(LifeCycleObjectRepository repo) {
        this.repo = repo;
    }

    @Override
    public <T> void onProvision(ProvisionInvocation<T> provisionInvocation) {
        T provision = provisionInvocation.provision();
        if(provision instanceof Closeable && shouldManage(provisionInvocation)) {
            repo.register((Closeable)provision);
        }
    }

    private boolean shouldManage(ProvisionInvocation<?> provisionInvocation) {
        return provisionInvocation.getBinding().acceptScopingVisitor(new BindingScopingVisitor<Boolean>() {
            @Override
            public Boolean visitEagerSingleton() {
                return true;
            }

            @Override
            public Boolean visitScope(Scope scope) {
                return scope == Scopes.SINGLETON;
            }

            @Override
            public Boolean visitScopeAnnotation(Class<? extends Annotation> scopeAnnotation) {
                return scopeAnnotation.isAssignableFrom(Singleton.class);
            }

            @Override
            public Boolean visitNoScoping() {
                return false;
            }
        });
    }
}
```

Here `LifeCycleObjectRepository` has the responsibility of registering and holding onto an instance until it is closed itself.

```java
public class LifeCycleObjectRepository {

    private static final Logger LOGGER = LoggerFactory.getLogger(LifeCycleObjectRepository.class);

    private final Set<Closeable> closeableObjects = Sets.newConcurrentHashSet();

    void register(Closeable closeable) {
        if(closeableObjects.add(closeable)) {
            LOGGER.info("Register {} for close at shutdown", closeable);
        }
    }

    public synchronized void closeAll() {
        closeableObjects.forEach(c -> {
            try {
                LOGGER.info("Close {}", c);
                c.close();
            } catch (IOException e) {
                LOGGER.error("Error closing object", e);
            }
        });
        closeableObjects.clear();
    }
}
```

This is almost a complete solution, now we need to make sure we close the `LifeCycleObjectRepository` when we get a SIGTERM, and register the CloseableListener so it can collect provisions of singletons, without leaking these details everywhere. To stop the details of the `CloseableListener` leaking, we can wrap it in a module which binds the listener, and installs the client module.

```java
public class LifeCycleAwareModule extends AbstractModule {
    private final Module module;
    private final LifeCycleObjectRepository repo;
    protected LifeCycleAwareModule(LifeCycleObjectRepository repo, Module module) {
        this.lifeCycleState = lifeCycleState;
        this.module = module;
    }

    @Override
    protected void configure() {
        bindListener(Matchers.any(), new CloseableListener(repo));
        install(module);
    }
}
```

Finally, implement a `LifeCycleManager` to own - and close in a shutdown hook - a `LifeCycleObjectRepository`. The `LifeCycleManager` receives all Guice modules required to bind the application, and wraps them with the `LifeCycleObjectRepository` to enable lifecycle management.

```java
public class LifeCycleManager {

    private final LifeCycleObjectRepository repo = new LifeCycleObjectRepository();
    private final Injector injector;

    public LifeCycleManager(Module... modules) {
        this(ImmutableList.copyOf(modules));
    }

    public LifeCycleManager(Iterable<Module> modules) {
        this.injector = Guice.createInjector(enableLifeCycleManagement(repo, modules));
        addShutdownHook();
    }

    public <T> T getInstance(Class<T> type) {
        return injector.getInstance(type);
    }

    private void addShutdownHook() {
        Runtime.getRuntime().addShutdownHook(new Thread(repo::closeAll));
    }

    private static Iterable<Module> enableLifeCycleManagement(LifeCycleObjectRepository repo, Iterable<Module> modules) {
        return StreamSupport.stream(modules.spliterator(), false)
                .map(m -> new LifeCycleAwareModule(repo, m))
                .collect(Collectors.toList());
    }
}
```

This is a very useful API to hook into to get control over object life cycle without inviting enormous frameworks into your code base.
