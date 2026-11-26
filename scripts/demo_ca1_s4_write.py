"""CA-1 S4：调用 Agent 工具 write_file / str_replace / read_file 验收写盘。

用法（仓库根、已激活 venv）：
  python scripts/demo_ca1_s4_write.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.tools.fs_tools import read_file
from app.tools.fs_write import str_replace, write_file
from app.tools.path_sandbox import project_root

DEMO_REL = "artifacts/ca1_write_demo/hello.txt"


def main() -> None:
    root = project_root()
    demo = root / DEMO_REL
    demo.parent.mkdir(parents=True, exist_ok=True)
    print(f"workspace={root}")
    print(f"demo={DEMO_REL}")

    # 1) 整文件覆盖写入
    w = write_file.invoke({"path": DEMO_REL, "content": "line-one\nkeep-me\n"})
    print("write_file:", w)
    assert w.startswith("ok "), w

    # 2) 局部替换
    r = str_replace.invoke(
        {"path": DEMO_REL, "old": "line-one", "new": "line-TWO", "replace_all": False}
    )
    print("str_replace:", r)
    assert r.startswith("ok "), r

    # 3) 读回核对
    text = read_file.invoke({"path": DEMO_REL, "offset": 1, "limit": 20})
    print("read_file:\n", text)
    assert "line-TWO" in text
    assert "keep-me" in text
    assert "line-one" not in text.split("\n", 1)[-1] or "line-TWO" in text

    disk = demo.read_text(encoding="utf-8")
    print("disk:", repr(disk))
    assert disk == "line-TWO\nkeep-me\n"

    # 4) 越界应失败
    bad = write_file.invoke({"path": "../outside_ca1.txt", "content": "nope"})
    print("escape write_file:", bad)
    assert bad.startswith("error:"), bad
    assert "escapes" in bad

    bak = demo.with_name(demo.name + ".ca1.bak")
    print("backup_exists:", bak.exists(), "->", bak.name if bak.exists() else "")
    print("S4 DEMO OK")


if __name__ == "__main__":
    main()
