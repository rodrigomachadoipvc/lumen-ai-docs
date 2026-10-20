# 0004. Hybrid search with Reciprocal Rank Fusion

- Status: accepted
- Date: 2026-10-20

## Context

Questions about documents are of two kinds:

- **Exact**: "what does article 7 say?", "Olympus Mons", "RGPD". Keyword search is precise here,
  while embeddings blur numbers and names.
- **Paraphrased**: "how long do you keep billing data?" when the text says "são conservados durante
  10 anos". Embeddings find these, while keywords do not ("guardados" ≠ "conservados").

The two search methods produce scores on unrelated scales (`ts_rank_cd` against cosine similarity),
so their scores cannot simply be added.

## Decision

Run both searches in PostgreSQL and merge their **rankings** with Reciprocal Rank Fusion:

```
score(chunk) = Σ over each ranking that contains the chunk of 1 / (60 + rank)
```

- **Full-text**: one `tsquery` per language (`portuguese`, `english` and `simple` for exact words
  and numbers), OR-ed together. Inside each one, `&` is replaced by `|`, so a chunk matches if it
  contains *any* word of the question, and `ts_rank_cd` ranks chunks that match more words higher.
  Headings have weight A and body text weight B.
- **Vector**: cosine distance on the HNSW index. `hnsw.iterative_scan = strict_order` keeps
  scanning when a document filter removes candidates (pgvector ≥ 0.8).
- Each method returns 30 candidates; the fused top *k* (default 8) is returned.
- Each hit keeps its cosine similarity and its rank in each list. The answer step uses the
  similarity to decide whether the evidence is strong enough.

`POST /search` also accepts `mode: "vector" | "fulltext"`, which is useful for debugging and evals.

## Alternatives considered

- **Weighted sum of normalised scores**: needs per-corpus tuning, and min–max normalisation is
  unstable with few results.
- **Vector search only**: misses article numbers and rare names, which users quote all the time.
- **A cross-encoder reranker**: better ordering, but one more local model to run on a 4 GB GPU.
  This can be added later behind the same `search()` function.

## Consequences

- One SQL round-trip per method, and no extra service.
- The Portuguese snowball stemmer does not merge some forms ("citação"/"citações"); vector search
  covers that gap.
- RRF scores are only meaningful for ordering, not as absolute confidence.
