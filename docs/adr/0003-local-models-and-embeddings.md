# 0003. Local-first models: Ollama with Qwen, 1024-dimension embeddings

- Status: accepted
- Date: 2026-10-20

## Context

Lumen must run on a laptop at zero cost, with no deployment. The development machine has a
4 GB GPU (GTX 1650 Ti) and 16 GB of RAM. Demo documents are in Portuguese and English. Hosted
models (Anthropic, OpenAI) should stay available as an option, but must not be required.

## Decision

- **Ollama** is the default provider for both embeddings and chat.
- Embeddings use **`qwen3-embedding:0.6b`** (639 MB, multilingual, 32K context, 1024 dimensions).
  Queries get the instruction prefix Qwen3-Embedding expects; documents do not.
- Chat uses **`qwen3.5:4b`** (3.3 GB, multilingual, supports tool calling and thinking), which is
  about the largest model that fits in 4 GB of VRAM.
- The database column is **`vector(1024)`**. The OpenAI adapter asks for 1024 dimensions
  (`text-embedding-3-*` supports shortening), so both providers fit the same schema. Each document
  records which embedding model produced its vectors.
- Providers sit behind small `Protocol` interfaces (`EmbeddingProvider`, and later `ChatProvider`),
  and are chosen with environment variables.

## Alternatives considered

- **`embeddinggemma` (768 dimensions)**: also multilingual and smaller. Qwen3-Embedding was chosen
  for its longer context and because it matches the chat model family.
- **`nomic-embed-text`**: popular, but weaker on Portuguese.
- **A variable-dimension column**: pgvector's HNSW index needs a fixed dimension.

## Consequences

- Switching the embedding model to one with a different dimension needs a migration and
  re-processing all documents. Switching between models with 1024 dimensions only needs
  re-processing.
- Answer quality with a 4B model is lower than with Claude or GPT. The evaluations (M8) measure
  this, and a hosted model can be enabled with one environment variable.
