"""应用配置：从环境变量 / .env 加载（pydantic-settings）。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """与 .env.example 字段对应；改配置后需 clear get_settings 缓存。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # OpenAI 兼容：本机隧道 → 实验室 vLLM Qwen
    openai_base_url: str = "http://127.0.0.1:18000/v1"
    openai_api_key: str = "EMPTY"
    model_name: str = "/home/data/data_taihy/Qwen2.5-32B-AWQ"
    max_steps: int = 10

    # MCP 网关；enabled=false 时用本地 add/echo 做离线演示
    mcp_gateway_url: str = "http://127.0.0.1:8090/mcp"
    mcp_enabled: bool = False
    mcp_caller_id: str = "yu-manus-langgraph"

    api_host: str = "127.0.0.1"
    api_port: int = 8200

    # CE-2.1：Agent 可读写沙箱根。默认 artifacts/agent_workspace（勿用仓库根，避免作文等落到源码旁）
    # 相对路径相对仓库根解析；要改真实工程时设 WORKSPACE_ROOT=目标路径
    workspace_root: str = "artifacts/agent_workspace"

    # CA-1：写文件安全阀（S1 纯函数；S2 再挂工具）
    max_write_bytes: int = 512_000  # UTF-8 编码后上限
    write_backup: bool = True  # 覆盖前写 *.ca1.bak

    # CA-2：受控 shell
    shell_timeout_sec: float = 60.0
    shell_max_output_chars: int = 80_000

    # CA-4：LangGraph SQLite checkpointer（相对仓库根或绝对路径）
    checkpoint_sqlite_path: str = "artifacts/checkpoints/manus.sqlite"
    checkpoint_enabled: bool = True

    # CA-6 HITL：总开关。false 时 policy 全部 allow_auto（S3 接闸后才真正改执行路径）
    hitl_enabled: bool = True

    # CE-3：工具结果字符数 ≥ 该阈值则本机落盘，回喂路径+预览（可手动删产物，无自动 GC）
    tool_result_file_threshold: int = 1000
    tool_output_dir: str = "artifacts/tool_outputs"

    # CE-5 最小投影：发给模型的最近回合数（完备摘要/线索见待办 CTX-1）
    context_max_turns: int = 5

    # CE-6 / IDX-WS：语料范围 / 切块 / 索引产物（路径相对 workspace）
    # search_mode：workspace=扫整个工作区；corpus=只扫 search_corpus_dir（旧 Demo 兼容）
    search_mode: str = "workspace"
    search_corpus_dir: str = "artifacts/corpus"
    search_index_dir: str = "artifacts/search_index"
    search_chunk_lines: int = 40  # 行窗长度
    search_chunk_overlap: int = 10  # 相邻块重叠行数
    # 目录黑名单（逗号分隔；路径任一层同名即跳过，如 .venv）
    search_ignore_dirs: str = (
        ".git,.venv,venv,node_modules,__pycache__,"
        ".pytest_cache,search_index,.idea,.vscode"
    )
    # 文件 glob 白名单（逗号分隔；只索引匹配类型）
    search_globs: str = (
        "*.py,*.md,*.txt,*.json,*.yml,*.yaml,*.toml,"
        "*.java,*.ts,*.tsx,*.js,*.go"
    )
    # 安全阀：单文件过大→跳过该文件；整仓 chunk 过多→建索引报错
    search_max_file_bytes: int = 512_000
    search_max_chunks: int = 8000

    # EMB-1：仅 bge（http）。禁止 stub 回退；测 EMB 前须开隧道 18001→8001
    embedding_backend: str = "http"
    embedding_base_url: str = "http://127.0.0.1:18001/v1"
    embedding_api_key: str = "EMPTY"
    embedding_model: str = "bge-m3"
    embedding_timeout: float = 60.0
    # 实验室实测（Qwen 已占双卡大半显存时，2026-11-24 探针）：
    # - 单条到 ~2000～3000 字 + batch≤4 较稳；4000+ 或 batch=8 易 HTTP 500/OOM
    # - 服务端 500 时 embed 仍会自动拆半重试
    embedding_max_batch: int = 4
    embedding_max_chars: int = 2000

    # CE-6 hybrid：embedding 权重 alpha；BM25 权重为 1-alpha
    hybrid_alpha: float = 0.5


@lru_cache
def get_settings() -> Settings:
    """进程内单例；测试里改环境后请调用 get_settings.cache_clear()。"""
    return Settings()
