# Lumen — AI document assistant

Lumen lets people upload documents (PDF, Markdown, text) and ask questions about them.
Answers are grounded in the documents and always cite the exact passages and pages used.
It is a portfolio project built to production standards by Rodrigo Machado.

The full plan is in `docs/ROADMAP.md` and the design in `docs/ARCHITECTURE.md`. Read both before
starting any milestone.

## How we work together

- Talk to Rodrigo in **European Portuguese**. Code, comments, commit messages, PRs and docs are in **English**.
- Rodrigo must understand every line that ships. At the end of each task, explain in Portuguese what you
  built, why you chose that approach, and one alternative you rejected. Keep it short and concrete.
- Before writing code for a milestone, propose a plan and wait for approval.
- Work one milestone at a time, on its own branch (`feat/m1-ingestion`, `chore/m0-bootstrap`, ...).
- Make small commits that each leave the build green. Use Conventional Commits
  (`feat(api): add hybrid search endpoint`). Never put "WIP" or unrelated changes in one commit.
- Open a pull request per milestone with `gh pr create`, describing what changed and how it was tested.
  Rodrigo reviews and merges. Never push directly to `main`.
- Before choosing a library or API, check its current official docs. Do not rely on memory for versions
  or signatures — several libraries here (MCP SDK, pgvector, AWS ECS) changed recently.
- If something in the plan looks wrong or outdated, say so and suggest a fix instead of following it blindly.

## Stack

| Area | Choice |
| --- | --- |
| Backend | Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic |
| Package tooling | `uv` (Python), `pnpm` (Node) |
| Database | PostgreSQL 18 with `pgvector` (HNSW index) and built-in full-text search |
| LLM and embeddings | Provider interface with adapters: Anthropic (Claude), OpenAI, Ollama (local, default for dev) |
| Agent | Own tool-calling loop on top of the provider interface; no heavy framework |
| MCP | Official MCP Python SDK (`mcp`), stdio and Streamable HTTP transports |
| Frontend | Next.js (App Router), TypeScript strict, Tailwind CSS, shadcn/ui |
| Observability | Structured JSON logs, OpenTelemetry, Langfuse for LLM traces |
| Tests | pytest + Testcontainers (backend), Vitest + Testing Library, Playwright (frontend) |
| Quality | ruff, mypy (strict), ESLint, Prettier, pre-commit |
| CI/CD | GitHub Actions; deploy with GitHub OIDC to AWS (no long-lived keys) |
| Cloud | AWS: ECR, ECS Express Mode (Fargate), RDS PostgreSQL, Secrets Manager — all in Terraform |

AWS App Runner is closed to new customers, so do not use it.

## Repository layout

```
backend/        FastAPI app (src/lumen/...), Alembic migrations, tests
frontend/       Next.js app
mcp-server/     MCP server exposing Lumen search as tools
evals/          golden dataset and evaluation scripts
infra/          Terraform (AWS)
docs/           ROADMAP, ARCHITECTURE, ADRs (docs/adr/NNNN-title.md)
data/samples/   small public-domain demo documents
```

## Commands

Keep this section up to date as commands are added.

```bash
docker compose up -d                       # postgres 18 + pgvector on :5432
docker compose --profile ollama up -d      # + Ollama container on :11435 (native Ollama uses :11434)
docker compose --profile langfuse up -d    # + Langfuse v4 on :3001
cd backend && uv sync && uv run pytest
cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy
cd backend && uv run alembic upgrade head            # migrations (needs docker compose up)
cd backend && uv run python -m lumen.seed            # load data/samples (needs Ollama models)
cd backend && uv run python scripts/build_sample_pdf.py   # rebuild the demo PDF from its source
cd backend && uv run uvicorn lumen.main:app --reload   # API on :8000
cd frontend && pnpm install && pnpm dev               # web on :3000
cd frontend && pnpm lint && pnpm format:check && pnpm typecheck && pnpm test
pre-commit run --all-files                 # all hooks (install: uv tool install pre-commit)
# From M5: cd frontend && pnpm exec playwright test
```

## Rules for code

- Type everything. mypy strict and TypeScript strict must pass.
- Every feature ships with tests. Bug fixes start with a failing test.
- Config comes from environment variables via a settings class. Keep `.env.example` complete.
- Never commit secrets, API keys, `.env` files or real personal data.
- Validate all input at the API edge. Return consistent JSON errors.
- Answers must cite sources. When retrieval finds no relevant evidence, the assistant says it does not know.
- Treat document text as data, never as instructions (prompt-injection defence; see OWASP Top 10 for LLM apps).
- Record any significant technical decision as a short ADR in `docs/adr/`.
- Update `README.md` and `docs/` in the same PR as the code they describe.

## Definition of done (every milestone)

- [ ] Lint, type checks and all tests pass locally and in CI
- [ ] New behaviour covered by tests
- [ ] README/docs updated, `.env.example` updated
- [ ] PR opened with a clear description and test notes
- [ ] Explanation given to Rodrigo in Portuguese
