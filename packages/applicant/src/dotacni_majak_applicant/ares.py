from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from dotacni_majak_source_sdk import GuardedHttpClient, GuardedHttpError

from .models import (
    ApplicantResolution,
    ResolvedFact,
    ResolutionStatus,
)


_ICO_RE = re.compile(r"^\d{8}$")


class AresResolver:
    BASE_URL = (
        "https://ares.gov.cz/"
        "ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty"
    )

    def __init__(
        self,
        http: GuardedHttpClient,
        *,
        base_url: str | None = None,
        resolver_version: str = "ares-tolerant-v1",
    ) -> None:
        self.http = http
        self.base_url = (base_url or self.BASE_URL).rstrip("/")
        self.resolver_version = resolver_version

    async def resolve(self, ico: str) -> ApplicantResolution:
        normalized = ico.strip()
        if not _ICO_RE.fullmatch(normalized):
            return ApplicantResolution(
                ResolutionStatus.INVALID_INPUT,
                warnings=("IČO musí mít přesně 8 číslic.",),
            )

        url = f"{self.base_url}/{quote(normalized, safe='')}"
        try:
            response = await self.http.get(
                url,
                headers={"accept": "application/json"},
                max_response_bytes=2 * 1024 * 1024,
            )
        except GuardedHttpError as exc:
            return ApplicantResolution(
                ResolutionStatus.UNAVAILABLE,
                warnings=(f"{type(exc).__name__}: {exc}",),
            )

        if response.status_code == 404:
            return ApplicantResolution(ResolutionStatus.NOT_FOUND)
        if response.status_code != 200:
            return ApplicantResolution(
                ResolutionStatus.UNAVAILABLE,
                warnings=(f"ARES HTTP {response.status_code}",),
            )

        try:
            payload = json.loads(response.content)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return ApplicantResolution(
                ResolutionStatus.UNAVAILABLE,
                warnings=(f"Invalid ARES JSON: {exc}",),
            )

        try:
            return self.normalize_payload(
                payload,
                requested_ico=normalized,
                source_url=url,
            )
        except (KeyError, TypeError, ValueError) as exc:
            return ApplicantResolution(
                ResolutionStatus.UNAVAILABLE,
                warnings=(
                    "ARES response shape is not compatible with the "
                    f"current resolver ({self.resolver_version}): {exc}",
                ),
            )

    def normalize_payload(
        self,
        payload: dict[str, Any],
        *,
        requested_ico: str,
        source_url: str,
        observed_at: datetime | None = None,
    ) -> ApplicantResolution:
        observed = observed_at or datetime.now(timezone.utc)

        response_ico = self._scalar(payload.get("ico") or payload.get("icoId"))
        if response_ico and response_ico.startswith("ARES_"):
            response_ico = response_ico.removeprefix("ARES_")
        if response_ico != requested_ico:
            raise ValueError(
                f"response IČO {response_ico!r} does not match request"
            )

        name = self._name(payload.get("obchodniJmeno"))
        legal_form = self._scalar(
            payload.get("pravniForma") or payload.get("pravniFormaRos")
        )
        address = self._address(payload.get("sidlo"))
        nace = self._codes(payload.get("czNace"))

        values: list[tuple[str, Any]] = [
            ("applicant.ico", requested_ico),
        ]
        if name:
            values.append(("applicant.organisation_name", name))
        if legal_form:
            values.append(("applicant.legal_form", legal_form))
        if address.get("kodObce") is not None:
            values.append(
                ("applicant.municipality.code", str(address["kodObce"]))
            )
        if address.get("nazevObce"):
            values.append(
                ("applicant.municipality.name", str(address["nazevObce"]))
            )
        if address.get("textovaAdresa"):
            values.append(
                ("applicant.address_text", str(address["textovaAdresa"]))
            )
        if nace:
            values.append(("applicant.cz_nace", nace))

        facts = tuple(
            ResolvedFact(
                attribute_key=key,
                value=value,
                source_kind="ARES",
                source_reference=source_url,
                observed_at=observed,
            )
            for key, value in values
        )
        return ApplicantResolution(
            ResolutionStatus.RESOLVED,
            facts=facts,
        )

    @staticmethod
    def _scalar(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, (str, int)):
            return str(value)
        if isinstance(value, dict):
            for key in ("hodnota", "kod", "value"):
                if value.get(key) is not None:
                    return str(value[key])
        return None

    @staticmethod
    def _name(value: Any) -> str | None:
        if isinstance(value, str):
            return value.strip() or None
        if not isinstance(value, list):
            return None

        candidates = [item for item in value if isinstance(item, dict)]
        candidates.sort(
            key=lambda item: (
                not bool(item.get("primarniZaznam")),
                bool(item.get("platnostDo")),
            )
        )
        for item in candidates:
            name = item.get("obchodniJmeno") or item.get("hodnota")
            if isinstance(name, str) and name.strip():
                return name.strip()
        return None

    @staticmethod
    def _address(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if not isinstance(value, list):
            return {}

        candidates = [item for item in value if isinstance(item, dict)]
        candidates.sort(
            key=lambda item: (
                not bool(item.get("primarniZaznam")),
                bool(item.get("platnostDo")),
            )
        )
        for item in candidates:
            nested = item.get("sidlo")
            if isinstance(nested, dict):
                return nested
            if "kodObce" in item or "nazevObce" in item:
                return item
        return {}

    @staticmethod
    def _codes(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        codes: list[str] = []
        for item in value:
            if isinstance(item, (str, int)):
                code = str(item)
            elif isinstance(item, dict):
                raw = item.get("kod") or item.get("hodnota")
                if raw is None:
                    continue
                code = str(raw)
            else:
                continue
            if code not in codes:
                codes.append(code)
        return codes
