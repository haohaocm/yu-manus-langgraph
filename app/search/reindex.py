"""IDX-WS S4：命令行强制重建 hybrid 索引并落盘。

用法（在项目根、已开 bge 隧道时）：

    python -m app.search.reindex
    python -m app.search.reindex --save-dir artifacts/search_index

说明：这不是 Agent 工具入参「路径」；工作区仍读环境变量 WORKSPACE_ROOT / SEARCH_MODE。
"""

from __future__ import annotations

import argparse
import json
import sys

from app.config import get_settings
from app.search.hybrid import build_and_save_hybrid
from app.search.scope import normalize_search_mode
from app.tools.path_sandbox import get_workspace_root
from app.tools.search_tools import clear_search_index_cache


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild hybrid search index for current WORKSPACE_ROOT / SEARCH_MODE",
    )
    parser.add_argument(
        "--save-dir",
        default=None,
        help="索引落盘目录（默认用配置 SEARCH_INDEX_DIR）",
    )
    args = parser.parse_args(argv)

    # 清进程缓存，避免与旧索引混用（本 CLI 通常是新进程，仍显式调用更清晰）
    clear_search_index_cache()
    get_settings.cache_clear()
    settings = get_settings()
    mode = normalize_search_mode(settings)
    root = get_workspace_root(settings)
    print(f"reindex: mode={mode} workspace={root}")

    try:
        index, out = build_and_save_hybrid(
            settings=settings,
            index_dir=args.save_dir,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"reindex failed: {exc}", file=sys.stderr)
        return 1

    print(f"reindex ok: chunks={index.size()} saved={out}")
    man_path = out / "manifest.json"
    if man_path.is_file():
        man = json.loads(man_path.read_text(encoding="utf-8"))
        print(
            "manifest:",
            json.dumps(
                {
                    "backend": man.get("backend"),
                    "search_mode": man.get("search_mode"),
                    "chunk_count": man.get("chunk_count"),
                    "max_chunks": man.get("max_chunks"),
                },
                ensure_ascii=False,
            ),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
