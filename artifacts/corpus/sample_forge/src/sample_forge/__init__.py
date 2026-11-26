"""Sample Forge: demo library for workspace scan + chunking."""

__version__ = "0.3.0"

from sample_forge.chunking import TextChunk, split_line_windows
from sample_forge.scanner import iter_source_files

__all__ = [
    "__version__",
    "TextChunk",
    "split_line_windows",
    "iter_source_files",
]
