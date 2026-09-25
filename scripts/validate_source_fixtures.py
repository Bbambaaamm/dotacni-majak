from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


class FixtureManifestError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FixtureValidationResult:
    manifests: int
    fixtures: int


_ALLOWED_ORIGIN = {"SANITIZED_DERIVATIVE", "GENERATED"}
_ALLOWED_PII = {"NONE_OBSERVED", "PUBLIC_CONTACTS_REMOVED", "REDACTED"}
_ALLOWED_SANITIZATION = {
    "MINIMIZED",
    "REDACTED",
    "STRUCTURE_ONLY",
    "GENERATED_SAFE",
}
_TEXT_MIME_PREFIXES = ("text/", "application/json", "application/xml")
_SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"(?i)authorization\s*:\s*bearer\s+[A-Za-z0-9._~+/=-]{12,}"),
)


def _is_text_mime(mime_type: str) -> bool:
    return mime_type.startswith(_TEXT_MIME_PREFIXES)


def _validate_source_url(value: str, *, context: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise FixtureManifestError(
            f"{context}: sourceUrl must be an absolute HTTPS URL"
        )
    if parsed.username is not None or parsed.password is not None:
        raise FixtureManifestError(
            f"{context}: sourceUrl credentials are forbidden"
        )


def _safe_fixture_path(root: Path, relative: str, *, context: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or relative in {"", "."}:
        raise FixtureManifestError(f"{context}: unsafe fixture path {relative!r}")
    path = (root / rel).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise FixtureManifestError(
            f"{context}: fixture path escapes fixture directory"
        ) from exc
    return path


def validate_fixture_manifest(
    manifest_path: Path,
    *,
    max_text_bytes: int = 512 * 1024,
    max_binary_bytes: int = 2 * 1024 * 1024,
) -> int:
    fixture_root = manifest_path.parent
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise FixtureManifestError(
            f"{manifest_path}: invalid UTF-8 JSON manifest"
        ) from exc

    if manifest.get("manifestVersion") != 1:
        raise FixtureManifestError(
            f"{manifest_path}: manifestVersion must be 1"
        )
    connector = manifest.get("connector")
    if not isinstance(connector, str) or not connector:
        raise FixtureManifestError(
            f"{manifest_path}: connector is required"
        )

    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise FixtureManifestError(
            f"{manifest_path}: non-empty entries are required"
        )

    listed: set[str] = set()
    for index, entry in enumerate(entries):
        context = f"{manifest_path}: entries[{index}]"
        if not isinstance(entry, dict):
            raise FixtureManifestError(f"{context}: entry must be an object")

        relative = entry.get("path")
        if not isinstance(relative, str):
            raise FixtureManifestError(f"{context}: path is required")
        if relative == "manifest.json":
            raise FixtureManifestError(
                f"{context}: manifest cannot list itself"
            )
        if relative in listed:
            raise FixtureManifestError(
                f"{context}: duplicate path {relative!r}"
            )
        listed.add(relative)

        source_url = entry.get("sourceUrl")
        if not isinstance(source_url, str):
            raise FixtureManifestError(
                f"{context}: sourceUrl is required"
            )
        _validate_source_url(source_url, context=context)

        captured_at = entry.get("capturedAt")
        if (
            not isinstance(captured_at, str)
            or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                captured_at,
            )
        ):
            raise FixtureManifestError(
                f"{context}: capturedAt must be UTC YYYY-MM-DDTHH:MM:SSZ"
            )

        mime_type = entry.get("mimeType")
        if not isinstance(mime_type, str) or "/" not in mime_type:
            raise FixtureManifestError(
                f"{context}: mimeType is required"
            )

        if entry.get("originType") not in _ALLOWED_ORIGIN:
            raise FixtureManifestError(
                f"{context}: unsupported originType"
            )
        if entry.get("piiStatus") not in _ALLOWED_PII:
            raise FixtureManifestError(
                f"{context}: piiStatus must be explicitly reviewed"
            )
        if entry.get("sanitization") not in _ALLOWED_SANITIZATION:
            raise FixtureManifestError(
                f"{context}: sanitization policy is required"
            )

        path = _safe_fixture_path(
            fixture_root,
            relative,
            context=context,
        )
        if not path.is_file():
            raise FixtureManifestError(
                f"{context}: fixture file does not exist: {relative}"
            )

        payload = path.read_bytes()
        size_limit = (
            max_text_bytes
            if _is_text_mime(mime_type)
            else max_binary_bytes
        )
        if len(payload) > size_limit:
            raise FixtureManifestError(
                f"{context}: fixture is too large: "
                f"{len(payload)} > {size_limit}"
            )

        for pattern in _SECRET_PATTERNS:
            if pattern.search(payload):
                raise FixtureManifestError(
                    f"{context}: fixture matches forbidden secret pattern"
                )

        expected_hash = entry.get("sha256")
        actual_hash = hashlib.sha256(payload).hexdigest()
        if expected_hash != actual_hash:
            raise FixtureManifestError(
                f"{context}: SHA256_MISMATCH path={relative} "
                f"expected={expected_hash!r} actual={actual_hash}"
            )

    actual_files = {
        path.relative_to(fixture_root).as_posix()
        for path in fixture_root.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    if actual_files != listed:
        missing = sorted(actual_files - listed)
        extra = sorted(listed - actual_files)
        raise FixtureManifestError(
            f"{manifest_path}: manifest/file mismatch; "
            f"unlisted={missing}, missing_files={extra}"
        )

    return len(entries)


def validate_repository_source_fixtures(repo_root: Path) -> FixtureValidationResult:
    manifest_paths = sorted(
        (repo_root / "connectors").glob("*/fixtures/manifest.json")
    )
    if not manifest_paths:
        raise FixtureManifestError("no source fixture manifests found")

    fixtures = 0
    for manifest in manifest_paths:
        fixtures += validate_fixture_manifest(manifest)

    return FixtureValidationResult(
        manifests=len(manifest_paths),
        fixtures=fixtures,
    )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    result = validate_repository_source_fixtures(root)
    print(
        f"OK source fixtures: {result.manifests} manifests, "
        f"{result.fixtures} fixtures"
    )


if __name__ == "__main__":
    main()
