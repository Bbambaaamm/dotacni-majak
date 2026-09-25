from __future__ import annotations

import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .document_model import BlockKind, ParsedBlock, ParsedDocument, SourceAnchor


_WS = re.compile(r"\s+")


class HtmlDocumentError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class HtmlParserPolicy:
    max_input_bytes: int = 5 * 1024 * 1024
    max_blocks: int = 20_000
    max_text_characters: int = 2_000_000
    max_table_cells: int = 50_000

    def __post_init__(self) -> None:
        for name, value in (
            ("max_input_bytes", self.max_input_bytes),
            ("max_blocks", self.max_blocks),
            ("max_text_characters", self.max_text_characters),
            ("max_table_cells", self.max_table_cells),
        ):
            if value < 1:
                raise ValueError(f"{name} must be >= 1")


def _clean(value: str) -> str:
    return _WS.sub(" ", html.unescape(value)).strip()


class _Collector(HTMLParser):
    SKIP_TAGS = {"script", "style", "noscript", "template", "svg"}
    TEXT_TAGS = {"p", "li"}
    HEADING_TAGS = {f"h{level}" for level in range(1, 7)}

    def __init__(self, *, base_url: str | None, policy: HtmlParserPolicy) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.policy = policy
        self.blocks: list[ParsedBlock] = []
        self.warnings: list[str] = []
        self.section_path: list[str] = []
        self._skip_depth = 0
        self._active_tag: str | None = None
        self._active_text: list[str] = []
        self._active_heading_level: int | None = None
        self._paragraph_count = 0
        self._list_count = 0
        self._heading_count = 0
        self._link_count = 0
        self._table_count = 0
        self._table_rows: list[tuple[str, ...]] = []
        self._row_cells: list[str] | None = None
        self._cell_text: list[str] | None = None
        self._table_cells = 0
        self._active_link_href: str | None = None
        self._active_link_text: list[str] | None = None
        self._text_characters = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in self.HEADING_TAGS:
            self._flush_active_text()
            self._active_tag = tag
            self._active_heading_level = int(tag[1])
            self._active_text = []
            return
        if tag in self.TEXT_TAGS:
            self._flush_active_text()
            self._active_tag = tag
            self._active_heading_level = None
            self._active_text = []
            return
        if tag == "br" and self._active_tag:
            self._active_text.append("\n")
            return
        if tag == "a":
            href = dict(attrs).get("href")
            self._active_link_href = href
            self._active_link_text = []
            return
        if tag == "table":
            self._table_count += 1
            self._table_rows = []
            return
        if tag == "tr":
            self._row_cells = []
            return
        if tag in {"td", "th"}:
            self._cell_text = []
            return

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag in self.HEADING_TAGS | self.TEXT_TAGS:
            if self._active_tag == tag:
                self._flush_active_text()
            return
        if tag == "a" and self._active_link_text is not None:
            text = _clean(" ".join(self._active_link_text))
            href = self._normalize_link(self._active_link_href)
            self._active_link_href = None
            self._active_link_text = None
            if text and href:
                self._link_count += 1
                self._append_block(
                    ParsedBlock(
                        kind=BlockKind.LINK,
                        text=text,
                        link_url=href,
                        anchor=SourceAnchor(
                            locator=f"html.link.{self._link_count}",
                            section_path=tuple(self.section_path),
                        ),
                    )
                )
            return
        if tag in {"td", "th"} and self._cell_text is not None:
            value = _clean(" ".join(self._cell_text))
            if self._row_cells is not None:
                self._row_cells.append(value)
                self._table_cells += 1
                if self._table_cells > self.policy.max_table_cells:
                    raise HtmlDocumentError("HTML table cell limit exceeded")
            self._cell_text = None
            return
        if tag == "tr" and self._row_cells is not None:
            if any(cell for cell in self._row_cells):
                self._table_rows.append(tuple(self._row_cells))
            self._row_cells = None
            return
        if tag == "table":
            if self._table_rows:
                rows = tuple(self._table_rows)
                text = "\n".join(" | ".join(row) for row in rows)
                self._append_block(
                    ParsedBlock(
                        kind=BlockKind.TABLE,
                        text=text,
                        table_rows=rows,
                        anchor=SourceAnchor(
                            locator=f"html.table.{self._table_count}",
                            section_path=tuple(self.section_path),
                        ),
                    )
                )
            self._table_rows = []
            self._row_cells = None
            self._cell_text = None

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._cell_text is not None:
            self._cell_text.append(data)
        if self._active_link_text is not None:
            self._active_link_text.append(data)
        if self._active_tag is not None:
            self._active_text.append(data)

    def close(self) -> None:
        super().close()
        self._flush_active_text()

    def _flush_active_text(self) -> None:
        if self._active_tag is None:
            return
        text = _clean(" ".join(self._active_text))
        tag = self._active_tag
        level = self._active_heading_level
        self._active_tag = None
        self._active_text = []
        self._active_heading_level = None
        if not text:
            return
        if tag in self.HEADING_TAGS and level is not None:
            while len(self.section_path) >= level:
                self.section_path.pop()
            while len(self.section_path) < level - 1:
                self.section_path.append("")
            self.section_path.append(text)
            self._heading_count += 1
            self._append_block(
                ParsedBlock(
                    kind=BlockKind.HEADING,
                    text=text,
                    heading_level=level,
                    anchor=SourceAnchor(
                        locator=f"html.heading.{self._heading_count}",
                        section_path=tuple(self.section_path),
                    ),
                )
            )
            return
        if tag == "p":
            self._paragraph_count += 1
            kind = BlockKind.PARAGRAPH
            locator = f"html.p.{self._paragraph_count}"
        else:
            self._list_count += 1
            kind = BlockKind.LIST_ITEM
            locator = f"html.li.{self._list_count}"
        self._append_block(
            ParsedBlock(
                kind=kind,
                text=text,
                anchor=SourceAnchor(
                    locator=locator,
                    section_path=tuple(self.section_path),
                ),
            )
        )

    def _append_block(self, block: ParsedBlock) -> None:
        if len(self.blocks) >= self.policy.max_blocks:
            raise HtmlDocumentError("HTML block limit exceeded")
        projected = self._text_characters + len(block.text)
        if projected > self.policy.max_text_characters:
            raise HtmlDocumentError("HTML text limit exceeded")
        self._text_characters = projected
        self.blocks.append(block)

    def _normalize_link(self, href: str | None) -> str | None:
        if not href:
            return None
        value = href.strip()
        if not value or value.startswith(("#", "javascript:", "data:", "mailto:")):
            return None
        resolved = urljoin(self.base_url or "", value)
        parsed = urlsplit(resolved)
        if parsed.scheme.lower() not in {"http", "https"}:
            return None
        return resolved


def parse_html_document(
    content: bytes | str,
    *,
    base_url: str | None = None,
    policy: HtmlParserPolicy | None = None,
) -> ParsedDocument:
    policy = policy or HtmlParserPolicy()
    if isinstance(content, bytes):
        if len(content) > policy.max_input_bytes:
            raise HtmlDocumentError("HTML input exceeds max_input_bytes")
        text = content.decode("utf-8", errors="replace")
    else:
        encoded = content.encode("utf-8")
        if len(encoded) > policy.max_input_bytes:
            raise HtmlDocumentError("HTML input exceeds max_input_bytes")
        text = content

    collector = _Collector(base_url=base_url, policy=policy)
    try:
        collector.feed(text)
        collector.close()
    except (RecursionError, MemoryError) as exc:
        raise HtmlDocumentError("HTML parser resource failure") from exc

    canonical_text = "\n\n".join(
        block.text for block in collector.blocks if block.kind != BlockKind.LINK
    )
    return ParsedDocument(
        format="HTML",
        blocks=tuple(collector.blocks),
        canonical_text=canonical_text,
        metadata={
            "headings": collector._heading_count,
            "paragraphs": collector._paragraph_count,
            "list_items": collector._list_count,
            "links": collector._link_count,
            "tables": collector._table_count,
        },
        warnings=tuple(collector.warnings),
    )
