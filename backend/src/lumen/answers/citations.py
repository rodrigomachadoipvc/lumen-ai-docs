"""Find the [n] markers in an answer and map them to the passages that were shown."""

import re
from collections.abc import Sequence
from typing import Any

from lumen.retrieval.search import SearchHit

# "[1]", "[2, 3]" and "[1][4]" are all accepted.
_MARKER = re.compile(r"\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\]")


def cited_numbers(answer: str, available: int) -> list[int]:
    """Valid source numbers in order of first appearance."""
    seen: list[int] = []
    for match in _MARKER.finditer(answer):
        for part in match.group(1).split(","):
            number = int(part)
            if 1 <= number <= available and number not in seen:
                seen.append(number)
    return seen


def strip_invalid_markers(answer: str, available: int) -> str:
    """Remove markers that point at sources that do not exist (small models invent them)."""

    def keep_valid(match: re.Match[str]) -> str:
        numbers = [p.strip() for p in match.group(1).split(",")]
        valid = [n for n in numbers if 1 <= int(n) <= available]
        return f"[{', '.join(valid)}]" if valid else ""

    return re.sub(r" +(?=[.,;:!?])", "", _MARKER.sub(keep_valid, answer)).strip()


def source_payload(number: int, hit: SearchHit) -> dict[str, Any]:
    return {
        "number": number,
        "chunk_id": str(hit.chunk_id),
        "document_id": str(hit.document_id),
        "filename": hit.filename,
        "page": hit.page,
        "heading_path": list(hit.heading_path),
        "text": hit.text,
        "similarity": hit.similarity,
    }


def citations_for(answer: str, hits: Sequence[SearchHit]) -> list[dict[str, Any]]:
    return [source_payload(n, hits[n - 1]) for n in cited_numbers(answer, len(hits))]
