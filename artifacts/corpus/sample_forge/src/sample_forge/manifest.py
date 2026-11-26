"""Build and serialize index manifests."""

from __future__ import annotations

import json
from pathlib import Path

from sample_forge.models import BuildManifest


def write_manifest(manifest: BuildManifest, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out


def read_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
