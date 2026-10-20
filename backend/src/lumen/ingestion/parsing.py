"""Turn uploaded bytes into text blocks that remember their page and heading path.

The type is detected from the content, never trusted from the file extension alone.
"""

import io
import re
from dataclasses import dataclass, field

from markdown_it import MarkdownIt
from pypdf import PdfReader
from pypdf.generic import Destination

from lumen.db.models import DocumentType


class UnsupportedFileError(ValueError):
    """The upload is not a PDF, Markdown or UTF-8 text file."""


class ParsingError(ValueError):
    """The file looked valid but its text could not be extracted."""


@dataclass(frozen=True)
class Block:
    """A paragraph-sized piece of text and where it came from."""

    text: str
    page: int | None = None
    heading_path: tuple[str, ...] = ()


@dataclass
class ParsedDocument:
    blocks: list[Block] = field(default_factory=list)
    page_count: int | None = None

    @property
    def text(self) -> str:
        return "\n\n".join(block.text for block in self.blocks)


_MARKDOWN_EXTENSIONS = (".md", ".markdown")
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


def detect_type(data: bytes, filename: str) -> DocumentType:
    """Decide the document type from its bytes; the extension only separates Markdown from text."""
    if data.startswith(b"%PDF-"):
        return DocumentType.PDF
    if b"\x00" in data[:8192]:
        raise UnsupportedFileError("Binary files other than PDF are not supported.")
    try:
        data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UnsupportedFileError("Text files must be UTF-8 encoded.") from exc
    if filename.lower().endswith(_MARKDOWN_EXTENSIONS):
        return DocumentType.MARKDOWN
    return DocumentType.TEXT


def parse(data: bytes, doc_type: DocumentType) -> ParsedDocument:
    match doc_type:
        case DocumentType.PDF:
            return parse_pdf(data)
        case DocumentType.MARKDOWN:
            return parse_markdown(data.decode("utf-8-sig"))
        case DocumentType.TEXT:
            return parse_text(data.decode("utf-8-sig"))


# --- Plain text -----------------------------------------------------------------------


def _paragraphs(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return [p.strip() for p in _PARAGRAPH_BREAK.split(text) if p.strip()]


def parse_text(text: str) -> ParsedDocument:
    return ParsedDocument(blocks=[Block(text=p) for p in _paragraphs(text)])


# --- Markdown ---------------------------------------------------------------------------


def parse_markdown(text: str) -> ParsedDocument:
    """Split Markdown into top-level blocks, tracking the heading hierarchy above each one.

    Block text is taken from the source lines, so lists, tables and code keep their formatting.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    tokens = MarkdownIt("commonmark").enable("table").parse(text)

    headings: list[tuple[int, str]] = []  # (level, title) stack
    blocks: list[Block] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.type == "heading_open":
            level = int(token.tag[1])
            title = tokens[index + 1].content.strip()
            headings = [(lvl, t) for lvl, t in headings if lvl < level]
            headings.append((level, title))
            index += 3  # heading_open, inline, heading_close
            continue
        if token.level == 0 and token.map is not None and token.nesting in (0, 1):
            start, end = token.map
            source = "\n".join(lines[start:end]).strip()
            if source:
                blocks.append(Block(text=source, heading_path=tuple(t for _, t in headings)))
            # Skip to the matching close token so nested tokens are not added twice.
            if token.nesting == 1:
                depth = 1
                while depth and index + 1 < len(tokens):
                    index += 1
                    depth += tokens[index].nesting
        index += 1
    return ParsedDocument(blocks=blocks)


# --- PDF --------------------------------------------------------------------------------


def _clean_pdf_text(text: str) -> str:
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # re-join words hyphenated across lines
    text = re.sub(r"[ \t]+", " ", text)
    return text


def _outline_by_page(reader: PdfReader) -> list[tuple[int, tuple[str, ...]]]:
    """Flatten the PDF outline (bookmarks) into (page_index, heading path) pairs, sorted by page."""
    entries: list[tuple[int, tuple[str, ...]]] = []

    def walk(items: list[object], path: tuple[str, ...]) -> None:
        last: tuple[str, ...] = path
        for item in items:
            if isinstance(item, list):
                walk(item, last)
            elif isinstance(item, Destination):
                title = str(item.title or "").strip()
                if not title:
                    continue
                try:
                    page_index = reader.get_destination_page_number(item)
                except Exception:  # noqa: S112 - broken outline entries are common; skip them
                    continue
                if page_index is None:
                    continue
                last = (*path, title)
                entries.append((page_index, last))

    try:
        walk(list(reader.outline), ())
    except Exception:  # an unreadable outline only means no headings
        return []
    return sorted(entries, key=lambda entry: entry[0])


def _normalize(line: str) -> str:
    return " ".join(line.split()).casefold()


def _pdf_page_blocks(
    lines: list[str], page: int, heading: tuple[str, ...], titles: dict[str, tuple[str, ...]]
) -> tuple[list[Block], tuple[str, ...]]:
    """Split one page into blocks, switching heading wherever a bookmark title appears as a line."""
    blocks: list[Block] = []
    current: list[str] = []
    # A bookmark whose title is not printed on the page applies from the top of that page.
    line_keys = {_normalize(line) for line in lines}
    for key in [k for k in titles if k not in line_keys]:
        heading = titles.pop(key)

    def flush() -> None:
        if current:
            blocks.append(
                Block(text=" ".join(" ".join(current).split()), page=page, heading_path=heading)
            )
            current.clear()

    for line in lines:
        key = _normalize(line)
        if key in titles:
            flush()
            heading = titles.pop(key)
        elif not key:
            flush()  # a blank line ends a paragraph
        else:
            current.append(line)
    flush()
    return blocks, heading


def parse_pdf(data: bytes) -> ParsedDocument:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ParsingError("Encrypted PDFs are not supported.")
        outline = _outline_by_page(reader)
        blocks: list[Block] = []
        heading: tuple[str, ...] = ()
        next_entry = 0
        for page_index, page in enumerate(reader.pages):
            titles: dict[str, tuple[str, ...]] = {}
            while next_entry < len(outline) and outline[next_entry][0] <= page_index:
                path = outline[next_entry][1]
                titles.setdefault(_normalize(path[-1]), path)
                next_entry += 1
            lines = _clean_pdf_text(page.extract_text() or "").splitlines()
            page_blocks, heading = _pdf_page_blocks(lines, page_index + 1, heading, titles)
            blocks.extend(page_blocks)
        page_count = len(reader.pages)
    except ParsingError:
        raise
    except Exception as exc:
        raise ParsingError(f"Could not read the PDF: {exc}") from exc
    if not blocks:
        raise ParsingError("The PDF has no extractable text (it may be a scanned image).")
    return ParsedDocument(blocks=blocks, page_count=page_count)
