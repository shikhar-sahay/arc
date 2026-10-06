# Demo (planned)

This demo is planned and does not work yet. It describes what a complete
ARC lifecycle demonstration should prove once enforcement is
implemented. Enforcement (changing nice values, affinity, or other
process properties) does not exist yet.

## What can be shown today

Contract parsing and read-only evaluation already work without
enforcement:

1. Validate an example: `arc validate
   contracts/examples/interactive-session-relief.yaml`.
2. Start the API and open `GET /api/contracts` to see the loaded
   contract with its live preview outcome (`trigger_pending`,
   `would_activate`, or `target_not_found`).
3. Start a matching workload (for example a Python process whose
   command line contains the target substring) and watch the outcome
   change as conditions hold.
4. Confirm in the response that ARC changed nothing: outcomes are
   previews, and no resource property is modified.

## Intended setup

- A Linux host with ARC running.
- A controlled CPU workload (for example a small busy-loop process started
  for the demo).
- One resource contract loaded from `contracts/examples/`.

## Intended lifecycle

1. Start ARC.
2. Start a controlled CPU workload.
3. ARC observes the trigger condition (for example sustained CPU usage
   above the contract threshold).
4. The resource contract activates.
5. ARC records the relevant prior resource state (for example the current
   nice value and CPU affinity of the workload).
6. ARC changes a real process property such as nice value or CPU affinity.
7. The triggering condition ends.
8. ARC restores the exact recorded prior state.
9. ARC logs the complete lifecycle: activation, snapshot, actions,
   restoration, and outcome.

## Success criteria

- A real process property changes while the contract is active.
- The property returns to its recorded prior value afterwards.
- Logs show each step with enough detail to audit the decision.
- No step is simulated: failures surface as failures.

## Status

The full demo waits on the enforcement pass (action execution,
snapshots, restoration execution). Monitoring, target resolution, and
trigger evaluation are implemented and demonstrable read-only today.
