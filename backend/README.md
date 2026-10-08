# Backend README (see docs/development.md for full instructions)

Backend for ARC (Adaptive Resource Contract Engine).

## Quick start

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows (use source .venv/bin/activate on Linux)
pip install -e ".[dev]"
uvicorn arc.api.app:app --reload --port 8000
```

Health check: `GET http://localhost:8000/api/health`

Actual enforcement requires Linux. CPU affinity and signals commonly work for
same-user child processes. Nice restoration can require `CAP_SYS_NICE`, and
CPU quota requires a writable delegated cgroups v2 CPU controller. ARC never
elevates privileges. See [development](../docs/development.md),
[testing](../docs/testing.md), and [limitations](../docs/limitations.md).
