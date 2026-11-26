# Architecture

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
