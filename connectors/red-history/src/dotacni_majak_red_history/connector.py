from __future__ import annotations

import csv
import gzip
import io
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from dotacni_majak_history import HistoricalAward
from dotacni_majak_source_sdk import AdapterContext


@dataclass(frozen=True, slots=True)
class RedHistoricalSources:
    dotace_url: str = (
        "https://red.financnisprava.cz/opendata/dataset/"
        "96e09eae-5b16-47d6-9606-416b0d9eab19/resource/"
        "75e035a1-36b0-4558-be88-02e79bf9b187/download/dotace.csv.gz"
    )
    prijemce_url: str = (
        "https://red.financnisprava.cz/opendata/dataset/"
        "5d65bb4d-5694-4166-a69b-579d6ab2f5cb/resource/"
        "3f734767-2c06-47fe-87d1-c3bff1d40cd3/download/prijemce.csv.gz"
    )
    rozhodnuti_url: str = (
        "https://red.financnisprava.cz/opendata/dataset/"
        "eb331c5f-3f4f-4be7-9543-96834d12b924/resource/"
        "f4d9e003-a3f2-48a3-9cee-b7151d5d1e6d/download/rozhodnuti.csv.gz"
    )


@dataclass(frozen=True, slots=True)
class RedHistoricalImportResult:
    awards: tuple[HistoricalAward, ...]
    rejected: tuple[str, ...]
    snapshot_ids: tuple[str, ...]


class RedHistoricalConnector:
    """Imports historical non-returnable grants from official ReD CSV exports.

    ReD is historical context only. This connector never creates GrantCall
    entities and never estimates probability of receiving a future grant.
    """

    SOURCE_CODE = "MF_RED_HISTORY"

    def __init__(
        self,
        *,
        sources: RedHistoricalSources | None = None,
        ontology: Any | None = None,
    ) -> None:
        self.sources = sources or RedHistoricalSources()
        self.ontology = ontology

    async def fetch(self, ctx: AdapterContext) -> RedHistoricalImportResult:
        if ctx.snapshots is None:
            raise RuntimeError("RAW snapshot store is required")

        payloads: dict[str, bytes] = {}
        snapshot_ids: list[str] = []

        for name, url in (
            ("dotace", self.sources.dotace_url),
            ("prijemce", self.sources.prijemce_url),
            ("rozhodnuti", self.sources.rozhodnuti_url),
        ):
            response = await ctx.http.get(url)
            if response.status_code != 200:
                raise RuntimeError(
                    f"ReD source {name} returned HTTP {response.status_code}"
                )
            snapshot = ctx.snapshots.put(
                source_code=self.SOURCE_CODE,
                source_url=url,
                content=response.content,
                mime_type=response.headers.get(
                    "content-type",
                    "application/gzip",
                ),
                retrieved_at=ctx.now,
                validators={
                    "etag": response.headers.get("etag", ""),
                    "last_modified": response.headers.get(
                        "last-modified",
                        "",
                    ),
                },
            )
            payloads[name] = response.content
            snapshot_ids.append(snapshot.snapshot_id)

        return self.from_compressed_csv(
            dotace_gzip=payloads["dotace"],
            prijemce_gzip=payloads["prijemce"],
            rozhodnuti_gzip=payloads["rozhodnuti"],
            snapshot_ids=tuple(snapshot_ids),
        )

    def from_compressed_csv(
        self,
        *,
        dotace_gzip: bytes,
        prijemce_gzip: bytes,
        rozhodnuti_gzip: bytes,
        snapshot_ids: tuple[str, ...] = (),
    ) -> RedHistoricalImportResult:
        return self.from_rows(
            dotace=self._read_gzip_csv(dotace_gzip),
            prijemce=self._read_gzip_csv(prijemce_gzip),
            rozhodnuti=self._read_gzip_csv(rozhodnuti_gzip),
            snapshot_ids=snapshot_ids,
        )

    def from_rows(
        self,
        *,
        dotace: list[dict[str, str]],
        prijemce: list[dict[str, str]],
        rozhodnuti: list[dict[str, str]],
        snapshot_ids: tuple[str, ...] = (),
    ) -> RedHistoricalImportResult:
        recipients: dict[str, dict[str, str]] = {}
        for raw in prijemce:
            row = self._normalize_row(raw)
            recipient_id = self._first(
                row,
                "idprijemce",
                "iriprijemce",
                "iriprijemcepomoci",
            )
            if recipient_id:
                recipients[recipient_id] = row

        decisions: dict[str, list[dict[str, str]]] = {}
        for raw in rozhodnuti:
            row = self._normalize_row(raw)
            grant_id = self._first(row, "iddotace", "iridotace")
            if grant_id:
                decisions.setdefault(grant_id, []).append(row)

        awards: list[HistoricalAward] = []
        rejected: list[str] = []

        for raw in dotace:
            row = self._normalize_row(raw)
            grant_id = self._first(row, "iddotace", "iridotace")
            if not grant_id:
                rejected.append("DOTACE_MISSING_ID")
                continue

            project_title = self._first(
                row,
                "projektnazev",
                "nazev",
            )
            if not project_title:
                rejected.append(f"{grant_id}:MISSING_PROJECT_TITLE")
                continue

            recipient_id = self._first(
                row,
                "idprijemce",
                "iriprijemce",
                "iriprijemcepomoci",
            )
            recipient = recipients.get(recipient_id or "", {})
            recipient_name = self._recipient_name(recipient)
            if not recipient_name:
                rejected.append(f"{grant_id}:MISSING_RECIPIENT")
                continue

            grant_decisions = decisions.get(grant_id, [])
            non_returnable = [
                item
                for item in grant_decisions
                if not self._parse_bool(
                    self._first(
                        item,
                        "navratnostindikator",
                        "navratnyindikator",
                    )
                )
            ]

            # If the source explicitly contains decisions and every one is
            # returnable aid, this is not a historical grant example.
            if grant_decisions and not non_returnable:
                rejected.append(f"{grant_id}:RETURNABLE_AID_ONLY")
                continue

            amounts: list[int] = []
            years: list[int] = []
            dates: list[str] = []
            for decision in non_returnable:
                amount = self._money_minor(
                    self._first(
                        decision,
                        "castkarozhodnuta",
                        "castkapriznana",
                    )
                )
                if amount is not None:
                    amounts.append(amount)

                year = self._int_or_none(
                    self._first(decision, "rokrozhodnuti")
                )
                if year is not None:
                    years.append(year)

                date = self._date_part(
                    self._first(
                        decision,
                        "dplatnost",
                        "platnostdatum",
                    )
                )
                if date:
                    dates.append(date)

            description = self._first(
                row,
                "projektpopis",
                "popis",
            )
            ontology_terms = self._ontology_terms(
                " ".join(
                    value
                    for value in (project_title, description)
                    if value
                )
            )

            source_url = self._first(row, "iridotace") or self.sources.dotace_url
            external_id = self._stable_external_id(grant_id)

            awards.append(
                HistoricalAward(
                    id=f"red:{external_id}",
                    project_title=project_title,
                    recipient_name=recipient_name,
                    recipient_ico=self._first(recipient, "ico"),
                    currency_code="CZK",
                    source_url=source_url,
                    project_description=description,
                    grant_amount_minor=sum(amounts) if amounts else None,
                    decision_date=max(dates) if dates else None,
                    award_year=max(years) if years else None,
                    ontology_terms=ontology_terms,
                )
            )

        awards.sort(
            key=lambda award: (
                -(award.award_year or 0),
                award.project_title.casefold(),
                award.id,
            )
        )
        return RedHistoricalImportResult(
            awards=tuple(awards),
            rejected=tuple(rejected),
            snapshot_ids=snapshot_ids,
        )

    def _ontology_terms(self, text: str) -> tuple[str, ...]:
        if self.ontology is None or not text.strip():
            return ()
        resolved = self.ontology.resolve(text)
        return tuple(sorted(resolved))

    @staticmethod
    def _read_gzip_csv(payload: bytes) -> list[dict[str, str]]:
        try:
            raw = gzip.decompress(payload)
        except OSError as exc:
            raise ValueError("invalid gzip payload") from exc

        text: str
        for encoding in ("utf-8-sig", "cp1250"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("CSV payload is neither UTF-8 nor CP1250")

        sample = text[:8192]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
            dialect.delimiter = ";"

        return [
            {str(key): (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(io.StringIO(text), dialect=dialect)
        ]

    @staticmethod
    def _normalize_row(row: dict[str, str]) -> dict[str, str]:
        return {
            str(key).replace("\ufeff", "").strip().casefold(): value.strip()
            for key, value in row.items()
            if key is not None
        }

    @staticmethod
    def _first(row: dict[str, str], *keys: str) -> str | None:
        for key in keys:
            value = row.get(key.casefold(), "").strip()
            if value:
                return value
        return None

    @classmethod
    def _recipient_name(cls, row: dict[str, str]) -> str | None:
        business = cls._first(row, "obchodnijmeno", "nazev")
        if business:
            return business
        parts = [
            cls._first(row, "jmeno"),
            cls._first(row, "prijmeni"),
        ]
        joined = " ".join(part for part in parts if part)
        return joined or None

    @staticmethod
    def _parse_bool(value: str | None) -> bool:
        if value is None or not value.strip():
            return False
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "ano", "yes"}:
            return True
        if normalized in {"false", "0", "ne", "no"}:
            return False
        raise ValueError(f"unknown boolean value {value!r}")

    @staticmethod
    def _money_minor(value: str | None) -> int | None:
        if value is None or not value.strip():
            return None
        normalized = (
            value.strip()
            .replace("\u00a0", "")
            .replace(" ", "")
            .replace(",", ".")
        )
        try:
            amount = Decimal(normalized)
        except InvalidOperation as exc:
            raise ValueError(f"invalid money value {value!r}") from exc
        minor = amount * 100
        if minor != minor.to_integral_value():
            raise ValueError(
                f"money value {value!r} has sub-minor-unit precision"
            )
        if minor < 0:
            raise ValueError("historical grant amount must not be negative")
        return int(minor)

    @staticmethod
    def _int_or_none(value: str | None) -> int | None:
        if value is None or not value.strip():
            return None
        return int(value.strip())

    @staticmethod
    def _date_part(value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        candidate = value.strip()[:10]
        try:
            datetime.fromisoformat(candidate)
        except ValueError:
            return None
        return candidate

    @staticmethod
    def _stable_external_id(value: str) -> str:
        return value.rstrip("/").rsplit("/", 1)[-1]
