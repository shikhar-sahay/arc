# ARC helper scripts

- `faculty_demo.py`: bounded terminal fallback controller for WSL/Linux. It
  starts only tagged child processes, verifies identity before signalling, and
  cleans up on normal exit or Ctrl+C.
- `demo_cpu_worker.py`: alternating CPU workload used by the older headless
  demonstration.

The GUI-first workflow is documented in `docs/FACULTY_DEMO.md`.
