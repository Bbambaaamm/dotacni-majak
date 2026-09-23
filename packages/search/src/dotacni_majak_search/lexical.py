from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass


_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def build_fts_query(text: str, *, prefix: bool = False) -> str:
    """Convert user text into a safe FTS5 AND query.

    Raw FTS operators are never passed through. Only Unicode word tokens are
    retained and each token is quoted. This prevents malformed MATCH syntax
    and avoids exposing FTS5 query-language features to public user input.
    """

    tokens = [token.casefold() for token in _TOKEN_RE.findall(text)]
    if not tokens:
        return ""

    parts: list[str] = []
    for token in tokens:
        quoted = '"' + token.replace('"', '""') + '"'
        if prefix and len(token) >= 3:
            quoted += "*"
        parts.append(quoted)

    return " ".join(parts)


@dataclass(frozen=True, slots=True)
class LexicalSearchHit:
    grant_call_version_id: str
    title: str
    summary: str
    status: str
    submission_close_at: str | None
    score: float


class SqliteLexicalSearch:
    """Reference FTS5 implementation compatible with D1 SQL semantics."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def search(
        self,
        text: str,
        *,
        statuses: tuple[str, ...] = ("OPEN", "PLANNED", "ANNOUNCED"),
        limit: int = 20,
    ) -> list[LexicalSearchHit]:
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        if not statuses:
            return []

        query = build_fts_query(text, prefix=True)
        if not query:
            return []

        placeholders = ",".join("?" for _ in statuses)
        sql = f"""
          SELECT
            d.grant_call_version_id,
            d.title,
            d.summary,
            d.status,
            d.submission_close_at,
            bm25(
              grant_search_fts,
              0.0,
              4.0,
              1.5,
              3.0,
              1.5,
              2.5
            ) AS rank
          FROM grant_search_fts
          JOIN grant_search_documents d
            ON d.grant_call_version_id = grant_search_fts.grant_call_version_id
          WHERE grant_search_fts MATCH ?
            AND d.status IN ({placeholders})
          ORDER BY rank ASC, d.grant_call_version_id ASC
          LIMIT ?
        """
        rows = self.connection.execute(
            sql,
            (query, *statuses, limit),
        ).fetchall()

        return [
            LexicalSearchHit(
                grant_call_version_id=row[0],
                title=row[1],
                summary=row[2],
                status=row[3],
                submission_close_at=row[4],
                score=float(row[5]),
            )
            for row in rows
        ]
