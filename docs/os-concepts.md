# Operating Systems concepts behind ARC

This note connects ARC to the OS ideas it builds on. It is background
reading, not a full OS reference.

## 1. Processes and process management

ARC observes and acts on running Linux processes: their identities,
lifetimes, resource usage, and tunable properties. PIDs are ephemeral
(the kernel reuses them), so ARC contracts match on process metadata
such as executable name and command line instead of persisted PIDs, and
the monitor re-resolves matches on every cycle. Snapshots pin PID plus kernel
start-time ticks from `/proc/<pid>/stat`, and restoration re-verifies the pair
so a reused
PID is never written to. The OS creates,
schedules, and reaps processes. ARC coordinates policy on top of that
lifecycle without replacing it.

## 2. CPU scheduling and process priority

Linux's Completely Fair Scheduler shares CPU among runnable tasks. The
nice value (typically -20 to 19) biases a process's scheduling weight:
lower values request preferential treatment, higher values yield more
readily. Nice values influence priority relatively, they do not guarantee
a fixed CPU share. ARC enforces nice values on Linux through the
`ResourceAdapter` boundary: snapshot the current value, set the new one
with `psutil.Process.nice()`, read it back to verify. CPU utilization
read back through `SystemSnapshot.cpu_percent` is the observation side
of the same idea: it tells policy how busy the machine is, without
promising any share.

## 3. CPU affinity

Affinity constrains which CPUs a task may execute on (for example through
`sched_setaffinity` or cpuset controls). It is useful for cache locality
or isolating workloads, but overly narrow masks can starve a process.
Affinity changes are reversible, so ARC records the prior mask in a
`ResourceSnapshot` and restores that exact mask afterwards, verifying by
reading it back. Requesting CPUs outside the allowed set fails
activation explicitly instead of being silently masked.

## 4. Resource control with cgroups v2

Control groups organize processes into hierarchies and provide kernel
mechanisms for accounting and limiting resources such as CPU, memory, and
I/O. ARC interfaces with cgroups v2 via `cpu.max` quota leases under a
dedicated `arc/arc-<pid>` directory below the configured hierarchy, attaching
target PIDs to managed groups
during activation and removing quotas upon contract restoration. When
cgroups v2 hierarchy is not writable or unavailable, ARC reports this
capability status transparently without faking support.

## 5. /proc and runtime observation

The `/proc` filesystem exposes per-process and system information (status,
scheduling parameters, CPU times, memory counters) as files. ARC's
monitoring layer reads through psutil (which itself draws on interfaces
like these on Linux) to build typed snapshots: `SystemSnapshot` for CPU
and memory utilization, and `ProcessObservation` entries carrying PID,
name, command line, and usage counters. Contract evaluation reasons
over these snapshots without mutating anything.

## 6. Signals and process control

POSIX signals let one process notify another (terminate, suspend with
`SIGSTOP`, resume with `SIGCONT`, or handle custom notifications). ARC
implements `suspend` and `resume` contract actions using standard POSIX
signals (`SIGSTOP` and `SIGCONT`). Process status is snapshotted prior to
mutation, ensuring that restoration only resumes processes that were
running beforehand, and self-protection guards prevent the engine from
signaling itself or its parent.

## 7. Concurrency

Monitoring, evaluation, and enforcement share state (active contracts,
snapshots, event logs). ARC keeps this simple: one synchronous engine
step runs under a short lock, the async loop only schedules steps, and
the API hands out copies. Lifecycle moves go through explicit
transitions, and errored contracts latch instead of retrying every poll.

## 8. Protection and privileges

Resource operations are privileged: lowering nice values, signaling other
users' processes, or managing cgroups requires ownership or elevated
capabilities. ARC runs as an ordinary user-space program subject to these
checks, and it never escalates (no sudo, no password prompts). When the
kernel refuses an operation, activation fails and rolls back, the
contract goes to ERROR, and the event log explains the denial. The demo
in `docs/demo.md` shows this concretely: restoring a nice value back
down may need `CAP_SYS_NICE`, and ARC reports that honestly instead of
faking success. `GET /api/status` exposes the platform capability report
so operators can see the constraint up front.

## 9. Policy versus mechanism

A classic OS distinction applies here. Linux provides mechanisms: nice
values, affinity masks, cgroups, signals, `/proc`. ARC provides a
higher-level policy and orchestration layer: explicit contracts that
decide when selected mechanisms are used, track what changed, restore
prior state, and explain each decision in logs. The contribution is that
contract abstraction and its lifecycle, not new kernel primitives.
