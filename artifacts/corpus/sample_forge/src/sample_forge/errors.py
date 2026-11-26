"""Typed errors for CLI and library callers."""


class ForgeError(Exception):
    """Base error."""


class ValidationError(ForgeError):
    """Bad user input (window, overlap, mode, etc.)."""


class ChunkBudgetError(ForgeError):
    """Too many chunks for the configured budget."""


class PathEscapeError(ForgeError):
    """A resolved path escaped the workspace root."""
