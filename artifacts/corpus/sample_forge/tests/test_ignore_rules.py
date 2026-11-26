from pathlib import Path

from sample_forge.ignore_rules import DEFAULT_IGNORE, should_skip_dir


def test_skip_venv(tmp_path: Path) -> None:
    assert should_skip_dir(tmp_path / ".venv", DEFAULT_IGNORE)
    assert not should_skip_dir(tmp_path / "src", DEFAULT_IGNORE)
