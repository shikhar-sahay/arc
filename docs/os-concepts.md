# Operating Systems concepts behind ARC

This note connects ARC to the OS ideas it builds on. It is background
reading, not a full OS reference.

## 1. Processes and process management

ARC observes and acts on running Linux processes: their identities,
lifetimes, resource usage, and tunable properties. PIDs are ephemeral
(the kernel reuses them), so ARC contracts match on process metadata
such as executable name and command line instead of persisted PIDs, and
the monitor re-resolves matches on every cycle. The OS creates,
schedules, and reaps processes. ARC coordinates policy on top of that
lifecycle without replacing it.

## 2. CPU scheduling and process priority

Linux's Completely Fair Scheduler shares CPU among runnable tasks. The
nice value (typically -20 to 19) biases a process's scheduling weight:
lower values request preferential treatment, higher values yield more
readily. Nice values influence priority relatively, they do not guarantee
a fixed CPU share. ARC validates nice intents against this range today
(`NiceAction` accepts -20 to 19) and will apply them as reversible
actions in the enforcement pass. CPU utilization read back through
`SystemSnapshot.cpu_percent` is the observation side of the same idea:
it tells policy how busy the machine is, without promising any share.

## 3. CPU affinity

Affinity constrains which CPUs a task may execute on (for example through
`sched_setaffinity` or cpuset controls). It is useful for cache locality
or isolating workloads, but overly narrow masks can starve a process.
Affinity changes are reversible, so ARC must record the prior mask and
restore that exact mask afterwards.

## 4. Resource control with cgroups v2

Control groups organize processes into hierarchies and provide kernel
mechanisms for accounting and limiting resources such as CPU, memory, and
I/O. Selected cgroups v2 controllers (for example `cpu` weight and limits)
are candidates for later ARC actions. ARC will use these interfaces, not
reimplement them.

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
`SIGSTOP`, resume with `SIGCONT`, or handle custom notifications). Signals
are asynchronous and easy to misuse, so any future ARC use needs explicit
semantics: which signal, to which process, under which contract, with what
logged outcome.

## 7. Concurrency

Monitoring, evaluation, and enforcement operate on different cadences over
shared state (active contracts, snapshots, event logs). That creates
classic coordination concerns: stale reads, races between activation and
restoration, and overlapping transitions for the same contract. Later
passes need clear ownership of shared state and serialized lifecycle
transitions per contract.

## 8. Protection and privileges

Resource operations are privileged: lowering nice values, signaling other
users' processes, or managing cgroups requires ownership or elevated
capabilities. ARC runs as an ordinary user-space program subject to these
checks. When the kernel refuses an operation, ARC must log the failure
with context instead of pretending the action succeeded.

## 9. Policy versus mechanism

A classic OS distinction applies here. Linux provides mechanisms: nice
values, affinity masks, cgroups, signals, `/proc`. ARC provides a
higher-level policy and orchestration layer: explicit contracts that
decide when selected mechanisms are used, track what changed, restore
prior state, and explain each decision in logs. The contribution is that
contract abstraction and its lifecycle, not new kernel primitives.
