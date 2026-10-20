import pytest

from lumen.db.models import DocumentType
from lumen.ingestion.parsing import (
    ParsingError,
    UnsupportedFileError,
    detect_type,
    parse,
    parse_markdown,
    parse_pdf,
    parse_text,
)
from tests.pdf_factory import make_pdf


class TestDetectType:
    def test_pdf_is_detected_from_content_not_extension(self) -> None:
        assert detect_type(make_pdf([["Hello"]]), "notes.txt") is DocumentType.PDF

    def test_markdown_needs_a_markdown_extension(self) -> None:
        assert detect_type(b"# Title", "readme.md") is DocumentType.MARKDOWN
        assert detect_type(b"# Title", "readme.txt") is DocumentType.TEXT

    def test_binary_files_are_rejected(self) -> None:
        with pytest.raises(UnsupportedFileError):
            detect_type(b"\x89PNG\r\n\x1a\n\x00\x00", "image.pdf")

    def test_non_utf8_text_is_rejected(self) -> None:
        with pytest.raises(UnsupportedFileError):
            detect_type("olá".encode("utf-16"), "a.txt")


def test_plain_text_splits_on_blank_lines() -> None:
    parsed = parse_text("First paragraph\nstill first.\n\n\nSecond.\r\n\r\nThird.")

    assert [b.text for b in parsed.blocks] == ["First paragraph\nstill first.", "Second.", "Third."]
    assert all(b.page is None and b.heading_path == () for b in parsed.blocks)


def test_markdown_tracks_heading_hierarchy() -> None:
    source = (
        "Intro text.\n\n"
        "# Chapter 1\n\nAlpha.\n\n"
        "## Section 1.1\n\n- item one\n- item two\n\n"
        "# Chapter 2\n\n```python\nprint('x')\n```\n"
    )

    blocks = parse_markdown(source).blocks

    assert [(b.text, b.heading_path) for b in blocks] == [
        ("Intro text.", ()),
        ("Alpha.", ("Chapter 1",)),
        ("- item one\n- item two", ("Chapter 1", "Section 1.1")),
        ("```python\nprint('x')\n```", ("Chapter 2",)),
    ]


def test_pdf_keeps_page_numbers_and_outline_headings() -> None:
    data = make_pdf(
        [["Page one text."], ["Page two first.", "Page two second."], ["Page three."]],
        outline=[("Introduction", 0), ("Rules", 1)],
    )

    parsed = parse_pdf(data)

    assert parsed.page_count == 3
    pages = [(b.page, b.heading_path) for b in parsed.blocks]
    assert (1, ("Introduction",)) in pages
    assert (2, ("Rules",)) in pages
    assert (3, ("Rules",)) in pages  # heading stays in force until the next bookmark
    assert "Page two second." in parsed.text


def test_pdf_without_text_fails_clearly() -> None:
    with pytest.raises(ParsingError, match="no extractable text"):
        parse_pdf(make_pdf([[""]]))


def test_corrupt_pdf_fails_clearly() -> None:
    with pytest.raises(ParsingError):
        parse(b"%PDF-1.4 not really a pdf", DocumentType.PDF)


def test_pdf_switches_heading_where_a_bookmark_title_is_printed() -> None:
    data = make_pdf(
        [["Chapter A", "Alpha body.", "Chapter B", "Beta body."], ["Still beta."]],
        outline=[("Chapter A", 0), ("Chapter B", 0)],
    )

    blocks = parse_pdf(data).blocks

    assert [(b.text, b.page, b.heading_path) for b in blocks] == [
        ("Alpha body.", 1, ("Chapter A",)),
        ("Beta body.", 1, ("Chapter B",)),
        ("Still beta.", 2, ("Chapter B",)),
    ]
