# Operational Limitations

ARC is an academic user-space engine. Its safety model is deliberately narrow
and transparent.

## Crash recovery

Snapshots and resource ownership are held in memory. Normal shutdown, SIGINT,
and SIGTERM run best-effort restoration. SIGKILL cannot be intercepted. A
backend crash, WSL shutdown, or host failure can leave a living target with its
last applied affinity, nice value, stopped state, or cgroup membership.

There is no startup reconciliation or durable journal. The correct future
design would persist an identity-pinned write-ahead restoration record, fsync it
before mutation, and reconcile it before accepting new enforcement. Adding that
system immediately before a demonstration would be riskier than documenting
the current boundary.

Stranded controlled Resource Lab processes can be identified by their
`arc-resource-lab-*` command token. Confirm identity before sending SIGCONT or
terminating them. Do not use broad process-name kill commands.

## Nice values

For an owned process, increasing the numeric nice value usually succeeds.
Returning from 10 to 0 raises scheduling priority and commonly requires
`CAP_SYS_NICE` or an appropriate `RLIMIT_NICE`. ARC attempts exact restoration,
reports a kernel denial, retains the snapshot, keeps the contract in ERROR, and
blocks conflicting owners. Manual reset retries restoration and never discards
the retained state.

## Cgroups v2

The CPU controller must be present, enabled in `cgroup.subtree_control`, and
delegated to a hierarchy writable by the ARC user. Many WSL2 sessions mount
cgroups v2 read-only for an ordinary user. ARC reports that configuration
unavailable and does not modify global cgroup configuration or invoke sudo.

## Process lifetime

Linux identities use PID plus kernel start-time ticks. If a target exits, its
per-process affinity, nice value, and stopped state cease with it. A reused PID
is never mutated. Static target selectors can still match more processes than
intended, so demonstration contracts use unique command tokens.

## Observation and storage

The event history is bounded and in memory. It is neither durable nor
tamper-proof. CPU and process percentages are sampled values and can be noisy.
Resource Lab throughput is genuine worker output, but it is not a standardized
benchmark and does not imply a guaranteed performance improvement.

## Security and scope

ARC has no authentication and should not be exposed to an untrusted network.
It has no database, privileged helper, kernel module, or automatic elevation.
Resource Lab controls are restricted to child processes created by its backend
controller, while general contracts remain operator-authored configuration.
