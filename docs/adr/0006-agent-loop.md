# 0006. Own bounded agent loop with four document tools

- Status: accepted
- Date: 2026-10-20

## Context

Some questions need more than one retrieval: comparing two documents, questions with several
parts, or reading the context around a passage. The answer must still cite exact passages. The loop
has to work with a small local model (`qwen3.5:4b`) as well as with Claude and GPT.

## Decision

A ~150-line loop in `lumen.agent.loop`, on top of the provider-neutral `ChatProvider`:

1. Send the history, the question (with the answer language) and the tool specs.
2. If the model returns tool calls, run each one with a **per-tool timeout** (30 s). Send the
   results back, and emit a `step` event (tool, arguments, summary, source numbers, error,
   duration).
3. Repeat for at most **5 rounds**. After that the model is told to answer and is given no tools.
   A **total timeout** (300 s) stops runaway loops.
4. When the model answers without tool calls, parse the citations.

**Tools** (`lumen.agent.tools`): `search_documents(query, documents?)`,
`get_document_section(document, page? | heading?)`, `compare_documents(question, documents[2–4])` and
`list_documents()`. Arguments are validated with Pydantic, and invalid arguments, unknown documents
and timeouts go back to the model as `Error: …` results, so it can correct itself. Documents can be
named by id, by filename, or loosely ("regulamento de teletrabalho"), because small models mangle
UUIDs.

**Citations across steps.** A `SourceRegistry` gives every passage a number the first time any tool
returns it, so `[3]` means the same passage in every step and in the final answer.

**Grounding rule.** If the tools returned no passages, the final answer is replaced by "I couldn't
find information about that in the documents". The model cannot answer from memory just by skipping
the tools.

**Streaming.** Text deltas are streamed as they come. If a step that streamed text ends in a tool
call, a `reset` event tells the client to discard that draft.

**Provider details.** The Anthropic adapter returns Claude's original content blocks (including
thinking) inside `ChatMessage.raw`. The loop sends them back unchanged, so nothing the model produced
is edited between steps.

## Alternatives considered

- **LangChain / LlamaIndex agents**: more features, but large dependencies and hidden prompts. The
  point here is a loop that is small, readable and fully tested.
- **The Anthropic SDK tool runner**: convenient, but Claude-only. Lumen must also run on Ollama and
  OpenAI.
- **Parallel tool execution**: the tools hit one local database and one local embedding model, so
  running them in parallel would not make them faster.

## Consequences

- Each extra step costs a model call: about 10–20 s with the local 4B model, about 1–3 s with hosted
  models.
- Small models sometimes merge separate sub-questions into one search, or skip the "search in the
  other language" hint. Hosted models handle multi-part questions much better. The evals measure
  this.
- Tests script tool calls with a fake provider, so the loop is tested without any model.
