"""CE-6 阶段 A：chunking（切块）单测。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings, get_settings
from app.search.chunking import (
    TextChunk,
    chunk_corpus,
    chunk_file,
    iter_corpus_files,
    split_line_windows,
)


def _write_lines(path: Path, n: int, prefix: str = "L") -> None:
    path.write_text("\n".join(f"{prefix}{i}" for i in range(1, n + 1)) + "\n", encoding="utf-8")


def test_a_t1_basic_windows_have_overlap(tmp_path: Path) -> None:
    """A-T1: 80 行 → 多块，相邻块有 overlap。"""
    lines = [f"L{i}" for i in range(1, 81)]
    chunks = split_line_windows(lines, path="a.py", window=40, overlap=10)
    assert len(chunks) >= 2
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 40
    # step = 30 → 第二块从 31 起，与第一块重叠 31..40
    assert chunks[1].start_line == 31
    assert chunks[1].end_line == 70
    overlap_text_first = "\n".join(lines[30:40])
    assert chunks[0].text.endswith(overlap_text_first)
    assert chunks[1].text.startswith(overlap_text_first)


def test_a_t2_line_content_matches_file(tmp_path: Path) -> None:
    """A-T2: start_line/end_line 与文件内容一致。"""
    f = tmp_path / "demo.py"
    _write_lines(f, 50, prefix="ROW")
    chunks = chunk_file(f, rel_path="demo.py", window=40, overlap=10)
    assert chunks
    c0 = chunks[0]
    file_lines = f.read_text(encoding="utf-8").splitlines()
    expected = "\n".join(file_lines[c0.start_line - 1 : c0.end_line])
    assert c0.text == expected


def test_a_t3_empty_and_binary_skipped(tmp_path: Path) -> None:
    """A-T3: 空目录 / 二进制不崩。"""
    empty = tmp_path / "empty"
    empty.mkdir()
    assert chunk_corpus(workspace=tmp_path, corpus_dir=empty, window=40, overlap=10) == []

    bin_dir = tmp_path / "bin_corpus"
    bin_dir.mkdir()
    (bin_dir / "x.bin").write_bytes(b"\x00\x01\x02" + b"abc" * 100)
    # *.bin 不在默认 glob 内 → 仍为空
    assert chunk_corpus(workspace=tmp_path, corpus_dir=bin_dir, window=40, overlap=10) == []

    # 伪装成 .py 的二进制应被跳过
    (bin_dir / "bad.py").write_bytes(b"\x00" * 100)
    assert chunk_file(bin_dir / "bad.py", rel_path="bad.py") == []


def test_a_t4_stable_ids(tmp_path: Path) -> None:
    """A-T4: 同输入两次切块 id 稳定。"""
    lines = [f"x{i}" for i in range(1, 45)]
    a = split_line_windows(lines, path="s.py", window=40, overlap=10)
    b = split_line_windows(lines, path="s.py", window=40, overlap=10)
    assert [c.chunk_id for c in a] == [c.chunk_id for c in b]
    assert a[0].chunk_id == "s.py:1-40"


def test_a_t5_repo_corpus_smoke() -> None:
    """仓库内 artifacts/corpus 可切出若干块（冒烟）。"""
    get_settings.cache_clear()
    chunks = chunk_corpus(settings=Settings(workspace_root="."), window=40, overlap=10)
    assert len(chunks) >= 2
    paths = {c.path for c in chunks}
    assert any("job_" in p or p.endswith("notes_on_retrieval.md") for p in paths)
    # 摘要可打印（pytest -s 可见）
    for c in chunks[:3]:
        print(f"{c.chunk_id} chars={len(c.text)}")


def test_invalid_overlap_raises() -> None:
    with pytest.raises(ValueError):
        split_line_windows(["a"], path="p", window=10, overlap=10)


def test_iter_skips_venv(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    (corpus / ".venv" / "lib").mkdir(parents=True)
    (corpus / ".venv" / "lib" / "x.py").write_text("secret=1\n", encoding="utf-8")
    (corpus / "ok.py").write_text("print(1)\n", encoding="utf-8")
    files = iter_corpus_files(corpus)
    assert len(files) == 1
    assert files[0].name == "ok.py"


def test_text_chunk_to_dict() -> None:
    c = TextChunk("p:1-2", "p", 1, 2, "a\nb")
    d = c.to_dict()
    assert d["chunk_id"] == "p:1-2"
    assert d["start_line"] == 1
