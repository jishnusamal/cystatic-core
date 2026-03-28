## Cystatic Core

Blast radius and refactor-risk analysis for code changes.

### Layout

- `source_adapters/` — fetch snapshots from GitHub, GitLab, etc.
- `language_adapters/` — per-language static analysis hooks
- `core_engine/` — dependency graph, impact scoring, refactor risk
- `api/` — FastAPI service (`uvicorn api.main:app`)
- `actions/` — GitHub Action that calls the API
- `tests/` — pytest suite