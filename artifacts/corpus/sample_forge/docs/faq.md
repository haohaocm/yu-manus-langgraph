# FAQ

## Is embedding the same as "the model read all my code"?
No. Embedding builds a retrieval index. The LLM still only sees the
retrieved snippets (plus whatever you open with read_file).

## Do ignore rules delete files?
No. They only exclude files from indexing.

## When do I rebuild?
After source changes, if you do not have file-hash incremental indexing,
run a full rebuild (or later IDX-INC per-file rebuild).
