# Demo (planned)

This demo is planned and does not work yet. It describes what a complete
ARC lifecycle demonstration should prove once the engine is implemented.

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

The engine pieces required for this demo (monitoring, evaluation,
enforcement, restoration) are not implemented in this bootstrap pass.
