# Observability

Lumen has three optional layers of observability. Everything runs locally, and none of them is
needed to use the app.

| Layer | What you get | Turn it on |
| --- | --- | --- |
| Structured logs | One JSON object per line (or readable text), for the API and uvicorn | Always on; `LUMEN_LOG_JSON=false` for readable text |
| Langfuse (LLM traces) | Every chat turn: retrieval, prompt, answer, tokens, latency, agent tool calls | `docker compose --profile langfuse up -d` and two keys |
| OpenTelemetry | Traces and HTTP metrics for every API request, over OTLP/HTTP | `LUMEN_OTEL_EXPORTER_ENDPOINT` |

## Langfuse

1. Start Langfuse. The first start takes 1–2 minutes while it runs its migrations:

   ```bash
   docker compose --profile langfuse up -d
   ```

2. The compose file creates an organisation, a project and API keys automatically. Add the keys
   to your `.env`:

   ```bash
   LUMEN_LANGFUSE_PUBLIC_KEY=pk-lf-lumen-local
   LUMEN_LANGFUSE_SECRET_KEY=sk-lf-lumen-local
   ```

3. Restart the API and ask a question. Then open <http://localhost:3001> and sign in with
   `admin@lumen.local` / `lumen-local-only`. You can change both with `LANGFUSE_ADMIN_EMAIL` /
   `LANGFUSE_ADMIN_PASSWORD` before the first start.

Each chat turn becomes one trace, and all turns of a chat share a **session** (the chat id):

```
chat-turn (chain | agent)        input: question · output: answer · metadata: grounded, citations, model
├── retrieval (retriever)        output: filename, page, section, similarity and rank of each passage
└── answer (generation)          model, full prompt, answer, input/output tokens, latency
    — or, in agent mode —
├── model-step-1 (generation)    output: text + tool calls
├── search_documents (tool)      arguments → passages
├── model-step-2 (generation)
└── …
```

The Langfuse client uses its **own** OpenTelemetry tracer provider, so LLM traces never mix with
the API's general traces.

## OpenTelemetry

Point Lumen at any OTLP/HTTP endpoint, such as an OpenTelemetry Collector, Jaeger, Grafana Alloy or
SigNoz:

```bash
LUMEN_OTEL_EXPORTER_ENDPOINT=http://localhost:4318
```

The API then exports a span for every request (except `/health`), and the standard HTTP server
metrics (request duration, active requests), with `service.name=lumen-api`.

A quick way to look at traces locally is Jaeger's all-in-one image, which accepts OTLP on 4318:

```bash
docker run --rm -p 16686:16686 -p 4318:4318 jaegertracing/jaeger:2.22.0
```

Then open <http://localhost:16686>.
