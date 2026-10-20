from itertools import pairwise

from lumen.ingestion.chunking import CHARS_PER_TOKEN, chunk_blocks, estimate_tokens
from lumen.ingestion.language import detect_language
from lumen.ingestion.parsing import Block


def _sentences(n: int, prefix: str = "Sentence") -> str:
    return " ".join(f"{prefix} number {i} has some words." for i in range(n))


def test_small_paragraphs_in_one_section_are_merged() -> None:
    blocks = [Block("One."), Block("Two."), Block("Three.")]

    chunks = chunk_blocks(blocks, chunk_size_tokens=100, overlap_tokens=0)

    assert [c.text for c in chunks] == ["One.\n\nTwo.\n\nThree."]


def test_chunks_never_cross_headings_or_pages() -> None:
    blocks = [
        Block("A1.", page=1, heading_path=("A",)),
        Block("A2.", page=2, heading_path=("A",)),
        Block("B1.", page=2, heading_path=("B",)),
    ]

    chunks = chunk_blocks(blocks, chunk_size_tokens=100, overlap_tokens=0)

    assert [(c.text, c.page, c.heading_path) for c in chunks] == [
        ("A1.", 1, ("A",)),
        ("A2.", 2, ("A",)),
        ("B1.", 2, ("B",)),
    ]


def test_long_paragraph_is_split_at_sentences_within_size() -> None:
    size_tokens = 50
    blocks = [Block(_sentences(60))]

    chunks = chunk_blocks(blocks, chunk_size_tokens=size_tokens, overlap_tokens=0)

    assert len(chunks) > 1
    assert all(len(c.text) <= size_tokens * CHARS_PER_TOKEN for c in chunks)
    assert all(c.text.endswith(".") for c in chunks)
    # Nothing is lost.
    assert " ".join(c.text for c in chunks).replace("\n\n", " ") == blocks[0].text


def test_consecutive_chunks_overlap() -> None:
    blocks = [Block(f"Paragraph {i}. " + _sentences(3, f"P{i}")) for i in range(10)]

    chunks = chunk_blocks(blocks, chunk_size_tokens=60, overlap_tokens=15)

    assert len(chunks) > 2
    for previous, current in pairwise(chunks):
        last_sentence = previous.text.rsplit(". ", 1)[-1]
        assert last_sentence in current.text


def test_word_longer_than_chunk_is_hard_cut() -> None:
    chunks = chunk_blocks([Block("x" * 1000)], chunk_size_tokens=50, overlap_tokens=0)

    assert all(len(c.text) <= 200 for c in chunks)
    assert "".join(c.text for c in chunks) == "x" * 1000


def test_estimate_tokens() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("a" * 400) == 100


def test_detect_language() -> None:
    portuguese = "O cidadão tem direito à informação e a proteção dos dados que são seus."
    english = "The citizen has the right to information and to the protection of their data."

    assert detect_language(portuguese) == "portuguese"
    assert detect_language(english) == "english"
    assert detect_language("12345 67890") == "simple"
