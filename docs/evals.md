# Evaluations

Lumen's quality is measured on a fixed **golden dataset**, so changes to chunking, search, prompts
or models can be compared with numbers instead of impressions.

## The dataset

[`evals/dataset.jsonl`](../evals/dataset.jsonl) has one question per line:

```json
{"id": "tele-days", "language": "pt", "question": "Quantos dias por semana posso estar em teletrabalho?",
 "answerable": true, "expected": [{"filename": "regulamento-teletrabalho.pdf", "contains": "3 dias por semana"}],
 "reference_answer": "No máximo 3 dias por semana (artigo 7.º)."}
```

A retrieved passage counts as **relevant** when it comes from the expected file and contains the
expected text (whitespace is ignored).

| Kind | Count | Examples |
| --- | --- | --- |
| Answerable, Portuguese | 25 | articles of the telework regulation, privacy policy |
| Answerable, English | 17 | employee handbook, Solar System notes |
| Cross-language | 2 | English question about the Portuguese PDF, and the reverse |
| Exact terms | 4 | "artigo 12.º", an e-mail address, "RGPD", a product name |
| Unanswerable | 8 | capital of France, VAT rate, Bitcoin price… |

## Running the evals

From the repository root, with PostgreSQL and Ollama running:

```bash
uv run --project backend python -m evals.run             # retrieval + gate, about 1 minute
uv run --project backend python -m evals.run --answers   # + every answer judged by the LLM
uv run --project backend pytest evals                    # unit tests for the scoring code
```

The runner uses its own database, `<your database>_evals`. It creates it, migrates it and loads
`data/samples`, so your own documents never affect the scores. A JSON report with every question's
result is written to `evals/results/` (git-ignored).

## Metrics

**Retrieval**, for each search mode (hybrid, vector only, full-text only), over the answerable
questions:

- **hit@k**: the share of questions with a relevant passage in the top *k* results. The model sees
  the top 6, so hit@5 and hit@8 matter most.
- **MRR** (mean reciprocal rank): the average of 1 / rank of the first relevant passage. It rewards
  putting the right passage first.

**"I don't know" gate**: for every question, the best vector similarity is compared with
`LUMEN_MIN_SIMILARITY`. The report shows how many unanswerable questions are refused, how many
answerable ones pass, and where the two groups overlap.

**Answers** (`--answers`):

- **Cited**: share of answerable questions answered with at least one valid citation.
- **Correct refusals**: share of unanswerable questions that got "I don't know".
- **Faithfulness (1–5)**: the judge checks every claim against the passages that were shown.
- **Relevance (1–5)**: the judge compares the answer with the reference answer.

The judge uses a fixed rubric (see `JUDGE_PROMPT` in [`evals/run.py`](../evals/run.py)) and is
the configured chat model. With the local 4B model, judge scores are a rough signal. For reliable
numbers, run the answers and the judge with a hosted model (`LUMEN_CHAT_PROVIDER=anthropic`).

## Latest results

| Retrieval (48 answerable questions) | hit@1 | hit@3 | hit@5 | hit@8 | MRR |
| --- | --- | --- | --- | --- | --- |
| **Hybrid (default)** | 0.81 | 0.92 | **0.96** | **0.98** | 0.87 |
| Vector only | 0.85 | 0.94 | 0.94 | 0.96 | 0.89 |
| Full-text only | 0.71 | 0.96 | 0.96 | 0.96 | 0.82 |

| Answers (56 questions, `qwen3.5:4b`) | Result |
| --- | --- |
| "I don't know" gate accuracy | 0.98 (all answerable questions pass; 7 of 8 unanswerable refused before the model) |
| Answerable questions answered with valid citations | 0.98 |
| Unanswerable questions refused (gate + model) | 8 / 8 |
| Faithfulness / relevance (LLM judge, 1–5) | 4.94 / 5.00 (judged by the same 4B model, so read it as optimistic) |
| Median time per answer | 11.5 s |

Run on 2026-10-20 on a laptop with a GTX 1650 Ti (4 GB), Ollama `qwen3-embedding:0.6b` and
`qwen3.5:4b`, chunks of 350 tokens and a gate at 0.42.

What the numbers say:

- **Hybrid has the best hit@5/hit@8**, which is what the model sees. Vector-only puts the right
  passage first slightly more often (MRR 0.89 against 0.87), but it **cannot find "artigo 12.º" at
  all**, while hybrid finds it at rank 5.
- **Failures are safe.** The only answerable question without a cited answer is cross-language
  (`x-vacation-pt`, a Portuguese question about the English handbook). Retrieval missed the
  passage, and the model said it could not find it instead of guessing.
- **Two lines of defence for "I don't know".** "Qual é o salário mínimo nacional?" passes the
  similarity gate (0.51, it sounds like an HR question), but the model then refuses because the
  passages don't answer it.
- **Weak spots:** cross-language questions, and long compound questions with the 4B model. In a
  manual test outside the dataset, a two-part question about telework produced a wrong number
  ("5 dias" instead of 3). This is why every claim links to its passage, and why a hosted model is
  recommended when accuracy matters.

## In CI

The `evals` job in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) starts PostgreSQL and
Ollama as service containers, pulls `qwen3-embedding:0.6b`, runs the retrieval evals, uploads the
JSON report as an artifact, and **fails the build if hybrid hit@5 is below 0.90**. Answer evals are
not run in CI because they need a chat model and take a long time.

## How the evals changed Lumen

See [ADR 0008](adr/0008-evaluations.md) for the details:

- the "I don't know" threshold moved from 0.5 to **0.42**;
- equal weights in Reciprocal Rank Fusion were kept, after down-weighting full-text did not help;
- exact-term questions were added to the dataset, because the first version had none.
