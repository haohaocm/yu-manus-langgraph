# Chunk demo notes

When window=40 and overlap=10, step size is 30 lines.
Adjacent chunks share context so symbols near boundaries are less likely
to be split away from their callers.

For IDX-WS learning, compare:
1. query by meaning via embeddings
2. query by exact token via BM25 / grep
