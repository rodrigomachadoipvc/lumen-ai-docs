# Roadmap

Each milestone is one branch and one pull request. Do them in order: each builds on the last.
Estimated effort assumes part-time work (about 10–15 hours a week).

| # | Milestone | Branch | Effort |
| --- | --- | --- | --- |
| M0 | Repository bootstrap | `chore/m0-bootstrap` | 2–3 days |
| M1 | Document ingestion | `feat/m1-ingestion` | 3–4 days |
| M2 | Hybrid retrieval | `feat/m2-retrieval` | 3 days |
| M3 | Grounded answers with citations | `feat/m3-answers` | 3–4 days |
| M4 | Agent with tools | `feat/m4-agent` | 3 days |
| M5 | Web app | `feat/m5-frontend` | 5–7 days |
| M6 | Authentication and workspaces | `feat/m6-auth` | 3 days |
| M7 | MCP server | `feat/m7-mcp` | 2 days |
| M8 | Evaluations and observability | `feat/m8-evals` | 3–4 days |
| M9 | AWS deployment with Terraform | `feat/m9-aws` | 4–5 days |
| M10 | Polish and v1.0.0 release | `chore/m10-release` | 2–3 days |

## M0 — Repository bootstrap

Goal: a clean monorepo where CI is green from day one.

- Folder layout from `CLAUDE.md`, MIT `LICENSE`, `.gitignore`, `.editorconfig`
- Backend skeleton: FastAPI app with `/health`, settings class, structured logging, one test
- Frontend skeleton: Next.js + TypeScript strict + Tailwind + shadcn/ui, one test
- `docker-compose.yml` with PostgreSQL + pgvector (Ollama and Langfuse as optional profiles)
- Tooling: uv, ruff, mypy, pnpm, ESLint, Prettier, pre-commit
- GitHub Actions: lint, type check and test jobs for backend and frontend
- README skeleton (English) with project pitch and quick start
- Issue and PR templates

Done when: `docker compose up` + both apps run locally, and CI passes on the PR.

## M1 — Document ingestion

Goal: upload a document and store it as searchable chunks.

- Data model: `documents`, `chunks` (text, page, heading path, token count, embedding), Alembic migrations
- Parsers for PDF, Markdown and plain text, keeping page numbers and headings
- Chunking with overlap that respects headings and paragraphs; documented in an ADR
- Embedding provider interface + Ollama adapter (local) + one hosted adapter
- `POST /documents` (upload), `GET /documents`, `GET /documents/{id}`, `DELETE /documents/{id}`
- Background processing with a status field (`pending`, `processing`, `ready`, `failed`)
- Demo corpus in `data/samples/` (public-domain texts, e.g. Portuguese legislation) + a seed command
- Tests with Testcontainers PostgreSQL

## M2 — Hybrid retrieval

Goal: find the right passages for a question.

- Full-text search (PostgreSQL `tsvector`, language-aware) + vector search (pgvector HNSW)
- Reciprocal Rank Fusion to merge both result lists
- `POST /search` returning ranked chunks with scores and source metadata
- Filters by document and workspace
- Unit tests for fusion, integration tests for search quality on the demo corpus

## M3 — Grounded answers with citations

Goal: answer questions using only the retrieved passages.

- LLM provider interface + adapters (Anthropic, OpenAI, Ollama)
- Prompt that cites passages by id; response parsed into answer + citations
- "I don't know" when evidence is weak (threshold documented)
- `POST /chat` with Server-Sent Events streaming
- Conversation history stored per chat
- Prompt-injection defences: document text clearly delimited and treated as data

## M4 — Agent with tools

Goal: handle questions that need several steps.

- Tool-calling loop with a step limit and timeouts
- Tools: `search_documents`, `get_document_section`, `compare_documents`, `list_documents`
- Each tool call traced and visible in the API response (for the UI and for debugging)
- Tests with a fake provider that scripts tool calls

## M5 — Web app

Goal: a polished, accessible interface.

- Chat with streaming answers and clickable citations that open the source passage and page
- Document library: upload with progress, status, delete
- Agent steps shown as a collapsible timeline
- Responsive layout, dark mode, keyboard navigation, WCAG AA contrast
- Vitest component tests and Playwright end-to-end tests in CI

## M6 — Authentication and workspaces

Goal: several users, each with private documents.

- Sign-up and login (password hashing with Argon2, short-lived JWT + refresh token in httpOnly cookie)
- Workspaces: documents and chats scoped to the owner
- Rate limiting on chat and upload
- Authorization tests (a user can never read another user's data)

## M7 — MCP server

Goal: let other AI tools use Lumen as a knowledge source.

- MCP server with tools `search_documents`, `list_documents`, `get_document_section`
- stdio transport for local use, Streamable HTTP with token auth for remote use
- README section showing how to connect it to Claude Code, Claude Desktop and VS Code
- Tests using the SDK's in-memory client

## M8 — Evaluations and observability

Goal: measure quality instead of guessing.

- Golden dataset: 40+ questions on the demo corpus with expected passages and reference answers
- Retrieval metrics: hit@k and MRR; answer metrics: faithfulness and relevance (LLM-as-judge with a fixed rubric)
- `uv run python -m evals.run` prints a report and writes JSON; CI runs retrieval evals on every PR
- Langfuse traces for every chat (prompt, retrieved chunks, tool calls, latency, cost)
- OpenTelemetry traces and metrics for the API

## M9 — AWS deployment with Terraform

Goal: a public demo that can be created and destroyed with one command.

- Terraform modules: network, ECR, ECS Express Mode services (API and web), RDS PostgreSQL with pgvector, Secrets Manager
- Remote state (S3 with locking), separate `dev` environment
- GitHub Actions deploy on tag using OIDC (no stored AWS keys)
- Budget alarm and a documented `terraform destroy` to keep costs near zero
- Health checks, logs in CloudWatch

## M10 — Polish and v1.0.0 release

- README: demo GIF, architecture diagram (Mermaid), features, tech stack, how to run, how evals work
- ADR index, CHANGELOG, security notes (OWASP Top 10 for LLM apps)
- Badges (CI, coverage, license), GitHub release `v1.0.0`
- Pin the repository on the GitHub profile and add the project to the CV and LinkedIn
