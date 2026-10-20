# 0008. Golden dataset, retrieval evals in CI, answer evals on demand

- Status: accepted
- Date: 2026-10-20

## Context

Retrieval settings (chunk size, fusion, the "I don't know" threshold) and prompts were first
chosen by reasoning and a handful of manual checks. Without measurement, a change that looks
harmless can quietly make answers worse. Answer quality also depends on a slow local model, so
evaluating every answer on every change is too expensive.

## Decision

- **Golden dataset** (`evals/dataset.jsonl`): questions over the demo corpus. Each answerable
  question names the document and a short passage that must be retrieved, plus a reference
  answer. The set covers Portuguese and English, cross-lingual questions, exact-term questions
  (article numbers, e-mail addresses, acronyms) and unanswerable questions.
- **Retrieval evals** (`python -m evals.run`): hit@1/3/5/8 and MRR for hybrid, vector-only and
  full-text search, plus the accuracy of the similarity gate. They run against a separate
  `<db>_evals` database with the real embedding model.
- **CI** runs the retrieval evals on every PR, with PostgreSQL and Ollama as service containers,
  and **fails if hybrid hit@5 drops below 0.90**. The JSON report is uploaded as an artifact.
- **Answer evals** (`--answers`) run on demand. Every question is answered. Unanswerable ones must
  be refused. Answerable ones are graded by an LLM judge with a fixed rubric: faithfulness to the
  shown sources (1–5) and relevance against the reference answer (1–5).

## What the evals changed

- **"I don't know" threshold 0.5 → 0.42.** With 0.5, two answerable questions were refused (best
  similarity 0.44 and 0.49). One unanswerable question ("salário mínimo nacional", 0.51) scores
  higher than some answerable ones, so no single threshold separates the two groups perfectly.
  A wrong refusal is worse than passing a question to the model, which can still say it does not
  know, so the threshold sits just below the lowest answerable question.
- **Equal RRF weights kept.** Lowering the full-text weight (0.7, 0.5, 0.3) did not improve hit@5
  or hit@8. Vector-only search has a slightly better MRR, but it cannot find "artigo 12.º" at all,
  which hybrid finds. Hybrid has the best hit@8, and that is what the model sees.
- **The dataset gained exact-term questions** after the first run showed that it had none, and
  those are the main reason hybrid search exists.

## Consequences

- The threshold and the dataset are tuned on the same small corpus, so there is a risk of
  overfitting. New documents should come with new questions.
- The LLM judge is the configured chat model. With the local 4B model its scores are noisy;
  judging with a hosted model gives more reliable numbers.
