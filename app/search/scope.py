"""IDX-WS S1：检索扫描范围（scope）助手。

本模块**不负责**整棵目录树扫描（那是 S2 的 chunk_workspace）。
这里只提供「规则解析 + 判定函数」，供后续扫描时调用：

- ignore（忽略目录黑名单）：命中则不进索引
- globs（扩展名白名单）：只保留匹配的文件类型
- max_file_bytes：单文件过大则跳过（不删磁盘文件）
- max_chunks：整仓切块过多则报错（避免默默截断）
"""

from __future__ import annotations

from pathlib import Path

from app.config import Settings, get_settings

# 允许的 SEARCH_MODE 取值
_VALID_MODES = frozenset({"workspace", "corpus"})


class SearchScopeError(ValueError):
    """扫描范围或安全阀违反（例如 search_mode 非法、chunk 超限）。"""


def parse_csv_list(raw: str | None) -> tuple[str, ...]:
    """把逗号分隔的配置字符串拆成元组；去掉空白，忽略空段。"""
    if not raw:
        return ()
    return tuple(p.strip() for p in str(raw).split(",") if p.strip())


def normalize_search_mode(settings: Settings | None = None) -> str:
    """规范化 search_mode，非法值直接报错。"""
    s = settings or get_settings()
    mode = (s.search_mode or "workspace").strip().lower()
    if mode not in _VALID_MODES:
        raise SearchScopeError(
            f"invalid search_mode={s.search_mode!r}; expected 'workspace' or 'corpus'"
        )
    return mode


def ignore_dir_names(settings: Settings | None = None) -> frozenset[str]:
    """读取配置中的目录黑名单（如 .venv、node_modules）。"""
    s = settings or get_settings()
    return frozenset(parse_csv_list(s.search_ignore_dirs))


def search_glob_patterns(settings: Settings | None = None) -> tuple[str, ...]:
    """读取扩展名白名单；若配置为空则退回常见源码/文档后缀。"""
    s = settings or get_settings()
    globs = parse_csv_list(s.search_globs)
    return globs if globs else ("*.py", "*.md", "*.txt")


def path_has_ignored_dir(path: Path, ignore: frozenset[str]) -> bool:
    """路径任意一层目录名落在 ignore 中则视为应跳过。"""
    return any(part in ignore for part in path.parts)


def should_skip_directory(dir_path: Path, settings: Settings | None = None) -> bool:
    """扫描时是否跳过该目录（不进入其子树）。"""
    ignore = ignore_dir_names(settings)
    return dir_path.name in ignore or path_has_ignored_dir(dir_path, ignore)


def is_file_within_size_limit(
    file_path: Path,
    settings: Settings | None = None,
) -> bool:
    """判断单文件是否允许切块 / embedding。

    - 超过 search_max_file_bytes → False（调用方应跳过，不是删除文件）
    - 无法 stat → False
    - limit <= 0 → 视为不限制
    """
    s = settings or get_settings()
    limit = int(s.search_max_file_bytes)
    if limit <= 0:
        return True
    try:
        size = file_path.stat().st_size
    except OSError:
        return False
    return size <= limit


def ensure_chunk_budget(
    chunk_count: int,
    settings: Settings | None = None,
) -> None:
    """检查整仓 chunk 数是否超过 search_max_chunks。

    超限抛 SearchScopeError：建索引应失败，并提示收窄 ignore/globs 或改 mode。
    """
    s = settings or get_settings()
    limit = int(s.search_max_chunks)
    if limit <= 0:
        return
    if chunk_count > limit:
        raise SearchScopeError(
            f"chunk count {chunk_count} exceeds search_max_chunks={limit}; "
            "narrow SEARCH_IGNORE_DIRS / SEARCH_GLOBS, raise the limit, "
            "or set SEARCH_MODE=corpus"
        )
