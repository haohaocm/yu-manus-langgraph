# 2026-11-25 SSE-TOK：仅 summarize 正文 token 流式

## 范围

- `summarize`：`llm.stream` + LangGraph `StreamWriter`（`custom`）推 `token`
- `iter_manus_events`：`stream_mode=["updates","custom"]` 转发
- `/stream`：`#answer` 边收 `delta` 边画；`done` 用终稿校正
- 事件流仍整节点；**不做** reason token

## 验收

- `pytest tests/test_sse_tok_summarize.py tests/test_ca5_stream.py -q` → 通过  
- 假模型：`''.join(token.delta) == done.answer`

## 试玩

重启 `python -m app.main` 后打开 http://127.0.0.1:8200/stream  

## 下一主线

**CA-6** HITL。
