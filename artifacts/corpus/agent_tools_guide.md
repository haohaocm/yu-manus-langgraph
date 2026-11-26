# Agent Tools Guide（代理工具指南）

This document explains how a coding agent uses tools to explore a repository.

## Path sandbox（路径沙箱）

The path sandbox is a safety gate. Every file path from the model must stay inside
the workspace root. If a user asks to read `../../etc/passwd`, resolve_safe must
reject the escape. PathSandboxError is raised when the resolved path leaves the root.

Key ideas:
- workspace root is the only allowed base
- relative paths like `app/search/chunking.py` are fine
- parent segments `..` that escape the root are blocked

## Grep versus semantic search（精确 vs 语义）

Exact grep finds symbol names and regex matches. It is perfect when you already
know the identifier, for example `PathSandboxError` or `search_hybrid`.

Semantic retrieval finds code by meaning. Ask "how do we stop path traversal"
and the index should surface path sandbox notes even if the query never says
`resolve_safe`.

## Chunking（切块）

Large files are split into overlapping line windows. Each chunk stores path,
start_line, end_line, and text. Overlap keeps a function signature visible in
two neighboring chunks so retrieval does not miss boundary context.

## Ranking（打分）

BM25 is lexical: it loves shared tokens. Embedding cosine is semantic: it
compares vector directions. Hybrid scoring mixes both after max-normalization:

    hybrid = (1 - alpha) * bm25_norm + alpha * embedding_norm

Use a higher alpha when meaning matters more than exact words.
