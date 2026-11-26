"""Example: print relative paths that a forge scan would keep."""

from pathlib import Path

from sample_forge.ignore_rules import DEFAULT_IGNORE
from sample_forge.scanner import iter_source_files


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    for path in iter_source_files(root, ignore_dirs=DEFAULT_IGNORE):
        print(path.relative_to(root).as_posix())


if __name__ == "__main__":
    main()
