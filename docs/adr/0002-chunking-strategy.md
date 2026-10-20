# 0002. Chunk by section and page, with sentence-level overlap

- Status: accepted
- Date: 2026-10-20

## Context

Answers must cite the exact passage and page they came from, and a small local model (about 4B
parameters) has to read the retrieved passages. Chunks therefore need to be:

- small enough that 5–8 of them fit comfortably in the prompt,
- large enough to hold a complete idea (an article of a regulation, a paragraph of a guide),
- tied to one page and one heading, so a citation can point at a single place.

## Decision

1. Parsers return paragraph-sized **blocks** that carry their page (PDF) and **heading path**
   (Markdown headings, or the PDF outline/bookmarks).
2. Consecutive blocks with the same page and heading path form a **section**. A chunk never crosses
   a section boundary.
3. Inside a section, paragraphs are packed until about **350 tokens**. A paragraph that is too long
   on its own is split at sentence boundaries (`. ! ? … ; :`), and only a single word longer than a
   chunk is hard-cut.
4. When a section needs several chunks, each new chunk starts with the **last whole sentences** of
   the previous one, up to about **50 tokens** of overlap.
5. Tokens are estimated as `characters / 4`. This is cheap, deterministic and independent of the
   embedding model, and only needs to be roughly right.
6. The text that gets embedded is the heading path followed by the chunk text, so a chunk that says
   "the limit is 3 days" still carries "Telework > Limits" in its vector. The stored text stays
   unchanged for citations.

Both sizes can be changed with `LUMEN_CHUNK_SIZE_TOKENS` and `LUMEN_CHUNK_OVERLAP_TOKENS`.

## Alternatives considered

- **Fixed-size windows over the whole text**: simple, but chunks straddle headings and pages, which
  breaks single-page citations and mixes unrelated topics.
- **Exact tokenizer (tiktoken or the model's own)**: more precise, but adds a dependency (tiktoken
  downloads vocabularies at runtime) and ties chunking to one model.
- **Semantic chunking with embeddings**: better boundaries in theory, but slow on a laptop and hard
  to test deterministically.

## Consequences

- Short sections create short chunks. This is fine for retrieval and keeps citations precise.
- In PDFs a paragraph that runs across a page break becomes two chunks, one per page.
- Changing the chunk sizes only affects documents processed afterwards (use *reprocess*).
