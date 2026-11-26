# CLI usage

```bash
sample-forge scan PATH
sample-forge chunk PATH --window 40 --overlap 10
sample-forge manifest PATH --out manifest.json
```

Exit codes:
- `0` success
- `2` validation error (bad window/overlap)
- `3` chunk budget exceeded
