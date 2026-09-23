from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
ASSETS = [
    ROOT / "apps/web/public/brand/lighthouse-mark.svg",
    ROOT / "apps/web/public/brand/lighthouse-mark-mono.svg",
    ROOT / "apps/web/public/brand/lighthouse-mark-white.svg",
    ROOT / "apps/web/public/icon.svg",
]


def validate(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"Missing brand asset: {path.relative_to(ROOT)}")

    raw = path.read_text(encoding="utf-8")
    lowered = raw.casefold()
    forbidden = ("<script", "javascript:", "http://", "https://")
    for value in forbidden:
        if value in lowered:
            raise SystemExit(
                f"{path.relative_to(ROOT)}: forbidden external/executable SVG content {value!r}"
            )

    root = ET.fromstring(raw)
    if not root.tag.endswith("svg"):
        raise SystemExit(f"{path.relative_to(ROOT)}: root element is not svg")
    if root.attrib.get("viewBox") not in {"0 0 64 64", "0 0 128 128"}:
        raise SystemExit(f"{path.relative_to(ROOT)}: unexpected or missing viewBox")
    if "width" in root.attrib or "height" in root.attrib:
        raise SystemExit(
            f"{path.relative_to(ROOT)}: omit fixed width/height for responsive reuse"
        )


def main() -> None:
    for asset in ASSETS:
        validate(asset)
        print(f"OK {asset.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
