# Repository Guidelines

## Project Structure & Module Organization
This repository is a multi-package RAG system. Core Python packages live in `data_module/` (ingestion, storage, indexing) and `brain_module/` (routing, retrieval orchestration, reranking, synthesis, FastAPI API). The React client lives in `frontend/src/`, with static assets in `frontend/public/`. Supporting tools are split into focused folders such as `audio/`, `record/`, `observability/`, `conference-scraper/`, and `rag-metrics-runner/`. Use the local `README.md` files inside each package before changing package-specific behavior.

## Build, Test, and Development Commands
Use the package-local tooling instead of ad hoc shell scripts when possible.

- `bash start_services.sh`: launches Neo4j, Ollama, Redis, LightRAG, the FastAPI backend, and the Vite frontend.
- `uv run --project brain_module --python 3.10 uvicorn brain_module.api.main:app --reload --port 8001`: run the backend only.
- `uv run --project data_module --python 3.10 data-pipeline --help`: inspect data ingestion commands.
- `cd frontend && pnpm dev`: start the frontend at `http://localhost:5173`.
- `cd frontend && pnpm build`: type-check and build the frontend bundle.
- `cd frontend && pnpm lint`: run ESLint on TypeScript and React files.

## Coding Style & Naming Conventions
Python targets 3.10 in the main packages. Follow PEP 8, 4-space indentation, and `snake_case` for modules, functions, and variables. Keep package boundaries clear: retrieval logic belongs under `brain_module/brain_module/retrieval/`, storage code under `data_module/data_module/storage/`. `data_module` declares `ruff`, `black`, and `mypy` in its dev extras; keep new Python code compatible with those tools even if you run them selectively.

Frontend code uses TypeScript, React 19, and ESLint. Prefer `PascalCase` for components like `AnswerCard.tsx`, `camelCase` for hooks and utilities, and colocate browser-only code under `frontend/src/`.

## Testing Guidelines
There is no committed top-level test suite yet, so new work should add targeted tests alongside the package it changes. Use `pytest` for Python packages and keep names like `test_router.py` or `test_pipeline.py`. For frontend changes, at minimum run `pnpm lint` and document any manual verification steps in the PR.

## Commit & Pull Request Guidelines
Recent history uses short, imperative commit subjects such as `Update file` and `Delete .streamlit/config.toml`. Prefer clearer messages in the same style, for example `Add LightRAG health check` or `Fix frontend microphone state`. PRs should include a concise summary, affected modules, commands run, linked issues when applicable, and screenshots for UI changes.
