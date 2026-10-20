"""Split parsed blocks into overlapping chunks that never cross a heading or a page.

See docs/adr/0002-chunking-strategy.md for the reasoning.
"""

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from itertools import groupby

from lumen.ingestion.parsing import Block

CHARS_PER_TOKEN = 4
_SENTENCE_END = re.compile(r"(?<=[.!?…;:])\s+")


def estimate_tokens(text: str) -> int:
    """Cheap, model-independent token estimate (about 4 characters per token)."""
    return max(1, round(len(text) / CHARS_PER_TOKEN))


@dataclass(frozen=True)
class ChunkDraft:
    text: str
    page: int | None
    heading_path: tuple[str, ...]
    token_count: int


def _split_long(text: str, max_chars: int) -> Iterator[str]:
    """Split one oversized paragraph at sentence boundaries, falling back to hard cuts."""
    current = ""
    for sentence in _SENTENCE_END.split(text):
        while len(sentence) > max_chars:
            cut = sentence.rfind(" ", 0, max_chars)
            cut = cut if cut > max_chars // 2 else max_chars
            if current:
                yield current
                current = ""
            yield sentence[:cut].strip()
            sentence = sentence[cut:].strip()
        if current and len(current) + 1 + len(sentence) > max_chars:
            yield current
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        yield current


def _tail(text: str, max_chars: int) -> str:
    """The last whole sentences of `text` that fit in `max_chars` (used as overlap)."""
    if max_chars <= 0:
        return ""
    tail = ""
    for sentence in reversed(_SENTENCE_END.split(text)):
        candidate = f"{sentence} {tail}".strip()
        if len(candidate) > max_chars:
            break
        tail = candidate
    return tail


def chunk_blocks(
    blocks: Iterable[Block], *, chunk_size_tokens: int, overlap_tokens: int
) -> list[ChunkDraft]:
    max_chars = chunk_size_tokens * CHARS_PER_TOKEN
    overlap_chars = min(overlap_tokens * CHARS_PER_TOKEN, max_chars // 2)
    drafts: list[ChunkDraft] = []

    for (page, heading_path), section in groupby(blocks, key=lambda b: (b.page, b.heading_path)):
        pieces: list[str] = []
        for block in section:
            if len(block.text) > max_chars:
                pieces.extend(_split_long(block.text, max_chars))
            else:
                pieces.append(block.text)

        current = ""
        for piece in pieces:
            if current and len(current) + 2 + len(piece) > max_chars:
                drafts.append(_draft(current, page, heading_path))
                overlap = _tail(current, overlap_chars)
                # Only carry the overlap if the next piece still fits next to it.
                fits = overlap and len(overlap) + 2 + len(piece) <= max_chars
                current = f"{overlap}\n\n{piece}" if fits else piece
            else:
                current = f"{current}\n\n{piece}" if current else piece
        if current:
            drafts.append(_draft(current, page, heading_path))
    return drafts


def _draft(text: str, page: int | None, heading_path: tuple[str, ...]) -> ChunkDraft:
    return ChunkDraft(
        text=text, page=page, heading_path=heading_path, token_count=estimate_tokens(text)
    )
