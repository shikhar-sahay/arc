# Adaptive Resource Contracts (authoritative schema, version 1)

An Adaptive Resource Contract connects a runtime condition to resource
actions and a defined restoration condition:

Trigger, then Action(s), then Restoration.

This document describes the implemented initial schema. Contracts are
declarative configuration loaded from YAML. Runtime state (matched PIDs,
duration timers, evaluation results) is kept in memory and never written
back into YAML files.

## Top-level fields

```yaml
version: 1
id: compile-relief
name: Compilation Relief
description: Reduce contention while a compilation workload is active.
enabled: true
target: { ... }
trigger: { ... }
actions: [...]
restore: { ... }
```

- `version`: schema version. Only `1` is accepted.
- `id`: stable slug for filenames and logs. Lowercase letters, digits,
  and hyphens only, starting and ending with a letter or digit, at most
  63 characters. There are no database-generated identifiers.
- `name`: human-readable name (required).
- `description`: optional free text.
- `enabled`: boolean, defaults to true. Disabled contracts are listed
  but never evaluate toward activation.
- `target`: workload selection (process targets only, see below).
- `trigger`: condition that starts an episode (see below).
- `actions`: one or more intended actions (see below). Actions declare
  intent only. Enforcement is not implemented yet.
- `restore`: restoration condition that ends an episode (see below).

Unknown fields are rejected so typos fail loudly.

## Target

Only `process` targets exist so far. The model is extensible, but no
other target type is implemented.

```yaml
target:
  type: process
  match:
    executable: python
    command_contains: demo_cpu_worker
```

- `executable`: process name to match (optional).
- `command_contains`: substring of the joined command line (optional).
- At least one of the two is required. An empty match would select every
  process, so it is rejected.
- When both are present, both must match (AND).
- Matching is case sensitive and deterministic. All matching processes
  are returned sorted by PID. ARC never persists a PID in configuration
  because PIDs are ephemeral and may be reused.

## Conditions

Supported metrics:

- `system.cpu.percent`: total CPU utilization, 0 to 100.
- `system.memory.percent`: memory utilization, 0 to 100.
- `target.process.present`: whether any process matches the target.

Numeric metrics support `gt`, `gte`, `lt`, `lte`, `eq`, `ne` with a
numeric value in 0 to 100. The presence metric supports `eq` and `ne`
with a boolean value.

```yaml
trigger:
  metric: system.cpu.percent
  operator: gt
  value: 75
  for_seconds: 5
```

`for_seconds` (default 0) requires the raw comparison to hold
continuously for that long before the condition counts as satisfied.
One false sample resets the timer. Durations are measured on a monotonic
clock, so wall-clock adjustments cannot corrupt them. Tests advance an
injected clock value instead of sleeping.

There are no nested AND/OR conditions. One trigger and one restore
condition per contract is enough for this stage.

## Why trigger and restore are separate

The separate restoration condition provides hysteresis. For example,
activate while CPU stays above 75 percent for 5 seconds, and restore
once CPU stays below 55 percent for 5 seconds. A single threshold would
flap when usage hovers near it. Two thresholds keep the episode stable.

## Actions (intent only)

Actions are validated now but never executed in this pass.

- `nice`: `{type: nice, value: 10}`. Value must fit the Linux nice range
  of -20 to 19.
- `cpu_affinity`: `{type: cpu_affinity, cpus: [0, 1]}`. The list must be
  non-empty, with unique non-negative CPU indexes.
- `suspend`: `{type: suspend}`. No extra fields.
- `resume`: `{type: resume}`. No extra fields.

Malformed actions fail validation with a clear error.

## Restoration condition versus restoration execution

The `restore` field is a CONDITION: it decides when an active contract
should stop applying. It is not a snapshot of resource values. When
enforcement arrives, ARC will record prior values (for example the
original nice value) before changing anything, and write back those
recorded values on restoration, never assumed defaults. Snapshot
storage and restoration execution belong to the enforcement pass.

## Complete example

```yaml
version: 1
id: interactive-session-relief
name: Interactive Session Relief
description: Deprioritize a background worker while CPU stays high.
enabled: true
target:
  type: process
  match:
    executable: python
    command_contains: demo_cpu_worker
trigger:
  metric: system.cpu.percent
  operator: gt
  value: 75
  for_seconds: 5
actions:
  - type: nice
    value: 10
restore:
  metric: system.cpu.percent
  operator: lt
  value: 55
  for_seconds: 5
```

## Validation and loading behavior

- Files are parsed with a safe YAML loader. YAML content is never
  executed and cannot name Python imports or commands.
- Only direct `*.yaml`/`*.yml` files in the configured contracts
  directory are loaded, in sorted filename order.
- `contracts/examples/` is never loaded implicitly. Examples are
  documentation. Copy one to `contracts/` to make it live.
- Invalid files raise errors naming the file and the reason. They are
  never silently skipped.
- Duplicate contract IDs are rejected, naming both files.
- Validate from the command line with `arc validate <path>` (file or
  directory). Exit code 0 means valid, non-zero means failure.
