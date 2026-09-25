from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BlockKind(str, Enum):
    HEADING = "HEADING"
    PARAGRAPH = "PARAGRAPH"
    LIST_ITEM = "LIST_ITEM"
    TABLE = "TABLE"
    LINK = "LINK"


@dataclass(frozen=True, slots=True)
class SourceAnchor:
    """Deterministic parser-local anchor for provenance."""

    locator: str
    page: int | None = None
    section_path: tuple[str, ...] = ()
    row: int | None = None
    cell: int | None = None
    field_path: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedBlock:
    kind: BlockKind
    text: str
    anchor: SourceAnchor
    heading_level: int | None = None
    link_url: str | None = None
    table_rows: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    format: str
    blocks: tuple[ParsedBlock, ...]
    canonical_text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    @property
    def text_characters(self) -> int:
        return len(self.canonical_text)
