"""One-shot generator: artifacts/corpus/sample_forge mini GitHub-shaped project."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "artifacts" / "corpus" / "sample_forge"


def main() -> None:
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)

    files: dict[str, str] = {}

    files["README.md"] = """# Sample Forge

A tiny but realistic open-source style Python toolkit for **workspace indexing demos**.

Sample Forge pretends to be a CLI that scans a project folder, applies ignore rules,
chunks text files, and prepares payloads for embedding-based retrieval.

## Features

- Workspace scanning with directory ignore lists
- Glob allow-lists for source-like files
- Line-window chunking with overlap
- Manifest writing for reproducible rebuilds
- Pluggable embedder interface (HTTP OpenAI-compatible)

## Quick start

```bash
pip install -e .
sample-forge scan ./my-project
sample-forge chunk ./my-project --window 40 --overlap 10
```

## Why this repo exists

It lives under `artifacts/corpus/sample_forge` so IDX-WS / CE-6 tests have a
**GitHub-shaped** tree (src, tests, docs, configs, ignore noise) without cloning
a huge upstream project that would blow embedding budgets.

## Layout

- `src/sample_forge/` — library + CLI
- `tests/` — unit tests
- `docs/` — design notes
- `examples/` — scripts
- `.venv/` / `node_modules/` — **noise dirs** (should be ignored by indexer)
- `logs/giant_debug.log` — oversized file for max_file_bytes demos

## License

MIT
"""

    files["LICENSE"] = """MIT License

Copyright (c) 2026 Sample Forge Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

    files["CHANGELOG.md"] = """# Changelog

## 0.3.0 — 2026-11-24
- Add hybrid score blend helpers
- Document ignore + size limits

## 0.2.0 — 2026-11-01
- Chunking with overlap
- Manifest schema v1

## 0.1.0 — 2026-10-01
- Initial scanner + CLI skeleton
"""

    files["CONTRIBUTING.md"] = """# Contributing

1. Fork and create a feature branch.
2. Keep public APIs typed.
3. Add tests under `tests/`.
4. Do not commit `.venv/`, `node_modules/`, or giant logs.
5. Run `pytest -q` before opening a PR.

### Code style
- Python 3.11+
- Prefer small pure functions for ignore / size gates
- Docstrings in English; user-facing CLI help in English
"""

    files["pyproject.toml"] = """[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "sample-forge"
version = "0.3.0"
description = "Demo toolkit for workspace scanning and chunking"
readme = "README.md"
requires-python = ">=3.11"
license = { text = "MIT" }
authors = [{ name = "Sample Forge Contributors" }]
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.scripts]
sample-forge = "sample_forge.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
"""

    files[".gitignore"] = """ .venv/
venv/
node_modules/
__pycache__/
*.py[cod]
.pytest_cache/
dist/
build/
*.egg-info/
logs/*.log
.idea/
.vscode/
""".lstrip()

    files[".github/workflows/ci.yml"] = """name: ci
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ".[dev]"
      - run: pytest -q
"""

    files["docs/architecture.md"] = """# Architecture

Sample Forge mirrors a simplified retrieval pipeline:

```text
workspace root
  -> walk files (ignore dirs + glob allow-list)
  -> skip oversized files
  -> line-window chunking
  -> (optional) embedding + lexical index
  -> query time: hybrid top-k
```

## Components

| Module | Responsibility |
|--------|----------------|
| `scanner` | Enumerate candidate files |
| `ignore_rules` | Directory blacklist helpers |
| `chunking` | Sliding line windows |
| `manifest` | Record build parameters |
| `cli` | User entrypoint |

## Non-goals

- Production vector database
- AST-aware chunking
- File-hash incremental rebuild (tracked elsewhere as IDX-INC)
"""

    files["docs/ignore_and_limits.md"] = """# Ignore rules and limits

## Ignore
Directories such as `.venv`, `node_modules`, and `.git` should never be
embedded. They explode cost and pollute semantic search with dependency noise.

## Limits
- **max_file_bytes**: skip a single oversized file (do not delete it on disk)
- **max_chunks**: fail the build if the corpus is too large after chunking

Skipping is an indexing policy, not a filesystem delete.
"""

    files["docs/cli_usage.md"] = """# CLI usage

```bash
sample-forge scan PATH
sample-forge chunk PATH --window 40 --overlap 10
sample-forge manifest PATH --out manifest.json
```

Exit codes:
- `0` success
- `2` validation error (bad window/overlap)
- `3` chunk budget exceeded
"""

    files["docs/security_notes.md"] = """# Security notes

- Never follow symlinks that escape the workspace root.
- Treat user-supplied globs carefully; prefer allow-lists.
- Oversized files may contain secrets dumped into logs — skipping them
  reduces accidental embedding of credentials.
"""

    files["docs/faq.md"] = """# FAQ

## Is embedding the same as "the model read all my code"?
No. Embedding builds a retrieval index. The LLM still only sees the
retrieved snippets (plus whatever you open with read_file).

## Do ignore rules delete files?
No. They only exclude files from indexing.

## When do I rebuild?
After source changes, if you do not have file-hash incremental indexing,
run a full rebuild (or later IDX-INC per-file rebuild).
"""

    files["examples/scan_demo.py"] = '''"""Example: print relative paths that a forge scan would keep."""

from pathlib import Path

from sample_forge.ignore_rules import DEFAULT_IGNORE
from sample_forge.scanner import iter_source_files


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    for path in iter_source_files(root, ignore_dirs=DEFAULT_IGNORE):
        print(path.relative_to(root).as_posix())


if __name__ == "__main__":
    main()
'''

    files["examples/chunk_demo.md"] = """# Chunk demo notes

When window=40 and overlap=10, step size is 30 lines.
Adjacent chunks share context so symbols near boundaries are less likely
to be split away from their callers.

For IDX-WS learning, compare:
1. query by meaning via embeddings
2. query by exact token via BM25 / grep
"""

    files["src/sample_forge/__init__.py"] = '''"""Sample Forge: demo library for workspace scan + chunking."""

__version__ = "0.3.0"

from sample_forge.chunking import TextChunk, split_line_windows
from sample_forge.scanner import iter_source_files

__all__ = [
    "__version__",
    "TextChunk",
    "split_line_windows",
    "iter_source_files",
]
'''

    files["src/sample_forge/__main__.py"] = '''from sample_forge.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
'''

    files["src/sample_forge/errors.py"] = '''"""Typed errors for CLI and library callers."""


class ForgeError(Exception):
    """Base error."""


class ValidationError(ForgeError):
    """Bad user input (window, overlap, mode, etc.)."""


class ChunkBudgetError(ForgeError):
    """Too many chunks for the configured budget."""


class PathEscapeError(ForgeError):
    """A resolved path escaped the workspace root."""
'''

    files["src/sample_forge/models.py"] = '''"""Dataclasses shared across modules."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class FileRef:
    """A file kept after ignore + size gates."""

    path: str
    size_bytes: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BuildManifest:
    """Parameters used to build an index snapshot."""

    workspace_root: str
    window: int
    overlap: int
    ignore_dirs: tuple[str, ...]
    globs: tuple[str, ...]
    max_file_bytes: int
    max_chunks: int
    file_count: int
    chunk_count: int

    def to_dict(self) -> dict:
        data = asdict(self)
        data["ignore_dirs"] = list(self.ignore_dirs)
        data["globs"] = list(self.globs)
        return data
'''

    files["src/sample_forge/ignore_rules.py"] = '''"""Directory ignore helpers (blacklist)."""

from __future__ import annotations

from pathlib import Path

DEFAULT_IGNORE: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        "search_index",
        ".idea",
        ".vscode",
        "dist",
        "build",
    }
)


def parse_csv(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def has_ignored_part(path: Path, ignore: frozenset[str] = DEFAULT_IGNORE) -> bool:
    return any(part in ignore for part in path.parts)


def should_skip_dir(path: Path, ignore: frozenset[str] = DEFAULT_IGNORE) -> bool:
    return path.name in ignore or has_ignored_part(path, ignore)
'''

    files["src/sample_forge/scanner.py"] = '''"""Walk a workspace and yield source-like files."""

from __future__ import annotations

from pathlib import Path

from sample_forge.ignore_rules import DEFAULT_IGNORE, has_ignored_part
from sample_forge.models import FileRef

DEFAULT_GLOBS: tuple[str, ...] = (
    "*.py",
    "*.md",
    "*.txt",
    "*.toml",
    "*.yml",
    "*.yaml",
    "*.json",
)


def iter_source_files(
    root: Path,
    *,
    ignore_dirs: frozenset[str] = DEFAULT_IGNORE,
    globs: tuple[str, ...] = DEFAULT_GLOBS,
    max_file_bytes: int = 512_000,
) -> list[Path]:
    """Return sorted files under root that pass ignore / glob / size gates."""
    root = root.resolve()
    found: set[Path] = set()
    for pattern in globs:
        for path in root.rglob(pattern):
            if not path.is_file():
                continue
            if has_ignored_part(path, ignore_dirs):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if max_file_bytes > 0 and size > max_file_bytes:
                continue
            found.add(path.resolve())
    return sorted(found, key=lambda p: p.as_posix().lower())


def list_file_refs(
    root: Path,
    *,
    ignore_dirs: frozenset[str] = DEFAULT_IGNORE,
    globs: tuple[str, ...] = DEFAULT_GLOBS,
    max_file_bytes: int = 512_000,
) -> list[FileRef]:
    refs: list[FileRef] = []
    root = root.resolve()
    for path in iter_source_files(
        root,
        ignore_dirs=ignore_dirs,
        globs=globs,
        max_file_bytes=max_file_bytes,
    ):
        rel = path.relative_to(root).as_posix()
        refs.append(FileRef(path=rel, size_bytes=path.stat().st_size))
    return refs
'''

    files["src/sample_forge/chunking.py"] = '''"""Line-window chunking with overlap."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from sample_forge.errors import ChunkBudgetError, ValidationError


@dataclass(frozen=True)
class TextChunk:
    chunk_id: str
    path: str
    start_line: int
    end_line: int
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


def split_line_windows(
    lines: list[str],
    *,
    path: str,
    window: int = 40,
    overlap: int = 10,
) -> list[TextChunk]:
    if window < 1:
        raise ValidationError("window must be >= 1")
    if overlap < 0 or overlap >= window:
        raise ValidationError("overlap must satisfy 0 <= overlap < window")
    n = len(lines)
    if n == 0:
        return []
    step = window - overlap
    out: list[TextChunk] = []
    start0 = 0
    while start0 < n:
        end0 = min(start0 + window, n)
        start_line = start0 + 1
        end_line = end0
        text = "\\n".join(lines[start0:end0])
        out.append(
            TextChunk(
                chunk_id=f"{path}:{start_line}-{end_line}",
                path=path,
                start_line=start_line,
                end_line=end_line,
                text=text,
            )
        )
        if end0 >= n:
            break
        start0 += step
    return out


def chunk_file(
    path: Path,
    *,
    rel_path: str,
    window: int = 40,
    overlap: int = 10,
) -> list[TextChunk]:
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    if b"\\x00" in raw[:8000]:
        return []
    text = raw.decode("utf-8", errors="replace")
    return split_line_windows(
        text.splitlines(),
        path=rel_path.replace("\\\\", "/"),
        window=window,
        overlap=overlap,
    )


def enforce_budget(chunks: list[TextChunk], max_chunks: int) -> None:
    if max_chunks > 0 and len(chunks) > max_chunks:
        raise ChunkBudgetError(
            f"chunk count {len(chunks)} exceeds max_chunks={max_chunks}"
        )
'''

    files["src/sample_forge/manifest.py"] = '''"""Build and serialize index manifests."""

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
'''

    files["src/sample_forge/hybrid_score.py"] = '''"""Tiny hybrid scoring helpers for teaching demos."""

from __future__ import annotations


def blend(bm25: float, embedding: float, alpha: float = 0.5) -> float:
    """alpha weights embedding; (1-alpha) weights bm25."""
    if not 0.0 <= alpha <= 1.0:
        raise ValueError("alpha must be in [0, 1]")
    return (1.0 - alpha) * bm25 + alpha * embedding


def min_max_norm(values: list[float]) -> list[float]:
    if not values:
        return []
    lo = min(values)
    hi = max(values)
    if hi <= lo:
        return [0.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]
'''

    files["src/sample_forge/config.py"] = '''"""Simple configuration object for demos."""

from __future__ import annotations

from dataclasses import dataclass

from sample_forge.ignore_rules import DEFAULT_IGNORE
from sample_forge.scanner import DEFAULT_GLOBS


@dataclass
class ForgeConfig:
    window: int = 40
    overlap: int = 10
    max_file_bytes: int = 512_000
    max_chunks: int = 8000
    ignore_dirs: frozenset[str] = DEFAULT_IGNORE
    globs: tuple[str, ...] = DEFAULT_GLOBS
    hybrid_alpha: float = 0.5
'''

    files["src/sample_forge/pipeline.py"] = '''"""End-to-end scan -> chunk -> manifest for demos."""

from __future__ import annotations

from pathlib import Path

from sample_forge.chunking import TextChunk, chunk_file, enforce_budget
from sample_forge.config import ForgeConfig
from sample_forge.models import BuildManifest
from sample_forge.scanner import iter_source_files


def build_chunks(root: Path, config: ForgeConfig | None = None) -> list[TextChunk]:
    cfg = config or ForgeConfig()
    root = root.resolve()
    chunks: list[TextChunk] = []
    files = iter_source_files(
        root,
        ignore_dirs=cfg.ignore_dirs,
        globs=cfg.globs,
        max_file_bytes=cfg.max_file_bytes,
    )
    for path in files:
        rel = path.relative_to(root).as_posix()
        chunks.extend(
            chunk_file(path, rel_path=rel, window=cfg.window, overlap=cfg.overlap)
        )
    enforce_budget(chunks, cfg.max_chunks)
    return chunks


def build_manifest(
    root: Path,
    chunks: list[TextChunk],
    config: ForgeConfig | None = None,
) -> BuildManifest:
    cfg = config or ForgeConfig()
    files = iter_source_files(
        root,
        ignore_dirs=cfg.ignore_dirs,
        globs=cfg.globs,
        max_file_bytes=cfg.max_file_bytes,
    )
    return BuildManifest(
        workspace_root=str(root.resolve()),
        window=cfg.window,
        overlap=cfg.overlap,
        ignore_dirs=tuple(sorted(cfg.ignore_dirs)),
        globs=cfg.globs,
        max_file_bytes=cfg.max_file_bytes,
        max_chunks=cfg.max_chunks,
        file_count=len(files),
        chunk_count=len(chunks),
    )
'''

    files["src/sample_forge/cli.py"] = '''"""Command-line entrypoint."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sample_forge.config import ForgeConfig
from sample_forge.errors import ChunkBudgetError, ForgeError, ValidationError
from sample_forge.manifest import write_manifest
from sample_forge.pipeline import build_chunks, build_manifest
from sample_forge.scanner import list_file_refs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sample-forge",
        description="Workspace scan/chunk demo CLI",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    scan = sub.add_parser("scan", help="List files that would be indexed")
    scan.add_argument("path", type=Path)

    chunk = sub.add_parser("chunk", help="Chunk a workspace and print counts")
    chunk.add_argument("path", type=Path)
    chunk.add_argument("--window", type=int, default=40)
    chunk.add_argument("--overlap", type=int, default=10)

    man = sub.add_parser("manifest", help="Write a build manifest JSON")
    man.add_argument("path", type=Path)
    man.add_argument("--out", type=Path, default=Path("manifest.json"))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.cmd == "scan":
            refs = list_file_refs(args.path)
            for ref in refs:
                print(f"{ref.size_bytes:8d}  {ref.path}")
            print(f"total={len(refs)}")
            return 0
        if args.cmd == "chunk":
            cfg = ForgeConfig(window=args.window, overlap=args.overlap)
            chunks = build_chunks(args.path, cfg)
            print(
                json.dumps(
                    {
                        "chunks": len(chunks),
                        "window": args.window,
                        "overlap": args.overlap,
                    }
                )
            )
            return 0
        if args.cmd == "manifest":
            chunks = build_chunks(args.path)
            manifest = build_manifest(args.path, chunks)
            write_manifest(manifest, args.out)
            print(f"wrote {args.out}")
            return 0
    except ValidationError as exc:
        print(f"validation error: {exc}", file=sys.stderr)
        return 2
    except ChunkBudgetError as exc:
        print(f"budget error: {exc}", file=sys.stderr)
        return 3
    except ForgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 1
'''

    files["tests/test_ignore_rules.py"] = '''from pathlib import Path

from sample_forge.ignore_rules import DEFAULT_IGNORE, should_skip_dir


def test_skip_venv(tmp_path: Path) -> None:
    assert should_skip_dir(tmp_path / ".venv", DEFAULT_IGNORE)
    assert not should_skip_dir(tmp_path / "src", DEFAULT_IGNORE)
'''

    files["tests/test_chunking.py"] = '''from sample_forge.chunking import split_line_windows


def test_overlap_windows() -> None:
    lines = [f"L{i}" for i in range(1, 101)]
    chunks = split_line_windows(lines, path="demo.py", window=40, overlap=10)
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 40
    assert chunks[1].start_line == 31
'''

    files["tests/test_hybrid_score.py"] = '''from sample_forge.hybrid_score import blend, min_max_norm


def test_blend_and_norm() -> None:
    assert blend(0.0, 1.0, alpha=0.5) == 0.5
    assert min_max_norm([2.0, 4.0, 6.0]) == [0.0, 0.5, 1.0]
'''

    files["tests/test_scanner_smoke.py"] = '''from pathlib import Path

from sample_forge.scanner import iter_source_files


def test_repo_self_scan_skips_noise() -> None:
    root = Path(__file__).resolve().parents[1]
    files = iter_source_files(root)
    rels = {p.relative_to(root).as_posix() for p in files}
    assert any(r.startswith("src/") for r in rels)
    assert not any(".venv" in r or "node_modules" in r for r in rels)
    assert not any(r.endswith("giant_debug.log") for r in rels)
'''

    files[".venv/Lib/site-packages/noise_pkg.py"] = """# fake site-package — must NOT be indexed
SECRET = "do-not-embed-me"
"""

    files["node_modules/leftpad/index.js"] = """// fake dependency noise
module.exports = function leftpad(s, n) { return s; };
"""

    files["src/sample_forge/py.typed"] = ""

    for rel, content in files.items():
        path = ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")

    # Fix accidental double-escaping in chunking.py from generator string
    chunking = ROOT / "src" / "sample_forge" / "chunking.py"
    text = chunking.read_text(encoding="utf-8")
    text = text.replace('"\\\\n".join', '"\\n".join')
    text = text.replace('b"\\\\x00"', 'b"\\x00"')
    text = text.replace('rel_path.replace("\\\\\\\\", "/")', 'rel_path.replace("\\\\", "/")')
    chunking.write_text(text, encoding="utf-8", newline="\n")

    log = ROOT / "logs" / "giant_debug.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_bytes(b"DEBUG spam line\n" * 40_000)

    print(f"wrote {len(files)} text files + giant log")
    print(f"giant_bytes={log.stat().st_size}")
    print(f"root={ROOT}")


if __name__ == "__main__":
    main()
