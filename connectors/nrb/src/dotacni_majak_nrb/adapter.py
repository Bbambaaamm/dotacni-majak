from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from dotacni_majak_source_sdk import (
    AdapterContext,
    ArtifactFetchResult,
    AuthorityLevel,
    DiscoveryItem,
    DiscoveryPage,
    FetchState,
    FetchValidators,
    HealthReport,
    HealthStatus,
    NativeRecord,
    RecordFetchResult,
    RemoteArtifactRef,
    RetrievalMode,
    SourceAdapter,
    SourceCheckpoint,
    SourceDescriptor,
)


LOANS_INDEX = "https://www.nrb.cz/podnikatele/uvery/"
GUARANTEES_INDEX = "https://www.nrb.cz/podnikatele/zaruky/"
_ALLOWED_HOSTS = {"nrb.cz", "www.nrb.cz"}

_PRODUCT_PATH_RE = re.compile(r"^/produkt/[^/]+/?$")


def _clean(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _normalize(value: str) -> str:
    table = str.maketrans(
        "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ",
        "acdeeinorstuuyzACDEEINORSTUUYZ",
    )
    return value.translate(table).casefold()


def _product_links(
    html: str,
    *,
    base_url: str,
    category: str,
) -> list[tuple[str, str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    result: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, anchor["href"])
        parts = urlsplit(url)
        if parts.hostname not in _ALLOWED_HOSTS:
            continue
        if not _PRODUCT_PATH_RE.match(parts.path):
            continue
        if url in seen:
            continue
        title = _clean(anchor.get_text(" ", strip=True))
        if not title:
            # Card titles can be nested in nearby headings rather than link text.
            parent = anchor.find_parent(["article", "div", "li"])
            if parent is not None:
                heading = parent.find(["h2", "h3", "h4"])
                if heading:
                    title = _clean(heading.get_text(" ", strip=True))
        if not title:
            title = PurePosixPath(parts.path.rstrip("/")).name.replace("-", " ")
        seen.add(url)
        result.append((title, url, category))
    return result


def _external_id(url: str) -> str:
    slug = PurePosixPath(urlsplit(url).path.rstrip("/")).name
    normalized = re.sub(r"[^a-z0-9]+", "-", _normalize(slug)).strip("-")
    if normalized:
        return f"NRB-{normalized[:100]}"
    return "NRB-" + hashlib.sha256(url.encode()).hexdigest()[:24]


def _status(body: str) -> str:
    folded = _normalize(body)
    if (
        "prijem zadosti byl" in folded
        and "pozastaven" in folded
    ) or "program je pozastaven" in folded:
        return "PAUSED"
    if (
        "spusteni programu" in folded
        and "planov" in folded
    ) or "prijem zadosti bude zahajen" in folded:
        return "PLANNED"
    if (
        "aktivni prijem zadosti" in folded
        or "prijem zadosti od" in folded
        or "zadosti prijimame" in folded
    ):
        return "OPEN"
    if (
        "prijem zadosti byl ukoncen" in folded
        or "program byl ukoncen" in folded
        or "prijem zadosti ukoncen" in folded
    ):
        return "CLOSED"
    return "UNKNOWN"


def _instrument_type(category: str, body: str) -> str:
    folded = _normalize(body)
    mixed_markers = (
        "financni prispevek",
        "dotace az",
        "dotacni slozka",
        "prispevek na",
        "odpusteni casti jistiny",
    )
    if category == "GUARANTEE":
        return "GUARANTEE"
    if any(marker in folded for marker in mixed_markers):
        return "MIXED"
    return "LOAN"


def _money_minor(text: str | None) -> tuple[int | None, str | None]:
    if not text:
        return None, None
    match = re.search(
        r"([0-9][0-9\s.,]*)\s*(mil\.?|mld\.?)?\s*(Kč|CZK|EUR|€)",
        text,
        re.I,
    )
    if not match:
        return None, None
    raw = match.group(1).replace(" ", "").replace("\xa0", "")
    if "," in raw and "." not in raw:
        raw = raw.replace(",", ".")
    else:
        raw = raw.replace(",", "")
    try:
        amount = float(raw)
    except ValueError:
        return None, None
    scale = (match.group(2) or "").casefold()
    if scale.startswith("mil"):
        amount *= 1_000_000
    elif scale.startswith("mld"):
        amount *= 1_000_000_000
    currency = "CZK" if match.group(3).casefold() in {"kč", "czk"} else "EUR"
    return int(round(amount * 100)), currency


def _percent_bps(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", text)
    if not match:
        return None
    return int(round(float(match.group(1).replace(",", ".")) * 100))


def _first_matching_text(soup: BeautifulSoup, labels: tuple[str, ...]) -> str | None:
    normalized_labels = tuple(_normalize(label) for label in labels)
    # Prefer compact blocks/cards and list items before scanning all body text.
    for element in soup.find_all(["li", "p", "div", "td", "dd"]):
        value = _clean(element.get_text(" ", strip=True))
        if not value:
            continue
        folded = _normalize(value)
        if any(label in folded for label in normalized_labels):
            return value
    return None


def _all_matching_text(soup: BeautifulSoup, labels: tuple[str, ...]) -> list[str]:
    normalized_labels = tuple(_normalize(label) for label in labels)
    result: list[str] = []
    seen: set[str] = set()
    for element in soup.find_all(["li", "p", "div", "td", "dd"]):
        value = _clean(element.get_text(" ", strip=True))
        if not value or value in seen:
            continue
        folded = _normalize(value)
        if any(label in folded for label in normalized_labels):
            seen.add(value)
            result.append(value)
    return result


def _mime_hint(url: str) -> str | None:
    value = url.casefold()
    if ".pdf" in value:
        return "application/pdf"
    if ".docx" in value:
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if ".doc" in value:
        return "application/msword"
    if ".xlsx" in value or ".xlsm" in value:
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if ".xls" in value:
        return "application/vnd.ms-excel"
    if ".zip" in value:
        return "application/zip"
    return None


def _artifact_role(title: str) -> str:
    folded = _normalize(title)
    if "vyzva" in folded:
        return "CALL_DOCUMENT"
    if (
        "pravidl" in folded
        or "metodik" in folded
        or "priruck" in folded
        or "podmink" in folded
    ):
        return "GUIDELINES"
    if "zadost" in folded or "formular" in folded:
        return "APPLICATION_FORM"
    return "ANNEX"


def _artifacts(soup: BeautifulSoup, base_url: str) -> list[RemoteArtifactRef]:
    result: list[RemoteArtifactRef] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, anchor["href"])
        if urlsplit(url).hostname not in _ALLOWED_HOSTS or url in seen:
            continue
        mime = _mime_hint(url)
        if mime is None:
            continue
        seen.add(url)
        title = _clean(anchor.get_text(" ", strip=True)) or PurePosixPath(urlsplit(url).path).name
        role = _artifact_role(title)
        result.append(
            RemoteArtifactRef(
                external_id=hashlib.sha256(url.encode()).hexdigest()[:24],
                url=url,
                role=role,
                title=title,
                mime_hint=mime,
                required=(role == "CALL_DOCUMENT"),
            )
        )
    return result


class NrbAdapter(SourceAdapter):
    descriptor = SourceDescriptor(
        code="NRB",
        name="Národní rozvojová banka — úvěry a záruky",
        authority=AuthorityLevel.OFFICIAL,
        country_code="CZ",
        base_url="https://www.nrb.cz/",
        retrieval_modes=[
            RetrievalMode.HTML,
            RetrievalMode.PDF,
            RetrievalMode.DOCX,
            RetrievalMode.XLSX,
        ],
        allowed_hosts=sorted(_ALLOWED_HOSTS),
        normal_refresh_minutes=360,
        max_concurrency=2,
        requests_per_second=0.5,
        disappearance_confirmation_runs=3,
        adapter_version="0.1.0",
    )

    async def healthcheck(self, ctx: AdapterContext) -> HealthReport:
        started = datetime.now(timezone.utc)
        diagnostics: dict[str, str] = {}
        failures: list[str] = []
        for label, url in (
            ("loans", LOANS_INDEX),
            ("guarantees", GUARANTEES_INDEX),
        ):
            try:
                response = await ctx.http.get(url)
                diagnostics[label] = str(response.status_code)
                if response.status_code != 200:
                    failures.append(f"{label}: HTTP {response.status_code}")
            except Exception as exc:
                failures.append(f"{label}: {type(exc).__name__}: {exc}")
        elapsed = datetime.now(timezone.utc) - started
        status = (
            HealthStatus.HEALTHY
            if not failures
            else (
                HealthStatus.DEGRADED
                if len(failures) == 1
                else HealthStatus.UNAVAILABLE
            )
        )
        return HealthReport(
            status=status,
            checked_at=ctx.now,
            latency_ms=max(0, int(elapsed.total_seconds() * 1000)),
            detail="; ".join(failures) if failures else None,
            diagnostics=diagnostics,
        )

    async def discover(
        self,
        ctx: AdapterContext,
        checkpoint: SourceCheckpoint | None,
    ) -> DiscoveryPage:
        del checkpoint
        items: dict[str, DiscoveryItem] = {}

        for index_url, category in (
            (LOANS_INDEX, "LOAN"),
            (GUARANTEES_INDEX, "GUARANTEE"),
        ):
            response = await ctx.http.get(index_url)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"NRB {category.lower()} index returned HTTP "
                    f"{response.status_code}"
                )
            snapshot_id = self._snapshot(
                ctx,
                source_url=index_url,
                content=response.content,
                mime_type=response.headers.get(
                    "content-type", "text/html"
                ).split(";", 1)[0],
                headers=response.headers,
            )
            for title, url, source_category in _product_links(
                response.text,
                base_url=index_url,
                category=category,
            ):
                external_id = _external_id(url)
                previous = items.get(external_id)
                categories = {
                    source_category,
                    *(
                        previous.metadata.get("source_categories", [])
                        if previous is not None
                        else []
                    ),
                }
                items[external_id] = DiscoveryItem(
                    external_id=external_id,
                    detail_url=url,
                    title_hint=title,
                    metadata={
                        "source_categories": sorted(categories),
                        "discovery_snapshot_ids": [
                            snapshot_id,
                            *(
                                previous.metadata.get(
                                    "discovery_snapshot_ids", []
                                )
                                if previous is not None
                                else []
                            ),
                        ],
                    },
                )

        values = sorted(items.values(), key=lambda item: item.external_id)
        return DiscoveryPage(
            items=values,
            next_checkpoint=None,
            is_complete=True,
            total_hint=len(values),
        )

    async def fetch_record(
        self,
        ctx: AdapterContext,
        item: DiscoveryItem,
        validators: FetchValidators | None = None,
    ) -> RecordFetchResult:
        headers: dict[str, str] = {}
        if validators:
            if validators.etag:
                headers["if-none-match"] = validators.etag
            if validators.last_modified:
                headers["if-modified-since"] = validators.last_modified

        response = await ctx.http.get(str(item.detail_url), headers=headers)
        if response.status_code == 304:
            return RecordFetchResult(
                state=FetchState.NOT_MODIFIED,
                http_status=304,
            )
        if response.status_code == 404:
            return RecordFetchResult(
                state=FetchState.GONE,
                http_status=404,
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"NRB detail returned HTTP {response.status_code}"
            )

        snapshot_id = self._snapshot(
            ctx,
            source_url=str(item.detail_url),
            content=response.content,
            mime_type=response.headers.get(
                "content-type", "text/html"
            ).split(";", 1)[0],
            headers=response.headers,
        )
        soup = BeautifulSoup(response.text, "html.parser")
        body = _clean(soup.get_text(" ", strip=True))
        h1 = soup.find("h1")
        title = (
            _clean(h1.get_text(" ", strip=True))
            if h1
            else (item.title_hint or item.external_id)
        )

        categories = set(
            str(value)
            for value in item.metadata.get("source_categories", [])
        )
        base_category = (
            "GUARANTEE"
            if "GUARANTEE" in categories and "LOAN" not in categories
            else "LOAN"
        )
        instrument = _instrument_type(base_category, body)

        loan_text = _first_matching_text(
            soup,
            (
                "výše úvěru",
                "úvěr od",
                "úvěr ve výši",
                "zaručovaný úvěr",
            ),
        )
        guarantee_text = _first_matching_text(
            soup,
            (
                "výše záruky",
                "záruka až",
                "záruka do",
            ),
        )
        interest_text = _first_matching_text(
            soup,
            ("úrok", "úroková sazba"),
        )
        maturity_text = _first_matching_text(
            soup,
            ("doba splatnosti", "splatnost"),
        )
        contribution_texts = _all_matching_text(
            soup,
            (
                "finanční příspěvek",
                "dotace",
                "odpuštění části jistiny",
            ),
        )
        applicants = _first_matching_text(
            soup,
            (
                "pro malé a střední podniky",
                "malé a střední podniky",
                "pro podnikatele",
                "oprávnění žadatelé",
            ),
        )
        geography = _first_matching_text(
            soup,
            (
                "celá čr",
                "celé území české republiky",
                "místo realizace",
            ),
        )

        loan_min = loan_max = loan_currency = None
        if loan_text:
            values = re.findall(
                r"[0-9][0-9\s.,]*\s*(?:mil\.?|mld\.?)?\s*(?:Kč|CZK|EUR|€)",
                loan_text,
                re.I,
            )
            parsed = [_money_minor(value) for value in values]
            parsed = [value for value in parsed if value[0] is not None]
            if parsed:
                loan_min = min(value[0] for value in parsed)
                loan_max = max(value[0] for value in parsed)
                loan_currency = parsed[0][1]

        guarantee_bps = _percent_bps(guarantee_text)
        interest_bps = _percent_bps(interest_text)

        return RecordFetchResult(
            state=FetchState.MODIFIED,
            record=NativeRecord(
                source_code=self.descriptor.code,
                external_id=item.external_id,
                detail_url=item.detail_url,
                native_title=title,
                native_status=_status(body),
                raw_fields={
                    "fundingInstrumentType": instrument,
                    "sourceCategories": sorted(categories),
                    "loanAmountText": loan_text,
                    "loanAmountMinMinor": loan_min,
                    "loanAmountMaxMinor": loan_max,
                    "loanCurrency": loan_currency,
                    "guaranteeText": guarantee_text,
                    "guaranteeCoverageBps": guarantee_bps,
                    "interestText": interest_text,
                    "interestRateBps": interest_bps,
                    "maturityText": maturity_text,
                    "contributionTexts": contribution_texts,
                    "eligibleApplicantsText": applicants,
                    "geographyText": geography,
                    "coverageNote": (
                        "NRB je veřejný finanční poskytovatel. Produkt je "
                        "klasifikován jako LOAN/GUARANTEE/MIXED; negrantové "
                        "nástroje se nesmějí vyhodnotit grantovým finance enginem."
                    ),
                },
                artifacts=_artifacts(soup, str(item.detail_url)),
                snapshot_ids=[snapshot_id],
            ),
            http_status=response.status_code,
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
        )

    async def fetch_artifact(
        self,
        ctx: AdapterContext,
        artifact: RemoteArtifactRef,
        validators: FetchValidators | None = None,
    ) -> ArtifactFetchResult:
        headers: dict[str, str] = {}
        if validators:
            if validators.etag:
                headers["if-none-match"] = validators.etag
            if validators.last_modified:
                headers["if-modified-since"] = validators.last_modified

        response = await ctx.http.get(str(artifact.url), headers=headers)
        if response.status_code == 304:
            return ArtifactFetchResult(state=FetchState.NOT_MODIFIED)
        if response.status_code == 404:
            return ArtifactFetchResult(state=FetchState.GONE)
        if response.status_code >= 400:
            raise RuntimeError(
                f"NRB artifact returned HTTP {response.status_code}"
            )

        mime = response.headers.get(
            "content-type",
            artifact.mime_hint or "application/octet-stream",
        ).split(";", 1)[0]
        snapshot_id = self._snapshot(
            ctx,
            source_url=str(artifact.url),
            content=response.content,
            mime_type=mime,
            headers=response.headers,
        )
        return ArtifactFetchResult(
            state=FetchState.MODIFIED,
            snapshot_id=snapshot_id,
            sha256=hashlib.sha256(response.content).hexdigest(),
            mime_type=mime,
            size_bytes=len(response.content),
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
        )

    def _snapshot(
        self,
        ctx: AdapterContext,
        *,
        source_url: str,
        content: bytes,
        mime_type: str,
        headers: Any,
    ) -> str:
        if ctx.snapshots is None:
            raise RuntimeError("NRB adapter requires ctx.snapshots")
        snapshot = ctx.snapshots.put(
            source_code=self.descriptor.code,
            source_url=source_url,
            content=content,
            mime_type=mime_type,
            retrieved_at=ctx.now,
            validators={
                "etag": headers.get("etag") or "",
                "last_modified": headers.get("last-modified") or "",
            },
        )
        return snapshot.snapshot_id
