# ARCHITECTURE.md

Authoritative technical architecture for ARC (Adaptive Resource Contract
Engine). The contract lifecycle through enforcement and restoration is
implemented for nice values, CPU affinity, process suspend and resume,
and delegated cgroups v2 CPU quotas on Linux.

## Architectural goals

- Coordinate existing Linux resource mechanisms through explicit,
  user-defined contracts.
- Separate policy (when and what to change) from mechanism (how Linux
  applies the change).
- Make restoration a first-class behavior: every temporary change must be
  reversible to its recorded prior state.
- Keep decisions observable through structured logs and events.
- Remain testable on non-Linux hosts by isolating Linux-specific code.

## System boundaries

1. **Web Presentation** (`frontend/`): observes engine state and submits
   user intent. It holds no authoritative policy logic.
2. **ARC API** (`backend/src/arc/api`): FastAPI interface exposing engine
   status, contracts, processes, and events. It is not the policy engine.
3. **ARC Core** (`backend/src/arc/core`, `contracts`, `monitoring`,
   `evaluation`, `enforcement`, `restoration`, `observability`): contract
   models, event detection, evaluation, lifecycle, enforcement
   orchestration, restoration, and observability.
4. **Linux Integration** (`backend/src/arc/linux`): the only layer
   that names OS resource operations. psutil-based read-only observation
   plus a `ResourceAdapter` protocol with a real Linux implementation
   (nice, affinity, signals, and selected cgroups v2 CPU controls) and
   an in-memory fake for tests.
5. **Linux Processes and Resources**: the OS-level entities ARC observes
   and acts on.

## Dependency direction

```mermaid
flowchart TD
  Web["ARC Web (React)"] --> API["ARC API (FastAPI)"]
  API --> Core["ARC Core (policy, lifecycle, orchestration)"]
  Core --> LinuxInt["Linux Integration (adapters)"]
  LinuxInt --> Linux["Linux Processes and Resources"]
```

Dependencies point downward only. The web layer never calls Linux
integration directly, and the API layer never embeds evaluation or
enforcement policy.

## ARC Core modules

- `core/`: lifecycle states with enforced transitions, per-contract
  runtime state, and the persistent runtime engine loop.
- `contracts/`: authoritative contract models and YAML loading.
- `monitoring/`: read-only system telemetry and process observation
  plus process target resolution, all built on psutil.
- `evaluation/`: trigger and restore condition evaluation.
  Independent of FastAPI.
- `enforcement/`: transaction-like activation (snapshot all, apply in
  contract order and PID order, verify each, roll back on failure).
- `restoration/`: exact snapshot restoration with identity checks and
  read-back verification.
- `linux/`: `ResourceAdapter` protocol, real Linux implementation,
  in-memory fake for tests, platform capability reporting.
- `observability/`: bounded in-memory event history plus logging.
  No event bus.
- `api/`: FastAPI interface that only reads engine state (health,
  status, system, contracts, processes, events).
- `cli/`: contract validation plus the headless `arc run` engine.

Core must stay headless-capable: anything the web UI can do should also be
possible without it.

## Configuration versus runtime state

Contract YAML is declarative configuration: identity, target, trigger,
actions, and restore condition. CRUD and enabled toggles write only this
configuration, and reload replaces definitions atomically. Protected
contracts cannot be changed or removed while activating, active, or
restoring. Runtime state is transient and per contract: matched PIDs, duration
timers, latest preview outcome, lifecycle state, and errors. It lives in
`ContractRuntimeState` objects owned by the observation engine and held
in memory only. There is no database.

## Target resolution

PIDs are ephemeral, so contracts match on process metadata (executable
name, command line substring) instead of persisted PIDs. Each cycle the
engine snapshots processes and resolves every match, sorted by PID.
When no process matches, a process-targeted contract reports
`target_not_found` and cannot move toward activation, even if a system
metric alone would satisfy the trigger.

## Duration semantics and hysteresis

A condition with `for_seconds: N` must hold continuously for N seconds
before it counts as satisfied. One false sample resets the timer, which
keeps single-sample spikes from activating policy. Timers run on a
monotonic clock passed into the evaluation functions, so tests inject
timestamps instead of sleeping. Trigger and restore conditions are
separate so episodes use hysteresis (activate above 75, restore below
55) instead of flapping around one threshold.

## Persistent runtime engine

`ObservationEngine` is the source of truth. It owns contracts, runtime
state, the event log, and the latest snapshots. One synchronous step
performs a full cycle (sample, resolve, evaluate, enforce, restore)
under one state lock; an async loop only schedules steps and never holds
the lock across sleeps. HTTP GET handlers only read cached state, they
never evaluate or enforce. Contract reload is an explicit mutation.
The observation-only WebSocket sends initial state and periodic ticks.

On graceful shutdown the engine best-effort restores every ACTIVE contract,
plus ERROR contracts retaining incomplete-restoration snapshots, before
exiting. It reports failures instead of silently abandoning modified resources.

## Resource adapter boundary

Domain code never calls scheduling or signal APIs directly. Nice,
affinity, suspend, and resume work go through `ResourceAdapter`. CPU
quota uses the explicit cgroups v2 manager boundary. The real implementation refuses clearly off Linux
and maps kernel denials to explicit errors. Tests use the in-memory
fake, which never stands in for real operations.

## Snapshot, rollback, and identity safety

Activation captures a `ResourceSnapshot` per target (PID, creation
time, name, plus only the properties about to change) before any
mutation. Mutations apply in contract order and PID order with
read-back verification. Any failure rolls the journal back in reverse
and lands the contract in ERROR with the rollback outcome recorded
(clean versus incomplete, naming each failed resource).

Restoration re-identifies each PID by creation time first. Exited
processes need no restoration and retire quietly. A reused PID is stale:
it is never touched and the contract goes to ERROR with a
restoration failure. Errored contracts never retry on their own. Manual reset
first retries any retained incomplete restoration and clears ERROR only after
verification.

## Resource Ownership and Conflict Semantics

Ownership is deterministic per process lifetime and resource dimension. Nice,
CPU affinity, cgroups CPU quota, and process stopped state are independent
dimensions. Suspend and resume share the stopped-state dimension. Before
activation, the engine checks all ACTIVE or RESTORING snapshots while holding
the same lock used for activation and restoration.

If another contract owns the same resource for a matching PID, activation is
deferred in INACTIVE state and one `contract_conflict` event is recorded for
that outcome transition. The satisfied contract retries on later engine ticks
and may activate only after the owner restores or retires. It never snapshots
or overwrites the active value. Different resource dimensions may be owned by
different contracts on the same process because their snapshots and restoration
writes do not overlap.

## Conceptual runtime flow

```mermaid
flowchart LR
  State["Runtime Linux State"] --> Mon["System Monitoring"]
  Mon --> Event["Event Detection"]
  Event --> Eval["Contract Evaluation"]
  Eval --> Enf["Policy Enforcement"]
  Enf --> Res["Linux Processes and Resources"]
  Res --> Mon
  Enf --> Restore["Restoration and Continuous Monitoring"]
  Restore --> Mon
```

## Contract lifecycle

```mermaid
stateDiagram-v2
  [*] --> INACTIVE
  INACTIVE --> ACTIVATING: trigger condition satisfied
  ACTIVATING --> ACTIVE: snapshot prior state, apply actions
  ACTIVE --> RESTORING: trigger no longer applies or termination condition satisfied
  RESTORING --> INACTIVE: restore recorded prior state, emit lifecycle events
  ACTIVATING --> ERROR: activation failed, record error, roll back
  RESTORING --> ERROR: restoration failed, record error
  ERROR --> RESTORING: recover retained snapshots
  ERROR --> INACTIVE: manual reset when no restoration remains
```

`ACTIVE` is reported only after every action applied and verified.
On platforms without enforcement, satisfied triggers yield the preview
outcome `WOULD_ACTIVATE` and the lifecycle stays `INACTIVE`; previews
are never logged or displayed as enforcement.

State snapshots are taken during `ACTIVATING`, before any resource is
mutated. `RESTORING` writes back the recorded values, not assumed defaults.
For example, if a process had nice value 5, ARC records 5, may change it to
15 while active, and restores 15 back to 5 on termination. The same
principle also applies to CPU affinity, signal state, and CPU quota.

## Observability requirement

Every lifecycle transition should emit a structured event: which contract,
which trigger fired, which actions were applied, which prior values were
snapshotted, and which values were restored. This is implemented as a
bounded in-memory event history (latest 500, newest first over
`GET /api/events`) recording transitions only, never per-poll repeats,
plus Python logging. Logs are local structured
records. No external database is planned. Preview outcomes must never be
logged as enforcement.

## Concurrency considerations

The persistent engine serializes sampling, evaluation, enforcement, and
restoration under its state lock. API mutations use the same boundary.
The async loop sleeps without the lock, and WebSocket broadcasting only
reads copied engine state.

One system sample and one process enumeration are shared by every contract in a
tick. The frontend uses WebSocket telemetry while connected and avoids duplicate
REST telemetry polling; it still refreshes cached contract lifecycle and process
views at bounded intervals.

## Privilege and protection considerations

Some operations (changing another user's nice value, managing cgroups,
sending signals) require appropriate capabilities or ownership. Adapters
must check preconditions, attempt the operation, and surface failures with
context. Signal safety refuses init, ARC itself, and ARC's parent chain,
while identity-pinned processes suspended by ARC remain eligible for exact
restoration. ARC never invokes sudo and never reports success when the
kernel refused the change.

## Platform constraints

- Target runtime for enforcement is Linux.
- Development of models, API, UI, and unit tests may happen on Windows or
  macOS.
- Linux-only code must sit behind explicit interfaces so core logic can be
  unit tested elsewhere with fakes at the adapter boundary (fakes used only
  in tests, never to misreport real operations).

## What ARC deliberately does not implement

- A new kernel, kernel module, CPU scheduler, or memory manager.
- New resource-control primitives.
- Machine learning based scheduling.
- Cloud resource scheduling, external databases, or authentication.
