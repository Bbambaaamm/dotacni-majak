from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from dotacni_majak_source_sdk import DiscoveryItem, NativeRecord

from .local_publish import SearchableGrant, slugify, stable_id


CANONICAL_STATUSES = frozenset({
    "DRAFT",
    "ANNOUNCED",
    "PLANNED",
    "OPEN",
    "PAUSED",
    "CLOSED",
    "CANCELLED",
    "ARCHIVED",
})

EU_STATUS_MAP = {
    "31094501": "PLANNED",
    "31094502": "OPEN",
    "31094503": "CLOSED",
}

_HTML_RE = re.compile(r"<[^>]+>")


class GrantNormalizer(Protocol):
    def normalize(
        self,
        item: DiscoveryItem,
        record: NativeRecord,
        captured_at: datetime,
    ) -> SearchableGrant: ...


def record_content_hash(record: NativeRecord) -> str:
    for snapshot_id in record.snapshot_ids:
        candidate = snapshot_id.rsplit(":", 1)[-1].lower()
        if len(candidate) == 64 and all(ch in "0123456789abcdef" for ch in candidate):
            return candidate
    payload = record.model_dump_json().encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def canonical_status(value: str | None, *, mapping: dict[str, str] | None = None) -> str:
    native = (value or "").strip().upper()
    if mapping and native in mapping:
        return mapping[native]
    return native if native in CANONICAL_STATUSES else "DRAFT"


def stable_programme_identity(namespace: str, name: str, fallback: str) -> tuple[str, str]:
    cleaned = " ".join((name or "").split()) or fallback
    digest = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:16]
    return stable_id("programme", namespace, digest), cleaned


def _plain_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    without_tags = _HTML_RE.sub(" ", html.unescape(value))
    return " ".join(without_tags.split())


def _first(value: object) -> object:
    if isinstance(value, list):
        return value[0] if value else None
    return value


@dataclass(frozen=True, slots=True)
class NsaGrantNormalizer:
    def normalize(
        self,
        item: DiscoveryItem,
        record: NativeRecord,
        captured_at: datetime,
    ) -> SearchableGrant:
        listing_url = str(item.metadata.get("listing_url") or "")
        if "dotace-investicni-parasport" in listing_url:
            programme_id, programme_name = "programme:nsa:parasport", "NSA — Parasport"
        elif "dotace-neinvesticni-parasport" in listing_url:
            programme_id, programme_name = (
                "programme:nsa:parasport-noninvestment",
                "NSA — Neinvestiční parasport",
            )
        elif "dotace-investicni" in listing_url:
            programme_id, programme_name = "programme:nsa:investment", "NSA — Investiční výzvy"
        else:
            programme_id, programme_name = "programme:nsa:noninvestment", "NSA — Neinvestiční výzvy"

        external_id = record.external_id
        content_hash = record_content_hash(record)
        grant_call_id = stable_id("grant", "nsa", external_id.replace("/", "-"))
        version_id = stable_id(grant_call_id, "sha", content_hash[:24])
        description = str(record.raw_fields.get("descriptionText") or "").strip()
        call_type = str(record.raw_fields.get("callType") or "").strip()

        return SearchableGrant(
            source_id="source:nsa",
            source_code="NSA",
            source_name="Národní sportovní agentura",
            source_base_url="https://nsa.gov.cz/",
            adapter_key="nsa-cz",
            retrieval_mode="HTML",
            source_external_id=external_id,
            source_url=str(record.detail_url),
            content_hash=content_hash,
            provider_id="provider:nsa",
            provider_name="Národní sportovní agentura",
            provider_type="NATIONAL",
            programme_id=programme_id,
            programme_name=programme_name,
            funding_origin="CZ_NATIONAL",
            grant_call_id=grant_call_id,
            grant_version_id=version_id,
            canonical_slug=slugify(f"nsa-{external_id}"),
            title=(record.native_title or item.title_hint or external_id).strip(),
            summary=description[:4000],
            status=canonical_status(record.native_status),
            verification_status="PARTIALLY_VERIFIED",
            captured_at=captured_at.isoformat(),
            currency_code="CZK",
            published_at=record.published_at.isoformat() if record.published_at else None,
            submission_open_at=record.raw_fields.get("submissionOpenAt"),
            submission_close_at=record.raw_fields.get("submissionCloseAt"),
            supported_activities=description,
            eligible_costs="",
            keywords=" ".join(
                part for part in (call_type, external_id, "Národní sportovní agentura") if part
            ),
        )


@dataclass(frozen=True, slots=True)
class DotaceEuGrantNormalizer:
    def programme_identity(self, record: NativeRecord) -> tuple[str, str]:
        return stable_programme_identity(
            "dotaceeu",
            str(record.raw_fields.get("programme") or ""),
            "DotaceEU — program neuveden",
        )

    def normalize(
        self,
        item: DiscoveryItem,
        record: NativeRecord,
        captured_at: datetime,
    ) -> SearchableGrant:
        del item
        programme_id, programme_name = self.programme_identity(record)
        content_hash = record_content_hash(record)
        external_id = record.external_id
        grant_call_id = stable_id("grant", "dotaceeu", external_id)
        version_id = stable_id(grant_call_id, "sha", content_hash[:24])

        call_type = str(record.raw_fields.get("callType") or "").strip()
        priority = str(record.raw_fields.get("priorityAxis") or "").strip()
        applicants = str(record.raw_fields.get("eligibleApplicantsText") or "").strip()
        period = str(record.raw_fields.get("programmingPeriod") or "").strip()
        call_code = str(record.raw_fields.get("callCode") or "").strip()

        summary = " · ".join(
            part
            for part in (
                f"Program: {programme_name}" if programme_name else "",
                f"Priorita: {priority}" if priority else "",
                f"Typ výzvy: {call_type}" if call_type else "",
                f"Oprávnění žadatelé: {applicants}" if applicants else "",
            )
            if part
        )
        searchable_context = " ".join(
            part
            for part in (
                record.native_title or "",
                programme_name,
                priority,
                call_type,
                applicants,
            )
            if part
        )

        return SearchableGrant(
            source_id="source:dotaceeu",
            source_code="DOTACEEU",
            source_name="DotaceEU.cz",
            source_base_url="https://www.dotaceeu.cz/",
            adapter_key="dotaceeu-cz",
            retrieval_mode="HTML",
            source_external_id=external_id,
            source_url=str(record.detail_url),
            content_hash=content_hash,
            provider_id="provider:dotaceeu:unspecified",
            provider_name="Poskytovatel neuveden v agregovaném záznamu",
            provider_type="NATIONAL",
            programme_id=programme_id,
            programme_name=programme_name,
            funding_origin="EU_SHARED",
            grant_call_id=grant_call_id,
            grant_version_id=version_id,
            canonical_slug=slugify(f"dotaceeu-{external_id}"),
            title=(record.native_title or external_id).strip(),
            summary=summary[:4000],
            status=canonical_status(record.native_status),
            verification_status="PARTIALLY_VERIFIED",
            captured_at=captured_at.isoformat(),
            currency_code="CZK",
            submission_open_at=record.raw_fields.get("submissionOpenAt"),
            submission_close_at=record.raw_fields.get("submissionCloseAt"),
            supported_activities=searchable_context,
            eligible_costs="",
            keywords=" ".join(
                part for part in (call_code, call_type, period, programme_name) if part
            ),
        )


@dataclass(frozen=True, slots=True)
class EuFundingGrantNormalizer:
    def normalize(
        self,
        item: DiscoveryItem,
        record: NativeRecord,
        captured_at: datetime,
    ) -> SearchableGrant:
        meta = record.raw_fields.get("metadata")
        metadata = meta if isinstance(meta, dict) else {}

        framework = _first(metadata.get("frameworkProgramme"))
        framework_name = str(framework or item.metadata.get("framework_programme") or "EU Funding & Tenders")
        programme_id, programme_name = stable_programme_identity(
            "eu-ft",
            framework_name,
            "EU Funding & Tenders",
        )

        content_hash = record_content_hash(record)
        external_id = record.external_id
        grant_call_id = stable_id("grant", "eu-ft", external_id)
        version_id = stable_id(grant_call_id, "sha", content_hash[:24])

        summary = _plain_text(record.raw_fields.get("summary"))
        if not summary:
            summary = (record.native_title or item.title_hint or external_id).strip()

        conditions = _plain_text(_first(metadata.get("topicConditions")))
        support_info = _plain_text(_first(metadata.get("supportInfo")))
        description = _plain_text(_first(metadata.get("descriptionByte")))
        supported = " ".join(part for part in (summary, conditions, support_info, description) if part)

        start = _first(metadata.get("startDate"))
        deadline = _first(metadata.get("deadlineDate"))
        call_title = _first(metadata.get("callTitle"))
        topic_type = _first(metadata.get("type"))

        return SearchableGrant(
            source_id="source:eu-ft",
            source_code="EU_FT",
            source_name="EU Funding & Tenders Portal",
            source_base_url="https://ec.europa.eu/info/funding-tenders/opportunities/portal/",
            adapter_key="eu-funding-tenders",
            retrieval_mode="API",
            source_external_id=external_id,
            source_url=str(record.detail_url),
            content_hash=content_hash,
            provider_id="provider:ec",
            provider_name="European Commission",
            provider_type="EU",
            programme_id=programme_id,
            programme_name=programme_name,
            funding_origin="EU_DIRECT",
            grant_call_id=grant_call_id,
            grant_version_id=version_id,
            canonical_slug=slugify(f"eu-ft-{external_id}"),
            title=(record.native_title or item.title_hint or external_id).strip(),
            summary=summary[:4000],
            status=canonical_status(record.native_status, mapping=EU_STATUS_MAP),
            verification_status="PARTIALLY_VERIFIED",
            captured_at=captured_at.isoformat(),
            currency_code="EUR",
            submission_open_at=str(start) if start else None,
            submission_close_at=str(deadline or item.metadata.get("deadline") or "") or None,
            supported_activities=supported[:12000],
            eligible_costs="",
            keywords=" ".join(
                str(part)
                for part in (
                    external_id,
                    call_title,
                    topic_type,
                    framework_name,
                    record.raw_fields.get("reference"),
                )
                if part
            ),
        )


NORMALIZERS: dict[str, GrantNormalizer] = {
    "NSA": NsaGrantNormalizer(),
    "DOTACEEU": DotaceEuGrantNormalizer(),
    "EU_FT": EuFundingGrantNormalizer(),
}


def normalizer_for(source_code: str) -> GrantNormalizer:
    try:
        return NORMALIZERS[source_code]
    except KeyError as exc:
        raise KeyError(f"no grant normalizer registered for source {source_code!r}") from exc
