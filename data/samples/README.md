# Demo documents

Small documents written for the Lumen demo and its evaluations. **Aurora Tech, Lda. is a fictional
company**: its regulations, handbook and policy are invented. The Solar System notes are common
public knowledge.

| File | Language | Type | Why it is here |
| --- | --- | --- | --- |
| `regulamento-teletrabalho.pdf` | Portuguese | PDF, 5 pages, bookmarks | Page numbers, numbered articles ("artigo 7.º"), outline headings |
| `politica-privacidade.md` | Portuguese | Markdown | Headings, legal vocabulary (RGPD) |
| `employee-handbook.md` | English | Markdown | Nested headings; overlaps with the regulation for comparison questions |
| `solar-system-notes.txt` | English | Plain text | No headings or pages; unrelated topic to test "I don't know" |

Load them with:

```bash
cd backend
uv run python -m lumen.seed
```

The seed loads every PDF, Markdown and text file in this folder except this README; the `sources/`
folder is ignored. The PDF is generated from `sources/regulamento-teletrabalho.md`. After editing the
source, rebuild it with `uv run python scripts/build_sample_pdf.py` (from `backend/`).
