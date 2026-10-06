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
