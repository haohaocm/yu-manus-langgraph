"""Command-line entrypoint."""

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
