# 0005. Grounded answers: numbered sources, a similarity gate and SSE

- Status: accepted
- Date: 2026-10-20

## Context

Answers must be checkable: every claim should point at a passage and page, and when the documents do
not contain the answer, Lumen must say so instead of inventing one. The default model is a small
local model (`qwen3.5:4b`), which is good at following a clear format but easily distracted.

## Decision

**Prompt.** The system prompt states the rules (use only the sources, cite with `[n]`, say you could
not find it, answer in the question's language). The user turn contains the retrieved passages as
numbered `<source id="n" document=… page=… section=…>` blocks, followed by the question. The answer
language is named explicitly ("Answer in European Portuguese"). Without it, the 4B model often
switched to English.

**Prompt-injection defence (OWASP LLM01).** Document text is HTML-escaped, so a document cannot close
its `<source>` tag or fake a new one. The system prompt tells the model that source text is data and
must never be followed as instructions.

**Citations.** `[1]`, `[2, 3]` and `[1][4]` are parsed after the answer is complete. Markers for
sources that do not exist are removed. The cited passages are returned with chunk id, document,
page, heading path and text. An answer with no valid citation is marked `grounded: false`.

**"I don't know" gate.** If the best cosine similarity among the retrieved passages is below
`LUMEN_MIN_SIMILARITY` (default **0.5**), Lumen answers "I couldn't find information about that in
the documents" in the question's language **without calling the model**. The threshold was measured
on the demo corpus with `qwen3-embedding:0.6b`:

| Questions | Best similarity |
| --- | --- |
| 10 answerable by the corpus | 0.607 – 0.839 |
| 10 unrelated (capital of France, recipes, VAT…) | 0.243 – 0.475 |

0.5 sits in the gap. The model's own "could not find it" instruction is the second line of defence
for questions that pass the gate but are not answered by the passages.

**Follow-ups.** The last few messages (`LUMEN_HISTORY_MESSAGES`, default 6) are sent as plain text.
Retrieval uses the previous user question plus the new one, so "e à sexta-feira?" still finds the
telework article.

**Streaming.** `POST /chats/{id}/messages` returns Server-Sent Events using FastAPI's native
`EventSourceResponse`: `sources`, many `delta`s, then `done` (final cleaned answer, citations,
grounded flag) and `saved` (message ids), or `error`. The turn runs in a background task that writes
to a queue, so the answer is still saved if the browser disconnects.

**Providers.** One `ChatProvider` protocol, with adapters for Ollama (default), Anthropic
(`claude-opus-5-5`, effort `medium`, server-side refusal fallback enabled) and OpenAI
(`gpt-6-luna`). Each adapter yields text deltas and then one completion with any tool calls. The
Anthropic adapter returns Claude's original content blocks, so they can be sent back unchanged within
an agent loop.

## Alternatives considered

- **Structured JSON output (answer + citation list)**: robust with large models, but small local
  models stream it poorly, and the user would wait for the whole JSON.
- **Anthropic's native document citations**: precise, but only for one provider.
- **No similarity gate, rely on the model only**: the 4B model sometimes answers from general
  knowledge (it knows the capital of France) despite the instructions.
- **`sse-starlette`**: no longer needed; FastAPI has native SSE.

## Consequences

- The threshold depends on the embedding model. Changing the model means re-measuring; the eval
  suite (M8) reports it.
- On a 4 GB GPU the 4B chat model runs partly on the CPU: about 7–15 s per answer once loaded.
  `LUMEN_CHAT_MODEL=qwen3.5:2b` is faster, and a hosted provider is faster and better.
