# ARC Faculty Demonstration

This demonstration runs inside WSL2 Ubuntu and uses only controlled child
processes. It does not require root for telemetry, CPU affinity, or signals.
The cgroups v2 quota action is optional because WSL delegation varies.

## Prerequisites

From `~/projects/arc`:

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -e 'backend[dev]'
cd frontend && npm install && cd ..
```

Start the backend and frontend in separate terminals:

```bash
ARC_CONTRACTS_DIR=contracts backend/.venv/bin/uvicorn arc.api.app:app --host 127.0.0.1 --port 8000
```

```bash
cd frontend
npm run dev -- --host 0.0.0.0
```

Open the printed frontend URL. Measurements describe the WSL Linux virtual
machine, not native Windows processes.

## Primary GUI Demonstration

The Resource Lab is the primary demonstration. It creates only backend-owned,
uniquely tagged Linux child processes. The foreground worker continuously
reports measured operations per second. Background workers remain idle during
the baseline phase and perform the same bounded computation during pressure.

1. Open **Resource Lab** and select 6 to 10 background workers. Use fewer on a
   smaller WSL VM.
2. Select **Start Scenario**. Wait for a stable foreground baseline.
3. Select **Enable Policy**. This enables the normal persisted
   `resource-lab-cpu-contention` contract. It does not apply resource controls
   directly.
4. Select **Apply Pressure**. Watch real system CPU, foreground throughput,
   background throughput, target PIDs, and the trigger-duration progress.
5. After three sustained seconds above 20 percent CPU, verify that the contract
   becomes ACTIVE and every background PID reports the policy CPU as its
   allowed set.
6. Select **Lower Pressure**. Background processes remain alive but idle, so
   ARC can verify their identities and restore their exact original affinity.
7. Wait for INACTIVE. Confirm that Current CPUs and Original CPUs agree, then
   open **Audit Log** to show snapshot, enforcement, verification, restoration,
   and lifecycle events.
8. Select **Stop Scenario**. ARC refuses this operation while resources remain
   owned, so workers cannot be discarded before recovery.

The throughput comparison is measured, not synthesized. Scheduling noise can
change the direction and magnitude of the foreground result. CPU affinity
isolates eligible processors but does not reserve capacity or impose a quota.

Independent verification remains optional:

```bash
taskset -pc <background-pid>
grep -E 'State|Cpus_allowed_list' /proc/<background-pid>/status
```

For the secondary workbench, copy either
`contracts/examples/resource-lab-suspend.yaml` or
`contracts/examples/resource-lab-affinity-conflict.yaml` into `contracts/`,
reload on the Contracts page, and enable it only while Resource Lab workers are
running. The suspension policy exercises verified SIGSTOP and SIGCONT. The
conflict policy demonstrates that a second affinity owner defers rather than
overwriting the active policy.

## Terminal Fallback Preflight

```bash
cd ~/projects/arc
uname -a
command -v python3 taskset curl
curl -fsS http://127.0.0.1:8000/api/status | python3 -m json.tool
python3 scripts/faculty_demo.py start
python3 scripts/faculty_demo.py status
```

`start` creates one idle target and a bounded number of CPU load workers. It
prints the target PID, original affinity, measured HIGH-phase CPU use, and
independent verification commands. Repeating it replaces only recorded load
workers. PID plus Linux start time and a unique command token are checked before
any process is signalled.

If HIGH does not exceed 20 percent, run:

```bash
python3 scripts/faculty_demo.py high --workers 8
```

If LOW does not fall below 10 percent, tune the copied example contract after
measuring both phases. Keep a clear gap between trigger and restore thresholds.

## Five to Seven Minute Sequence

### A. CPU Load and Live Telemetry

1. Open **Overview** and identify CPU, memory, logical processors, and history.
2. Run `python3 scripts/faculty_demo.py high --workers 6`.
3. Show the real aggregate CPU rise and per-core activity.
4. Run `python3 scripts/faculty_demo.py low` and show recovery.

### B. Affinity Enforcement and Exact Restoration

Copy the primary contract and reload from the Contracts page:

```bash
cp contracts/examples/faculty-affinity-demo.yaml contracts/faculty-affinity-demo.yaml
python3 scripts/faculty_demo.py high --workers 6
python3 scripts/faculty_demo.py status
```

Use the printed PID as `<PID>`:

```bash
taskset -pc <PID>
grep -E 'State|Cpus_allowed_list' /proc/<PID>/status
```

Expected observations:

1. The contract becomes ACTIVE after the trigger duration.
2. Audit Log records snapshot capture, verified application, and activation.
3. `taskset` reports CPU 0 while active.
4. Run `python3 scripts/faculty_demo.py low`.
5. The contract returns to INACTIVE and Audit Log records restoration.
6. `taskset` reports the exact original affinity printed by `start`.

Remove the copied example only after restoration and INACTIVE state:

```bash
rm contracts/faculty-affinity-demo.yaml
```

### C. SIGSTOP and SIGCONT

Use this example separately from the affinity contract:

```bash
cp contracts/examples/faculty-suspend-demo.yaml contracts/faculty-suspend-demo.yaml
python3 scripts/faculty_demo.py high --workers 6
grep '^State:' /proc/<PID>/status
```

The active state should be `T` or `t`. Restore and verify:

```bash
python3 scripts/faculty_demo.py low
grep '^State:' /proc/<PID>/status
```

The process should return to a non-stopped state. ARC verifies PID plus creation
time and refuses to suspend itself, its parent chain, or unsafe targets.

### D. Conflict Safety

Copy both affinity examples, reload, and start HIGH load:

```bash
cp contracts/examples/faculty-affinity-demo.yaml contracts/faculty-affinity-demo.yaml
cp contracts/examples/faculty-affinity-conflict.yaml contracts/faculty-affinity-conflict.yaml
python3 scripts/faculty_demo.py high --workers 6
```

Only one contract may own CPU affinity for that process lifetime. The other
remains INACTIVE with a `contract_conflict` audit event and retries after the
owner restores. It never overwrites the active setting. Contracts controlling
different dimensions, such as nice and affinity, may coexist.

## Troubleshooting

- **No trigger:** compare HIGH and LOW measurements, tune the copied YAML, then
  reload from disk.
- **Wrong CPU number:** use a CPU listed by `taskset -pc <PID>`. Restricted
  environments can exclude CPU 0.
- **Permission denied:** show the truthful Audit Log failure. ARC never invokes
  sudo. Lowering nice or writing cgroups can require additional permission.
- **cgroups unavailable:** affinity and signals still work. Detection does not
  prove that a later kernel write will succeed.
- **Reload blocked:** wait for restoration. Active definitions are protected.
- **Backend unavailable:** verify `curl http://127.0.0.1:8000/api/status`.

## Cleanup and Recovery

First request restoration, wait for INACTIVE, then stop owned workers:

```bash
python3 scripts/faculty_demo.py low
python3 scripts/faculty_demo.py status
python3 scripts/faculty_demo.py stop
```

Remove only demo copies deliberately placed in `contracts/`. The controller
never deletes contracts or signals processes it did not create.

## What This Demonstrates

ARC is not only a monitoring dashboard. Its headless engine samples Linux,
evaluates declarative conditions with monotonic duration tracking, resolves
targets, snapshots kernel-visible state, applies and reads back controls, and
restores exact prior values. PID plus creation time protects against PID reuse.
A reverse journal handles partial activation. Resource-level ownership prevents
overlapping contracts from overtaking each other. The UI observes the persistent
engine and manages contracts; it does not enforce policy.

## Honest Limitations

- Snapshots are in memory. An ungraceful process or host crash cannot restore
  state after restart.
- Nice restoration can be denied when it requires raising priority.
- cgroups v2 quota needs a writable delegation and is not guaranteed by
  detection alone.
- Audit history is bounded and in memory, not durable or tamper-proof.
