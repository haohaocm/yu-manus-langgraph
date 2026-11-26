"""
FastAPI 入口（端口默认 8200）。

以后 Java 业务侧只需转发到本服务；浏览器请用 GET / 试跑页，正式接口为 POST /agent/run。
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app import __version__
from app.config import get_settings
from app.manus import (
    iter_manus_events,
    iter_manus_hitl_resume,
    read_thread_history,
    read_thread_state,
    run_manus,
)
from app.search.compare_demo import compare_bge_search
from app.search.embed import EmbeddingError, get_embedder
from app.tasks.store import get_task_store

app = FastAPI(title="yu-manus-langgraph", version=__version__)


class AgentRunRequest(BaseModel):
    message: str = Field(..., min_length=1)
    # CA-4：与 thread_id 同义；续跑请传上次返回的值
    session_id: str | None = None
    thread_id: str | None = Field(
        default=None,
        description="LangGraph checkpoint thread；空则新建；与 session_id 二选一即可",
    )
    max_steps: int | None = Field(default=None, ge=1, le=50)


class AgentRunResponse(BaseModel):
    """answer / final_answer：给用户看的总结；step_logs：内部轨迹。"""

    answer: str
    final_answer: str = ""
    status: str
    end_reason: str = ""
    steps: int
    step_logs: list[str]
    session_id: str | None = None
    thread_id: str | None = None
    task_id: str | None = None


class EmbedCompareRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    # 本地试玩：填绝对路径或相对项目根的路径；浏览器无法直接「选文件夹」给服务端
    workspace_root: str | None = Field(
        default=None,
        description="要索引的工程根；默认 jieba 演示仓或 .env 的 WORKSPACE_ROOT",
    )
    search_mode: str = Field(default="workspace")
    rebuild: bool = Field(default=False, description="强制重建索引（改文件后勾选）")


_INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>YuManus LangGraph</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; }
    textarea { width: 100%; min-height: 100px; }
    button { margin-top: 0.75rem; padding: 0.5rem 1rem; }
    pre { background: #f4f4f4; padding: 1rem; overflow: auto; white-space: pre-wrap; }
    .hint { color: #555; font-size: 0.9rem; }
  </style>
</head>
<body>
  <h1>YuManus LangGraph</h1>
  <p class="hint">浏览器地址栏是 GET；业务接口是 POST <code>/agent/run</code>。请优先看 <code>answer</code>（最终答复）；<code>status</code>/<code>end_reason</code> 为结束语义；<code>step_logs</code> 为内部步骤。打开 <a href="/docs">/docs</a>。bge：<a href="/embed-compare">/embed-compare</a>。流式：<a href="/stream"><strong>/stream</strong></a>。</p>
  <form id="f">
    <label>message<br/><textarea name="message" required>请调用 add 计算 2+3，然后 terminate，outcome=success，reason=done。</textarea></label>
    <br/>
    <label>max_steps <input name="max_steps" type="number" value="8" min="1" max="50" /></label>
    <br/>
    <button type="submit">运行 Agent</button>
  </form>
  <h2>结果</h2>
  <pre id="out">等待提交…</pre>
  <script>
    const f = document.getElementById('f');
    const out = document.getElementById('out');
    f.addEventListener('submit', async (e) => {
      e.preventDefault();
      out.textContent = '运行中…';
      const fd = new FormData(f);
      const body = {
        message: fd.get('message'),
        max_steps: Number(fd.get('max_steps') || 8)
      };
      try {
        const r = await fetch('/agent/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });
        const text = await r.text();
        out.textContent = text;
      } catch (err) {
        out.textContent = String(err);
      }
    });
  </script>
</body>
</html>
"""


_STREAM_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>YuManus SSE 流式试玩</title>
  <style>
    :root { --bg: #0f1419; --panel: #1a2332; --text: #e7ecf3; --muted: #8b9bb4; --accent: #3d9cf0; --ok: #3dd68c; --warn: #f0c14d; }
    * { box-sizing: border-box; }
    body { font-family: "Segoe UI", system-ui, sans-serif; background: var(--bg); color: var(--text); max-width: 880px; margin: 0 auto; padding: 1.5rem; }
    h1 { font-size: 1.4rem; margin: 0 0 0.5rem; }
    .hint { color: var(--muted); font-size: 0.9rem; margin-bottom: 1rem; }
    a { color: var(--accent); }
    textarea, input { width: 100%; background: var(--panel); color: var(--text); border: 1px solid #2a3548; border-radius: 8px; padding: 0.6rem 0.75rem; }
    textarea { min-height: 90px; }
    button { margin-top: 0.75rem; margin-right: 0.5rem; padding: 0.55rem 1.1rem; border: 0; border-radius: 8px; background: var(--accent); color: #fff; cursor: pointer; font-weight: 600; }
    button.secondary { background: #2a3548; }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    #feed { background: var(--panel); border-radius: 10px; padding: 0.75rem 1rem; min-height: 280px; max-height: 55vh; overflow: auto; font-family: ui-monospace, Consolas, monospace; font-size: 0.85rem; line-height: 1.45; }
    .ev { margin: 0.35rem 0; padding: 0.35rem 0.5rem; border-left: 3px solid #3a4a63; }
    .ev.start { border-color: var(--accent); }
    .ev.node { border-color: #7aa2f7; }
    .ev.done { border-color: var(--ok); }
    .ev.error { border-color: #f07178; }
    .tag { display: inline-block; font-size: 0.75rem; padding: 0.1rem 0.4rem; border-radius: 4px; background: #243044; margin-right: 0.4rem; color: var(--warn); }
    #answer { margin-top: 1rem; white-space: pre-wrap; background: #132018; border: 1px solid #1e3d2f; border-radius: 10px; padding: 0.9rem 1rem; min-height: 3rem; }
  </style>
</head>
<body>
  <h1>SSE 流式试玩（CA-5 + SSE-TOK + HITL）</h1>
  <p class="hint">事件流=图节点；最终 answer=summarize token；写文件/shell 会 <code>hitl_required</code> 等人批。同页续聊复用 thread。返回 <a href="/">首页</a></p>
  <label>message<br/><textarea id="msg">请用 write_file 把内容 hello-hitl 写到 outputs/hitl_demo.txt，然后 terminate 成功结束。</textarea></label>
  <br/><br/>
  <label>max_steps <input id="steps" type="number" value="8" min="1" max="50" style="width:6rem"/></label>
  <br/>
  <p class="hint">当前 thread：<code id="tidShow">（尚未开始）</code></p>
  <button id="go" type="button">开始流式运行</button>
  <button id="stop" class="secondary" type="button" disabled>停止</button>
  <button id="newChat" class="secondary" type="button">新对话</button>
  <div id="hitlBox" style="display:none;margin-top:1rem;padding:0.9rem 1rem;border:1px solid #f0c14d;border-radius:10px;background:#2a2416;">
    <h2 style="margin:0 0 0.5rem;font-size:1.05rem;">待人工确认（HITL）</h2>
    <p class="hint" id="hitlMeta"></p>
    <pre id="hitlDiff" style="white-space:pre-wrap;max-height:220px;overflow:auto;background:#1a1510;padding:0.6rem;border-radius:8px;"></pre>
    <label>备注（可选）<input id="hitlNote" style="width:100%;margin-top:0.35rem"/></label>
    <br/>
    <button id="hitlApprove" type="button">批准</button>
    <button id="hitlReject" class="secondary" type="button">拒绝</button>
  </div>
  <h2>事件流</h2>
  <div id="feed"></div>
  <h2>最终 answer</h2>
  <div id="answer">（尚未完成）</div>
  <script>
    let es = null;
    const THREAD_KEY = 'yu_manus_stream_thread_id';
    const feed = document.getElementById('feed');
    const answer = document.getElementById('answer');
    const go = document.getElementById('go');
    const stop = document.getElementById('stop');
    const tidShow = document.getElementById('tidShow');
    const hitlBox = document.getElementById('hitlBox');

    function currentThread() {
      return localStorage.getItem(THREAD_KEY) || '';
    }
    function setThread(id) {
      if (id) localStorage.setItem(THREAD_KEY, id);
      else localStorage.removeItem(THREAD_KEY);
      tidShow.textContent = id || '（尚未开始 / 已新对话）';
    }
    setThread(currentThread() || '');

    function addEv(cls, html) {
      const d = document.createElement('div');
      d.className = 'ev ' + cls;
      d.innerHTML = html;
      feed.appendChild(d);
      feed.scrollTop = feed.scrollHeight;
    }

    function hideHitl() { hitlBox.style.display = 'none'; }

    function showHitl(data) {
      hitlBox.style.display = 'block';
      document.getElementById('hitlMeta').textContent =
        'tool=' + (data.tool||'') + ' path=' + (data.path||'') + ' command=' + (data.command||'') + ' risk=' + (data.risk||'');
      document.getElementById('hitlDiff').textContent =
        data.diff_text || data.preview_text || JSON.stringify(data.proposal || data, null, 2);
      document.getElementById('hitlNote').value = '';
    }

    function closeEs() {
      if (es) { es.close(); es = null; }
      go.disabled = false;
      stop.disabled = true;
    }

    function bindEsHandlers() {
      es.onmessage = (ev) => {
        let data;
        try { data = JSON.parse(ev.data); } catch (e) {
          addEv('error', '<span class="tag">parse</span>' + ev.data);
          return;
        }
        const t = data.type || '?';
        if (data.thread_id) setThread(data.thread_id);
        if (t === 'start' || t === 'hitl_resumed') {
          const resumeTag = data.resumed ? ' <span class="tag">续聊</span>' :
            (t === 'hitl_resumed' ? ' <span class="tag">HITL恢复</span>' : ' <span class="tag">新会话</span>');
          addEv('start', '<span class="tag">' + t + '</span>' + resumeTag + ' task=' + (data.task_id||'') + ' · ' + (data.message_preview || data.decision || ''));
        } else if (t === 'token') {
          if (answer.textContent === '运行中…' || answer.textContent === '等待 HITL…') answer.textContent = '';
          answer.textContent += (data.delta || '');
        } else if (t === 'node') {
          let body = '<span class="tag">' + (data.node||'node') + '</span>';
          if (data.think_preview) body += ' think: ' + data.think_preview;
          if (data.tool_calls) body += ' calls=' + JSON.stringify(data.tool_calls);
          if (data.tool) body += ' tool=' + data.tool + ' → ' + (data.tool_preview||'');
          if (data.log_tail) body += ' · ' + data.log_tail;
          if (data.final_answer) body += ' · answer≈ ' + data.final_answer;
          if (data.plan && data.plan.length) body += ' · plan=' + JSON.stringify(data.plan);
          addEv('node', body);
        } else if (t === 'hitl_required') {
          addEv('node', '<span class="tag">hitl_required</span> tool=' + (data.tool||'') + ' path=' + (data.path||''));
          showHitl(data);
          answer.textContent = '等待 HITL…';
          if (es) { es.close(); es = null; }
          stop.disabled = true;
          go.disabled = false;
        } else if (t === 'done') {
          hideHitl();
          addEv('done', '<span class="tag">done</span>status=' + data.status + ' steps=' + data.steps);
          answer.textContent = data.answer || data.final_answer || answer.textContent || '(empty)';
          closeEs();
        } else if (t === 'error') {
          hideHitl();
          addEv('error', '<span class="tag">error</span>' + (data.error||''));
          answer.textContent = '错误：' + (data.error||'');
          closeEs();
        } else {
          addEv('node', '<span class="tag">' + t + '</span>' + JSON.stringify(data));
        }
      };
      es.onerror = () => {
        addEv('error', '<span class="tag">sse</span>连接中断或后端错误（若已 done/HITL 可忽略）');
        if (hitlBox.style.display === 'none') closeEs();
        else { if (es) { es.close(); es = null; } }
      };
    }

    function startHitlResume(decision) {
      hideHitl();
      const tid = currentThread();
      if (!tid) { addEv('error', '无 thread_id'); return; }
      answer.textContent = 'HITL 恢复中…';
      go.disabled = true;
      stop.disabled = false;
      const q = new URLSearchParams({
        thread_id: tid,
        decision: decision,
        note: document.getElementById('hitlNote').value || ''
      });
      es = new EventSource('/agent/hitl/resume?' + q.toString());
      bindEsHandlers();
    }

    document.getElementById('hitlApprove').onclick = () => startHitlResume('approve');
    document.getElementById('hitlReject').onclick = () => startHitlResume('reject');

    stop.onclick = () => closeEs();
    document.getElementById('newChat').onclick = () => {
      closeEs();
      hideHitl();
      setThread('');
      feed.innerHTML = '';
      answer.textContent = '（新对话，尚未运行）';
    };

    go.onclick = () => {
      closeEs();
      hideHitl();
      feed.innerHTML = '';
      answer.textContent = '运行中…';
      go.disabled = true;
      stop.disabled = false;
      const q = new URLSearchParams({
        message: document.getElementById('msg').value,
        max_steps: String(document.getElementById('steps').value || 8)
      });
      const tid = currentThread();
      if (tid) q.set('thread_id', tid);
      es = new EventSource('/agent/stream?' + q.toString());
      bindEsHandlers();
    };
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """首页：非流式试跑表单。"""
    return _INDEX_HTML


@app.get("/stream", response_class=HTMLResponse)
def stream_page() -> str:
    """CA-5：SSE 流式试玩前端。"""
    return _STREAM_HTML


@app.get("/agent/stream")
def agent_stream(
    message: str = Query(..., min_length=1),
    max_steps: int | None = Query(default=8, ge=1, le=50),
    thread_id: str | None = Query(default=None),
):
    """
    CA-5 + SSE-TOK + HITL：节点事件 / summarize token；遇审批则 ``hitl_required``。

    浏览器可用 EventSource 订阅；每条 ``data:`` 为一行 JSON。
    """

    def event_gen():
        try:
            for ev in iter_manus_events(
                message.strip(),
                max_steps=max_steps,
                thread_id=thread_id,
                persist_event_log=True,
            ):
                payload = json.dumps(ev, ensure_ascii=False)
                yield f"data: {payload}\n\n"
        except Exception as exc:  # noqa: BLE001
            err = json.dumps({"type": "error", "error": str(exc)}, ensure_ascii=False)
            yield f"data: {err}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/agent/hitl/resume")
def agent_hitl_resume(
    thread_id: str = Query(..., min_length=1),
    decision: str = Query(..., pattern="^(approve|reject)$"),
    note: str = Query(default=""),
):
    """
    CA-6：人对 ``hitl_required`` 点批准/拒绝后，用 SSE 继续推送后续事件。

    EventSource 只能 GET，故用 query 传 decision，而不是 POST body。
    """

    def event_gen():
        try:
            for ev in iter_manus_hitl_resume(
                thread_id.strip(),
                decision=decision,
                note=note or "",
                persist_event_log=True,
            ):
                payload = json.dumps(ev, ensure_ascii=False)
                yield f"data: {payload}\n\n"
        except Exception as exc:  # noqa: BLE001
            err = json.dumps({"type": "error", "error": str(exc)}, ensure_ascii=False)
            yield f"data: {err}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "UP", "app": "yu-manus-langgraph", "version": __version__}


_COMPARE_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>bge hybrid search</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }
    textarea, input[type=text] { width: 100%; box-sizing: border-box; }
    textarea { min-height: 72px; }
    button { margin-top: 0.75rem; padding: 0.5rem 1rem; }
    pre { background: #f4f4f4; padding: 1rem; overflow: auto; white-space: pre-wrap; }
    .hint { color: #555; font-size: 0.9rem; }
    label { display: block; margin-top: 0.6rem; }
  </style>
</head>
<body>
  <h1>bge hybrid 全仓检索试玩</h1>
  <p class="hint">
    仅 bge（无 stub）。须开隧道 <code>18001→8001</code>。
    在下方填<strong>本机文件夹路径</strong>（资源管理器地址栏复制即可；浏览器无法把「选中的文件夹」直接传给服务器）。
    返回 <a href="/">Agent 试跑</a>。
  </p>
  <form id="f">
    <label>工作区路径 workspace_root<br/>
      <input type="text" name="workspace_root" id="ws"
        value="artifacts/workspace_demos/github_jieba" />
    </label>
    <p class="hint">快捷：jieba 演示仓已预填；也可改成 sample_forge 或其它工程绝对路径。</p>
    <button type="button" id="btn-jieba">填入 jieba</button>
    <button type="button" id="btn-forge">填入 sample_forge</button>
    <label>query<br/><textarea name="query" required>中文分词 精确模式 搜索引擎模式</textarea></label>
    <label>top_k <input name="top_k" type="number" value="5" min="1" max="20" /></label>
    <label>search_mode
      <select name="search_mode">
        <option value="workspace" selected>workspace（全仓）</option>
        <option value="corpus">corpus（仅 SEARCH_CORPUS_DIR）</option>
      </select>
    </label>
    <label><input type="checkbox" name="rebuild" id="rebuild" /> 强制重建索引 rebuild</label>
    <br/>
    <button type="submit">检索打分</button>
  </form>
  <p id="meta" class="hint"></p>
  <pre id="out">等待…</pre>
  <script>
    document.getElementById('btn-jieba').onclick = () => {
      document.getElementById('ws').value = 'artifacts/workspace_demos/github_jieba';
    };
    document.getElementById('btn-forge').onclick = () => {
      document.getElementById('ws').value = 'artifacts/corpus/sample_forge';
    };
    const f = document.getElementById('f');
    f.addEventListener('submit', async (e) => {
      e.preventDefault();
      document.getElementById('out').textContent = '运行中（首次全仓 embed 可能较慢）…';
      document.getElementById('meta').textContent = '';
      const fd = new FormData(f);
      const body = {
        query: fd.get('query'),
        top_k: Number(fd.get('top_k') || 5),
        workspace_root: fd.get('workspace_root'),
        search_mode: fd.get('search_mode') || 'workspace',
        rebuild: document.getElementById('rebuild').checked
      };
      try {
        const r = await fetch('/api/embed-compare', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });
        const data = await r.json();
        if (!data.ok) {
          document.getElementById('out').textContent = data.error || JSON.stringify(data, null, 2);
          return;
        }
        document.getElementById('meta').textContent =
          `workspace=${data.workspace_root} mode=${data.search_mode} chunks=${data.chunk_count} alpha=${data.alpha} backend=${data.bge.backend} dim=${data.bge.dim} rebuild=${data.rebuild}`;
        document.getElementById('out').textContent = (data.bge.hits || []).map(h =>
          `${h.rank}. hybrid=${h.hybrid} bm25=${h.bm25_raw} emb=${h.emb_raw}\\n   ${h.path}\\n   ${h.excerpt}`
        ).join('\\n\\n');
      } catch (err) {
        document.getElementById('out').textContent = String(err);
      }
    });
  </script>
</body>
</html>
"""


@app.get("/embed-compare", response_class=HTMLResponse)
def embed_compare_page() -> str:
    return _COMPARE_HTML


@app.post("/api/embed-compare")
def embed_compare_api(body: EmbedCompareRequest) -> dict[str, Any]:
    return compare_bge_search(
        body.query,
        top_k=body.top_k,
        workspace_root=body.workspace_root,
        search_mode=body.search_mode,
        rebuild=body.rebuild,
    )


@app.get("/api/embed-ping")
def embed_ping() -> dict[str, Any]:
    """探测当前默认 embedder（http 时即 bge）。"""
    try:
        emb = get_embedder()
        if hasattr(emb, "ping"):
            return {"backend": emb.name, **emb.ping()}  # type: ignore[misc]
        vecs = emb.embed(["ping"])
        return {"backend": emb.name, "ok": True, "dim": len(vecs[0]) if vecs else None}
    except EmbeddingError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}



@app.get("/agent/run")
def agent_run_get_help(
    message: str | None = Query(default=None, description="若提供则直接以 GET 试跑（仅便于浏览器调试）"),
    max_steps: int | None = Query(default=None, ge=1, le=50),
):
    """
    浏览器直接打开本路径时是 GET。
    - 不带参数：返回用法说明（不再 405）
    - 带 ?message=...：方便地址栏快速试跑
    """
    if message and message.strip():
        result = run_manus(message.strip(), max_steps=max_steps)
        tid = result.get("thread_id")
        return AgentRunResponse(
            answer=result["answer"],
            final_answer=result.get("final_answer") or result["answer"],
            status=result["status"],
            end_reason=result.get("end_reason") or "",
            steps=result["steps"],
            step_logs=result["step_logs"],
            session_id=tid,
            thread_id=tid,
            task_id=result.get("task_id") or tid,
        )
    return JSONResponse(
        {
            "ok": True,
            "hint": "浏览器地址栏只能发 GET。正式调用请 POST /agent/run，或打开 / 、/docs 试跑。",
            "try": "http://127.0.0.1:8200/agent/run?message=请调用%20add%20计算%201%2B2%20然后%20terminate",
            "post_example": {
                "url": "/agent/run",
                "method": "POST",
                "body": {
                    "message": "请调用 add 计算 2+3，然后 terminate(outcome=success)",
                    "max_steps": 8,
                },
            },
            "ui": "/",
            "docs": "/docs",
        }
    )


@app.get("/agent/threads/{thread_id}")
def agent_thread_state(thread_id: str, history: bool = Query(default=False)):
    """CA-4：读 SQLite 中该 thread 的当前状态；history=true 时附带 checkpoint 历史。"""
    state = read_thread_state(thread_id)
    if history:
        return {"state": state, "history": read_thread_history(thread_id)}
    return state


@app.get("/agent/tasks")
def agent_list_tasks(limit: int = Query(default=20, ge=1, le=100)):
    """CA-4 S6：最近任务名片列表（不含 checkpoint 正文）。"""
    store = get_task_store()
    return {"tasks": [t.to_dict() for t in store.list_recent(limit=limit)]}


@app.get("/agent/tasks/{task_id}")
def agent_get_task(task_id: str):
    """CA-4 S6：单个任务名片。"""
    store = get_task_store()
    info = store.get(task_id)
    if info is None:
        return JSONResponse({"ok": False, "error": "task not found"}, status_code=404)
    return info.to_dict()


@app.post("/agent/run", response_model=AgentRunResponse)
def agent_run(body: AgentRunRequest) -> AgentRunResponse:
    """Run Manus once (sync)；可带 thread_id/session_id 续跑。"""
    tid = body.thread_id or body.session_id
    result = run_manus(body.message, max_steps=body.max_steps, thread_id=tid)
    out_tid = result.get("thread_id")
    out_task = result.get("task_id") or out_tid
    return AgentRunResponse(
        answer=result["answer"],
        final_answer=result.get("final_answer") or result["answer"],
        status=result["status"],
        end_reason=result.get("end_reason") or "",
        steps=result["steps"],
        step_logs=result["step_logs"],
        session_id=out_tid,
        thread_id=out_tid,
        task_id=out_task,
    )


def create_app() -> FastAPI:
    return app


if __name__ == "__main__":
    import uvicorn

    s = get_settings()
    uvicorn.run("app.main:app", host=s.api_host, port=s.api_port, reload=False)
