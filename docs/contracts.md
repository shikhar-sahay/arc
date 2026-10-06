# Adaptive Resource Contracts (concept)

An Adaptive Resource Contract connects a runtime condition to resource
actions and a defined restoration behavior:

Trigger, then Action(s), then Restoration.

## Elements of a contract

- **Identity**: a stable name so logs and events can refer to the contract.
- **Target workload**: which process or group the contract applies to
  (selection criteria are defined in a later architecture pass).
- **Trigger condition**: the runtime condition that activates the contract
  (for example sustained high CPU usage by the target).
- **Actions**: one or more resource-management operations applied through
  existing Linux mechanisms (for example adjusting nice value or CPU
  affinity).
- **Termination condition**: when the contract stops applying (trigger no
  longer holds, an explicit stop, or a separate restoration condition).
- **Restoration behavior**: which prior values ARC recorded and must write
  back when the contract ends.

## Conceptual example

Suppose a background compile job competes with an interactive session.
A contract could read as: when the interactive session is active, lower
the compile job scheduling priority, and when the session ends, restore
the compile job to the exact priority it had before.

The key point is restoration of recorded state: if the compile job had
nice value 5, ARC restores 5, not an assumed default such as 0.

## Status

This document is conceptual. The contract schema (YAML fields, matching
rules, condition language) will be architected separately before
implementation. Nothing here should be read as a frozen schema, and no
contract evaluation is implemented yet.
