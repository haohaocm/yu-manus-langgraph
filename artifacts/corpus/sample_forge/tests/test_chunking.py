from sample_forge.chunking import split_line_windows


def test_overlap_windows() -> None:
    lines = [f"L{i}" for i in range(1, 101)]
    chunks = split_line_windows(lines, path="demo.py", window=40, overlap=10)
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 40
    assert chunks[1].start_line == 31
