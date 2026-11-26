# Ignore rules and limits

## Ignore
Directories such as `.venv`, `node_modules`, and `.git` should never be
embedded. They explode cost and pollute semantic search with dependency noise.

## Limits
- **max_file_bytes**: skip a single oversized file (do not delete it on disk)
- **max_chunks**: fail the build if the corpus is too large after chunking

Skipping is an indexing policy, not a filesystem delete.
