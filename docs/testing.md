# Testing ARC

ARC separates deterministic engine tests from real Linux integration tests so
the evidence is clear.

## Portable backend suite

From `backend/`:

```bash
ruff check .
ruff format --check .
pytest -v
arc validate ../contracts/examples
```

Most tests use `FakeResourceAdapter` and `FakeCgroupManager`. They verify
contract parsing, monotonic duration handling, lifecycle transitions, resource
ownership, snapshots, reverse rollback, restoration failures, PID reuse,
events, API behavior, WebSocket payloads, and persistence without claiming a
kernel operation occurred.

## Linux adapter integration

`tests/test_linux_integration.py` runs only on Linux and spawns its own child
processes. It verifies real affinity changes and exact restoration, real
SIGSTOP/SIGCONT, and a three-cycle engine affinity lifecycle. Its nice test
applies a higher numeric nice value, then skips exact restoration when the
kernel denies the priority increase needed to return to the original value.

## Opt-in Resource Lab integration

The complete API to engine to kernel scenario is intentionally opt-in because
it creates sustained CPU load for roughly half a minute:

```bash
ARC_RUN_LINUX_E2E=1 pytest -v -s tests/test_resource_lab_linux_e2e.py
```

It starts controlled workers through the same API as the GUI. One test enables
the persisted demo contract, performs three HIGH/LOW cycles, verifies active
affinity masks and exact restoration, reports measured throughput, and stops
all workers. A second test suspends a dedicated low-activity target while
separate workers maintain pressure, verifies the real stopped state, then
verifies SIGCONT restoration and safe cleanup.

## Cgroups v2

Deterministic tests cover quota conversion, movement bookkeeping, verification,
restoration, and cleanup after partial failure. A real quota test can run only
where the test user has a writable delegated cgroups v2 CPU controller enabled
for child cgroups. A mounted but read-only or non-delegated hierarchy is
reported unavailable and is not treated as successful integration evidence.

## Frontend checks

From `frontend/`:

```bash
npm run lint
npm run format:check
npm run build
```

`npm run build` includes `tsc --noEmit`. The repository currently has no
browser-test dependency. Visual claims therefore require manual browser
inspection or available browser automation in addition to these checks.

## Interpreting skips

- Platform skips mean a real Linux API cannot be exercised on that host.
- Nice restoration skips mean Linux denied the upward priority change.
- The Resource Lab end-to-end test skips unless explicitly enabled.
- A cgroup integration block is an environmental restriction, not a pass.
