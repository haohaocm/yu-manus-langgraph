# Sample Forge

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
- `logs/giant_debug.log` / `logs/oversized_notes.txt` — oversized files for max_file_bytes demos

## License

MIT
