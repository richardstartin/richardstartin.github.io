---
title: How Async-Profiler's crash handler works
layout: post
tags: profiling
date: 2023-11-12
---

Raw pointers in C/C++ open up entire classes of error that are practically unimaginable in higher level languages.
So why does anybody use them at all?
Unfortunately, it's impossible to write a profiler without getting close to some of the sharp edges of unsafe memory. 
The async-profiler code base contains a lot of low level tricks, and it's worth studying how some of them work. 

This post is about how async-profiler safely dereferences arbitrary pointers without crashing the JVM, and why it needs to do that sometimes.

1. TOC
{:toc}

# Signals and signal handlers

Linux allows threads to be interrupted by signals, which are identified by a signal number.
Signals can be sent to threads via a number of syscalls, such as [`tgkill`](https://man7.org/linux/man-pages/man2/tgkill.2.html), or indirectly via profiling services like [itimer](https://man7.org/linux/man-pages/man3/setitimer.3p.html) or [perf_event_open](https://man7.org/linux/man-pages/man2/perf_event_open.2.html).
When a thread transitions between the kernel and user space, such as when the thread is scheduled to run on the CPU, the kernel checks if there are any pending signals for the thread.
If there is a pending signal, and the signal isn't blocked by a [signal mask](https://man7.org/linux/man-pages/man2/sigprocmask.2.html), and there is a _signal handler_ installed for the signal, then the thread is halted and the signal handler is invoked.
A signal based sampling profiler consists of a mechanism for choosing threads and sending signals (usually `SIGPROF`) to them, then a signal handler for collecting information about the state of the thread (e.g. unwinding the stack).
Signals and signal handlers are used for a number of other things, such as killing the process (`SIGKILL`), or signalling that something has gone wrong (`SIGSEGV`, `SIGABRT`, `SIGBUS`).
If you just want your program not to crash when performing memory unsafe operations, you can install signal handlers for error signals and swallow them, though this will cause other problems without care.    

# Frame pointer unwinding

You don't need to handle segfaults if your code can't segfault, so why not just use a programming language with a compiler which verifies memory safety?
Unfortunately, you wouldn't have much of a profiler if you did that (without unsafe blocks, anyway).
Consider the simplest stack unwinding approach using frame pointers.

Signal handlers are invoked with a `ucontext` which consists of a program counter, a frame pointer, and a stack pointer.

The program counter (`pc`) is the address of the code currently being executed.
It can be used to find the currently executing function by binary searching a compiled binary's text section (where the code is found) or the JVM's code heap for JIT compiled code.
It is enough to determine the currently executing instruction (which is how instruction profiling works).
However, the program counter is not enough to determine the caller of the interrupted function.

The frame pointer (`fp`) determines the start address of the stack frame, which contains function parameters and local variables.
The stack frame is like a snapshot of the registers before calling a function, so that when the called function returns, the calling context can be restored.
Obtaining the frame pointer to the calling frame from the callee frame is known as _unwinding_.
_If_ a binary is compiled with frame pointers, it's really simple: on x64, the `rbp` register contains the caller's frame pointer.
So frame pointer unwinding consists of the following (on x64, the registers differ on aarch64):

1. Record the program counter from the `ucontext` (this can be used later to determine things like function name, line number, and the instruction)
2. Read the caller's frame pointer from `rbp`
3. Check termination (this could be if the frame pointer is zero, if the frame pointer is outside the bounds of the stack, or in async-profiler if a Java frame has been found).
4. Restore the caller frame from the caller's frame pointer (dereference the frame pointer).
5. Record the program counter (see point 1)
6. Go to step 2

This is about as fast and simple as stack unwinding gets, but the problem is lots of binaries are compiled without frame pointers.
If a binary is compiled without frame pointers, `rbp` contains arbitrary data and isn't safe to dereference.
Depending on the exact value stored in the register, dereferencing it may produce a bogus frame but will probably segfault (generate a `SIGSEGV` signal).
I am unaware of any way to determine that an arbitrary binary was compiled with frame pointers or not, so the only way to determine whether `rbp` is a frame pointer or not is to dereference it and hopefuly get a frame.
This puts frame pointer unwinding outside the realm of compile time memory safety checks: either mitigate at runtime or don't do it.

# `SafeAccess::load`

Async-profiler uses the following mechanism:
1. Always dereference untrusted data via a function called `SafeAccess::load`.
2. Install a `SIGSEGV` handler.
3. Check in the `SIGSEGV` handler if the `SIGSEGV` signal's `pc` came from `SafeAccess::load`. If it did, patch things up as if the function returned zero, otherwise pass the signal on.

There are some details which are worth paying attention to in the function declaration ([source](https://github.com/async-profiler/async-profiler/blob/master/src/safeAccess.h#L33)):

```cpp
   #ifdef __clang__
   #  define NOINLINE __attribute__((noinline))
   #else
   #  define NOINLINE __attribute__((noinline,noclone))
   #endif
   ...
   NOINLINE __attribute__((aligned(16)))
    static void* load(void** ptr) {
        return *ptr;
    }
```

Firstly, the function can't be inlined because of the compiler attributes applied to it, because if it were inlined, it wouldn't be possible to determine whether the `SIGSEGV`'s `pc` came from the function or not.
Next, the function is aligned so that a `pc` can be determined to be within the function's code's address range easily.

In the signal handler installed when starting the profiler, the following code executes:

```cpp
    uintptr_t length = SafeAccess::skipLoad(pc);
    if (length > 0) {
        // Skip the fault instruction, as if it successfully loaded NULL
        frame.pc() += length;
        frame.retval() = 0;
        return;
    }
```

This code figures out how far to skip ahead to simulate returning from the function, having set the return value to zero.
The way the number of instructions to skip is determined is a little cryptic (only for x64 below):

```cpp
    static uintptr_t skipLoad(uintptr_t pc) {
        if ((pc - (uintptr_t)load) < 16) {
            return *(u16*)pc == 0x8b48 ? 3 : 0;  // mov rax, [reg]
        }
        return 0;
    }
```

Checking if the `pc` is in the address range of the `load` function is straightforward enough, but what on earth is `0x8b48`?
Dereferencing a `pc` gives a sequence of bytes corresponding to the instructions. 
Casting to a `u16*` truncates to the most significant 2 bytes, which has the effect of ignoring the register the value would be loaded into.
The `0x8b48` check verifies that the `pc` is pointing at a `mov` operation, otherwise something has gone wrong.
Finally, 3 bytes need to be skipped over: 2 for the load, and one for the destination register.

# Replacing crash handlers

The JVM has its own `SIGSEGV` handler already, in fact, it's quite important because it's part of the [uncommon trap mechanism](https://shipilev.net/jvm/anatomy-quarks/29-uncommon-traps/) for deoptimisation of speculative optimisations.
This means Async-profiler must delegate to the JVM's `SIGSEGV` handler in order not to break the JVM.
It does this by [returning a function pointer to the old handler](https://github.com/async-profiler/async-profiler/blob/master/src/os_linux.cpp#L255) when [installing its own handler](https://github.com/async-profiler/async-profiler/blob/master/src/profiler.cpp#L888), and then delegates to it if the `pc` didn't come from `SafeAccess::load`.
The JVM doesn't exactly like signals it handles being overridden like this, given the central importance of `SIGSEGV` signals to the lifecycle of JIT compiled code, and running with `-Xcheck:jni` will spit out angry warning messages about it. 
These messages are annoying but much better than simply dropping samples when the JVM is not executing Java code, because Java code can call native code, and this is sometimes where performance problems lie.