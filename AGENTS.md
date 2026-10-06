# AGENTS.md

Permanent working rules for ARC. Coding agents should follow this file without
needing the full project brief restated.

## Project identity

- ARC (Adaptive Resource Contract Engine) is primarily an Operating Systems
  project, not a web application.
- ARC is a Linux user-space, event-driven policy engine for adaptive resource
  management.
- The React frontend is an observation and interaction interface only. It is
  not the core project.

## Architecture (preserve this)

- Dependency direction: Web Presentation depends on ARC API, which depends on
  ARC Core, which depends on Linux Integration, which touches Linux processes
  and resources. Never invert this direction.
- Keep policy and domain logic in `backend/src/arc`. Keep it importable and
  testable without FastAPI or React wherever practical.
- FastAPI (`backend/src/arc/api`) is an interface to the engine. It must not
  become the policy engine.
- Isolate Linux-specific behavior behind explicit interfaces or adapters so
  core logic can be unit tested on other platforms.
- Core must remain headless-capable (usable without the web UI).
- The frontend must never contain authoritative policy logic.

## Engineering

- Prefer simple, explicit code over clever or abstract code.
- Type public interfaces (Pydantic models, function signatures, TS types).
- Avoid premature abstractions and unnecessary dependencies.
- Do not add infrastructure (databases, auth, Docker, CI services, cloud
  resources) without a concrete, explicitly requested requirement.
- Do not create fake implementations. Never simulate a successful Linux
  resource operation. Surface failures explicitly.
- State restoration is first-class: when ARC changes a resource property
  (for example a nice value), it must snapshot the prior value and restore
  that exact value later, not an assumed default.
- Update or add tests when behavior changes.
- Keep docs synchronized with code changes.

## Documentation

- Never use em dashes in repository-authored prose or user-facing text.
  Use commas, colons, or separate sentences instead.
- Never claim a planned feature is implemented. Distinguish current
  implementation from planned ARC functionality.
- No marketing language, no hype, no fake production claims.
- Preserve the OS framing (processes, scheduling, affinity, signals, /proc,
  cgroups, concurrency, protection).

## Scope (do not expand without explicit request)

- No external database.
- No authentication.
- No Docker.
- No cloud infrastructure.
- No kernel module, no new scheduler, no new memory manager.
- No machine learning.

## Git

- Inspect `git status` and existing work before editing.
- Make focused commits with concise conventional messages.
- Do not rewrite unrelated user changes or remote history.
- Validate (tests, lint, type checks) before committing.
- Push completed logical work to the configured remote when available.
