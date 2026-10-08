# Demo (works on Linux)

The supported primary demonstration is the GUI-driven Resource Lab described
in [FACULTY_DEMO.md](FACULTY_DEMO.md). It uses reversible CPU affinity on
controlled child processes. This page retains a smaller headless example and
explains why nice values are not a suitable unprivileged restoration demo.

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
5. In another terminal, confirm with `ps -o pid,ni,comm -p <PID>` that nice
   rises to 10. On an ordinary unprivileged account, restoration to 0 is
   expected to be denied by Linux.
6. Stop ARC with Ctrl+C. It attempts restoration and exits nonzero if cleanup
   is incomplete. Remove
   `contracts/interactive-session-relief.yaml` afterwards so the demo
   policy is not live by accident.

## Privilege caveat (read this, it is the OS lesson)

Raising a nice value (lowering priority, for example 0 to 10) normally
works for your own processes. Lowering it back (for example 10 to 0)
raises priority and the kernel may refuse it without privilege
(`CAP_SYS_NICE`, typically root). If that happens, ARC does the honest
thing: restoration fails explicitly, the contract goes to ERROR with a
`restoration_failed` event, and nothing is faked. For the complete
round trip, the process needs `CAP_SYS_NICE` or an equivalent permitted
resource limit. ARC never invokes `sudo` or elevates itself. Use Resource Lab's
CPU-affinity scenario for the reversible, unprivileged presentation path.
