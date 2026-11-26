"""
CA-7 评测入口。

用法（在仓库根）：
  .\\.venv\\Scripts\\python.exe -m evals.ca7.run_ca7
  .\\.venv\\Scripts\\python.exe -m evals.ca7.run_ca7 --offline-only
  .\\.venv\\Scripts\\python.exe -m evals.ca7.run_ca7 --live-only
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback


def main(argv: list[str] | None = None) -> int:
    """跑 CA-7 题集并打印表格；返回失败题数量（0=全过）。"""
    parser = argparse.ArgumentParser(description="CA-7 fixed eval suite")
    parser.add_argument("--offline-only", action="store_true")
    parser.add_argument("--live-only", action="store_true")
    args = parser.parse_args(argv)

    from evals.ca7.cases import get_cases

    cases = get_cases()
    if args.offline_only:
        cases = [c for c in cases if c.mode == "offline"]
    if args.live_only:
        cases = [c for c in cases if c.mode == "live"]

    print("=== CA-7 eval ===")
    rows: list[tuple[str, str, str, str]] = []
    fails = 0
    for case in cases:
        t0 = time.time()
        try:
            result = case.run()
        except Exception as exc:  # noqa: BLE001
            result = type(
                "R",
                (),
                {
                    "case_id": case.id,
                    "title": case.title,
                    "passed": False,
                    "detail": f"EXCEPTION: {exc}\n{traceback.format_exc()[-400:]}",
                },
            )()
        elapsed = time.time() - t0
        mark = "PASS" if result.passed else "FAIL"
        if not result.passed:
            fails += 1
        rows.append((mark, case.id, case.title, f"{elapsed:.1f}s | {result.detail}"))
        print(f"[{mark}] {case.id} — {case.title} ({elapsed:.1f}s)")
        print(f"       {result.detail}")

    total = len(rows)
    passed = total - fails
    print("---")
    print(f"pass_rate={passed}/{total} ({(100.0 * passed / total) if total else 0:.0f}%)")
    return fails


if __name__ == "__main__":
    sys.exit(main())
