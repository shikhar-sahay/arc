# Demo (works on Linux)

This demonstrates the full ARC lifecycle on a real process: condition,
evaluation, snapshot, modification, ACTIVE, restore condition, exact
restoration, and a logged trail. It needs Linux. Read-only parts work
anywhere, enforcement does not.

## What you need

- Linux (multi-core is best), Python 3.12+.
- Backend installed: `cd backend && pip install -e ".[dev]"`.
- A terminal for the worker, one for ARC, optionally one for the API.

## Steps

1. Start the workload (high load 15s, idle 15s, repeating):
   `python scripts/demo_cpu_worker.py --high-seconds 15 --low-seconds 15`.
   Note its PID.
2. Make the example live:
   `cp contracts/examples/interactive-session-relief.yaml contracts/`.
   It targets `demo_cpu_worker`, triggers above 75 percent CPU for 5s,
   applies `nice: 10`, and restores below 55 percent for 5s.
3. Run ARC headlessly: `cd backend && arc run --interval 2`.
4. Watch events: `contract_activating`, `resource_action_applied`,
   `contract_activated`, later `contract_restoring`, `resource_restored`,
   `contract_restored`.
5. In another terminal, confirm with `ps -o pid,ni,comm -p <PID>`: nice
   rises to 10 during high load and returns to its original value
   during idle, while the same PID stays alive throughout.
6. Stop ARC with Ctrl+C. ACTIVE contracts restore on exit. Remove
   `contracts/interactive-session-relief.yaml` afterwards so the demo
   policy is not live by accident.

## Privilege caveat (read this, it is the OS lesson)

Raising a nice value (lowering priority, for example 0 to 10) normally
works for your own processes. Lowering it back (for example 10 to 0)
raises priority and the kernel may refuse it without privilege
(`CAP_SYS_NICE`, typically root). If that happens, ARC does the honest
thing: restoration fails explicitly, the contract goes to ERROR with a
`restoration_failed` event, and nothing is faked. For the complete
round trip, run the demo with appropriate privilege (for example
`sudo`). Alternatively, demonstrate the reversible-without-privilege
path with CPU affinity on your own processes, after editing the CPU
list in `contracts/examples/memory-pressure-relief.yaml` to match your
host (`nproc` shows available CPUs).
