from pathlib import Path

from sample_forge.scanner import iter_source_files


def test_repo_self_scan_skips_noise() -> None:
    root = Path(__file__).resolve().parents[1]
    files = iter_source_files(root)
    rels = {p.relative_to(root).as_posix() for p in files}
    assert any(r.startswith("src/") for r in rels)
    assert not any(".venv" in r or "node_modules" in r for r in rels)
    assert not any(r.endswith("giant_debug.log") for r in rels)
