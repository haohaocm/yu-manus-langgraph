# Security notes

- Never follow symlinks that escape the workspace root.
- Treat user-supplied globs carefully; prefer allow-lists.
- Oversized files may contain secrets dumped into logs — skipping them
  reduces accidental embedding of credentials.
