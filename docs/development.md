# Development

## Prerequisites

- Python 3.12 or newer
- Node.js 20 or newer, with npm
- Git
- Linux for actual resource enforcement (see platform note below)

## Backend setup

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate
pip install -e ".[dev]"
```

## Run the backend

```bash
cd backend
uvicorn arc.api.app:app --reload --port 8000
```

Health check: `GET http://localhost:8000/api/health`

Other read-only endpoints: `GET /api/system`, `GET /api/contracts`,
`GET /api/processes?limit=100` (limit must be 1 to 1000).

## Contract validation CLI

After installing the backend package, validate a contract file or a
directory of contracts:

```bash
cd backend
arc validate ../contracts/examples/interactive-session-relief.yaml
arc validate ../contracts/examples
```

Exit code 0 means every contract is valid. Failures name the file and
the reason.

## Live contracts versus examples

- Live contracts are YAML files placed directly in `contracts/`. The
  engine and API load only those direct files, in sorted order.
- `contracts/examples/` holds documented examples and is never loaded
  automatically. Copy an example to `contracts/` to try it as policy.
- Set `ARC_CONTRACTS_DIR` to point the API at a different directory.

## Frontend setup

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server runs on `http://localhost:5173` and proxies `/api`
requests to `http://localhost:8000`. To target a different API host, set
`VITE_ARC_API_URL` before running `npm run dev` or `npm run build`.

## Tests

Backend (from `backend/`):

```bash
pytest
```

## Linting and formatting

Backend (from `backend/`):

```bash
ruff check .
ruff format --check .
```

Frontend (from `frontend/`):

```bash
npm run lint
npm run format:check
npm run build
```

`npm run build` runs the TypeScript check (`tsc --noEmit`) followed by the
Vite production build.

## Windows development note

Ordinary API, domain-model, UI, and unit-test work runs on Windows. Linux
specific enforcement (nice values, affinity, cgroups, signals) must be
isolated behind adapters and is exercised on Linux.

## Linux runtime requirement

Actual resource management requires Linux with appropriate permissions for
the operations involved. Non-Linux hosts are for development of portable
layers only. ARC must surface enforcement failures explicitly and must
never report an unsupported operation as successful.
