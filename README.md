# Lumen

[![CI](https://github.com/rodrigomachadoipvc/lumen-ai-docs/actions/workflows/ci.yml/badge.svg)](https://github.com/rodrigomachadoipvc/lumen-ai-docs/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Ask questions about your documents and get answers you can check.**

Lumen lets you upload PDFs, Markdown and text files and ask questions about them. Every answer is grounded
in your documents and cites the exact passages and pages it used. When the documents do not contain the
answer, Lumen says so instead of guessing.

> Status: early development. See the [roadmap](docs/ROADMAP.md).

## Features (planned)

- Hybrid search: PostgreSQL full-text + pgvector, merged with Reciprocal Rank Fusion
- Grounded answers with clickable citations, streamed to the browser
- An agent that can search, compare and read document sections in several steps
- An MCP server, so Claude Code, Claude Desktop and VS Code can use Lumen as a knowledge source
- Evaluations in CI that measure retrieval and answer quality on every change

## Tech stack

FastAPI · Pydantic v2 · SQLAlchemy 2 · PostgreSQL 18 + pgvector · Next.js · TypeScript · Tailwind CSS ·
shadcn/ui · Ollama / Anthropic / OpenAI · Langfuse · GitHub Actions · AWS (Terraform)

The design is described in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and decisions are recorded in
[docs/adr/](docs/adr/).

## Quick start

Requirements: [Docker](https://docs.docker.com/get-docker/), [uv](https://docs.astral.sh/uv/),
Node.js 24+, [pnpm](https://pnpm.io/installation) and [Ollama](https://ollama.com/download).

```bash
cp .env.example .env
docker compose up -d                 # PostgreSQL + pgvector on localhost:5432
ollama pull qwen3-embedding:0.6b     # embeddings (639 MB)
ollama pull qwen3.5:4b               # chat model (3.3 GB)

cd backend
uv sync
uv run alembic upgrade head          # create the tables
uv run python -m lumen.seed          # optional: load the demo documents in data/samples
uv run uvicorn lumen.main:app --reload  # API on http://localhost:8000 (docs at /docs)

cd ../frontend
pnpm install
pnpm dev                             # web app on http://localhost:3000
```

Optional services:

```bash
docker compose --profile ollama up -d    # Ollama in a container (host port 11435)
docker compose --profile langfuse up -d  # Langfuse on http://localhost:3001
```

## Development

```bash
# Backend
cd backend
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest

# Frontend
cd frontend
pnpm lint && pnpm format:check
pnpm typecheck
pnpm test

# Git hooks (once per clone)
uv tool install pre-commit
pre-commit install
```

## Repository layout

```
backend/        FastAPI app (src/lumen/...), tests
frontend/       Next.js app
mcp-server/     MCP server exposing Lumen search as tools
evals/          golden dataset and evaluation scripts
infra/          Terraform (AWS)
docs/           roadmap, architecture, ADRs
data/samples/   small public-domain demo documents
```

## License

[MIT](LICENSE) © Rodrigo Machado
