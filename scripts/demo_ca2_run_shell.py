"""CA-2 Demo：调用 run_shell 跑一条无害命令。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.tools.shell_tools import run_shell


def main() -> None:
    out = run_shell.invoke(
        {
            "command": 'python -c "print(\'CA-2-DEMO-OK\')"',
            "working_directory": ".",
        }
    )
    print(out)
    assert out.startswith("ok ")
    assert "CA-2-DEMO-OK" in out
    assert "exit_code=0" in out
    print("CA-2 DEMO OK")


if __name__ == "__main__":
    main()
