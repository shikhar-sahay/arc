# Contributing to ARC

## Setup

See `docs/development.md` for prerequisites and reproducible setup steps for
the backend and frontend.

## Branches

- Work on short-lived feature branches branched from `main`.
- Keep each branch focused on one logical change.

## Commits

- Write concise conventional messages (for example `feat:`, `fix:`,
  `docs:`, `chore:`, `test:`).
- Prefer a small number of meaningful commits over one commit per file.
- Do not commit `node_modules`, virtual environments, caches, build output,
  secrets, or IDE-specific files.

## Testing and quality

- Add or update tests with behavior changes.
- Backend: `pytest`, `ruff check`, `ruff format --check`.
- Frontend: `npm run build`, `npm run lint`, `npm run format:check`.
- Validate before committing.

## Documentation

- Update the relevant docs with each behavior or interface change.
- Never claim planned features are implemented.
- Never use em dashes in repository prose.

## Scope

- Do not silently expand project scope (new infrastructure, new subsystems,
  new dependencies) without discussion. ARC is a university OS project with
  a fixed architecture: Core, API, Web, and Linux Integration.
