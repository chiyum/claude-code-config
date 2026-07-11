#!/usr/bin/env python3
"""collect-run-metrics.py — 任務級 run 遙測收集器（telemetry 制度核心）

在五步驟步驟 5 回報前執行，解析本任務相關 session 的 transcript JSONL，
產出一筆 run 記錄到 ~/.claude/run-metrics/runs/<date>-<slug>.json。

用法：
  python3 collect-run-metrics.py --slug <任務slug> \
      [--sessions id1,id2]      # 明確指定 session id；省略時從 state/<slug>.json 的 session_id 取
      [--tasks-dir <path>]      # subagent transcript 目錄（可重複；本 harness 為 session scratch 的 tasks/）
      [--product <代號>] [--outcome done|blocked|aborted] [--notes "一句話"]

零 token 開銷：純本地檔案解析。transcript 有清理週期，務必在任務結束當下跑。
"""
import argparse, glob, json, os, re, subprocess, sys
from datetime import datetime, timezone

HOME = os.path.expanduser("~")
CLAUDE = os.path.join(HOME, ".claude")
PROJECTS = os.path.join(CLAUDE, "projects")
RUNS_DIR = os.path.join(CLAUDE, "run-metrics", "runs")

USAGE_FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def new_usage():
    return {k: 0 for k in USAGE_FIELDS}


def add_usage(acc, u):
    for k in USAGE_FIELDS:
        v = u.get(k)
        if isinstance(v, (int, float)):
            acc[k] += int(v)


def iter_jsonl(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return


def find_session_files(session_ids):
    """在 ~/.claude/projects/*/ 找 session 主 transcript。"""
    files = []
    for sid in session_ids:
        hits = glob.glob(os.path.join(PROJECTS, "*", f"{sid}*.jsonl"))
        if not hits:
            print(f"[warn] 找不到 session transcript：{sid}", file=sys.stderr)
        files.extend(hits)
    return files


def parse_main_transcript(path, run):
    """主 transcript：主迴圈 usage、工具統計、agent 派遣（tool_use ↔ agentId 對映）、inline sidechain。"""
    agent_calls = run["agent_calls"]          # subagent_type -> 次數
    tool_counts = run["tool_counts"]          # tool name -> 次數
    pending = {}                              # tool_use_id -> subagent_type（等 tool_result 揭曉 agentId）
    agent_id_type = run.setdefault("_agent_id_type", {})  # agentId -> subagent_type
    ts_min, ts_max = run.get("_ts_min"), run.get("_ts_max")

    for o in iter_jsonl(path):
        ts = o.get("timestamp")
        if isinstance(ts, str):
            ts_min = ts if ts_min is None or ts < ts_min else ts_min
            ts_max = ts if ts_max is None or ts > ts_max else ts_max
        msg = o.get("message") or {}
        sidechain = bool(o.get("isSidechain"))
        u = msg.get("usage")
        if isinstance(u, dict):
            bucket = run["tokens"]["sidechain_inline"] if sidechain else run["tokens"]["main_loop"]
            add_usage(bucket, u)
            model = msg.get("model")
            if model:
                add_usage(run["tokens_by_model"].setdefault(model, new_usage()), u)
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use":
                name = b.get("name", "?")
                tool_counts[name] = tool_counts.get(name, 0) + 1
                if name in ("Task", "Agent"):
                    st = (b.get("input") or {}).get("subagent_type") or "unspecified"
                    agent_calls[st] = agent_calls.get(st, 0) + 1
                    pending[b.get("id")] = st
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in pending:
                st = pending.pop(b.get("tool_use_id"))
                text = ""
                c = b.get("content")
                if isinstance(c, str):
                    text = c
                elif isinstance(c, list):
                    text = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
                m = re.search(r"agentId:\s*([0-9a-f]{8,})", text)
                if m:
                    agent_id_type[m.group(1)] = st
        # user turn 內的 task-notification 也可能帶 subagent_tokens（備援統計）
        if o.get("type") == "user" and isinstance(msg.get("content"), list):
            for b in msg["content"]:
                if isinstance(b, dict) and b.get("type") == "text":
                    for tid, tok in re.findall(r"<task-id>([0-9a-f]+)</task-id>.*?<subagent_tokens>(\d+)</subagent_tokens>", b.get("text", ""), re.S):
                        run["_notif_tokens"][tid] = int(tok)
    run["_ts_min"], run["_ts_max"] = ts_min, ts_max


def parse_agent_outputs(tasks_dirs, run):
    """subagent 獨立 transcript（tasks/<agentId>.output 或 .jsonl）→ 按 agent 類型分帳。"""
    agent_id_type = run.get("_agent_id_type", {})
    for d in tasks_dirs:
        for path in glob.glob(os.path.join(d, "*")):
            base = os.path.basename(path)
            aid = re.sub(r"\.(output|jsonl)$", "", base)
            if not re.fullmatch(r"[0-9a-f]{8,}", aid):
                continue
            usage = new_usage()
            n = 0
            for o in iter_jsonl(path):
                u = (o.get("message") or {}).get("usage")
                if isinstance(u, dict):
                    add_usage(usage, u)
                    n += 1
            if n == 0:
                continue
            st = agent_id_type.get(aid, "unknown")
            bucket = run["tokens_by_agent"].setdefault(st, new_usage())
            add_usage(bucket, usage)
            run["_seen_agent_files"].add(aid)


def apply_notification_fallback(run):
    """沒有 transcript 檔的 agent，用 task-notification 的 subagent_tokens 補 output 概數。"""
    for tid, tok in run.get("_notif_tokens", {}).items():
        if tid in run["_seen_agent_files"]:
            continue
        st = run.get("_agent_id_type", {}).get(tid, "unknown")
        bucket = run["tokens_by_agent"].setdefault(st, new_usage())
        bucket["output_tokens"] += tok  # 通知只給總數，記為 output 概數


def config_commit():
    try:
        return subprocess.run(["git", "-C", CLAUDE, "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--sessions", default="")
    ap.add_argument("--tasks-dir", action="append", default=[])
    ap.add_argument("--product", default="")
    ap.add_argument("--outcome", default="done")
    ap.add_argument("--notes", default="")
    args = ap.parse_args()

    session_ids = [s for s in args.sessions.split(",") if s.strip()]
    state_path = os.path.join(CLAUDE, "state", f"{args.slug}.json")
    if not session_ids and os.path.exists(state_path):
        try:
            st = json.load(open(state_path))
            for key in ("session_id", "session_ids", "sessions"):
                v = st.get(key)
                if isinstance(v, str):
                    session_ids.append(v)
                elif isinstance(v, list):
                    session_ids.extend(v)
        except Exception as e:
            print(f"[warn] 讀 state 檔失敗：{e}", file=sys.stderr)
    if not session_ids:
        print("錯誤：無 session id（--sessions 或 state/<slug>.json 的 session_id 皆空）", file=sys.stderr)
        sys.exit(1)

    run = {
        "slug": args.slug,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config_commit": config_commit(),
        "product": args.product,
        "sessions": session_ids,
        "outcome": args.outcome,
        "notes": args.notes,
        "verdict": None,          # good | ok | bad — 使用者驗收後由主 Claude 寫入
        "verdict_comment": None,
        "tokens": {"main_loop": new_usage(), "sidechain_inline": new_usage()},
        "tokens_by_model": {},
        "tokens_by_agent": {},    # subagent_type -> usage
        "agent_calls": {},        # subagent_type -> 派遣次數（reviewer 次數≈審查回合數）
        "tool_counts": {},
        "_notif_tokens": {},
        "_seen_agent_files": set(),
    }

    for f in find_session_files(session_ids):
        parse_main_transcript(f, run)

    tasks_dirs = list(args.tasks_dir)
    for sid in session_ids:  # 常見兩種歷史位置自動補搜
        tasks_dirs += [os.path.join(CLAUDE, "tasks", sid), os.path.join(CLAUDE, "tasks", f"session-{sid[:8]}")]
    parse_agent_outputs([d for d in tasks_dirs if os.path.isdir(d)], run)
    apply_notification_fallback(run)

    run["duration"] = {"first_ts": run.pop("_ts_min", None), "last_ts": run.pop("_ts_max", None)}
    total = new_usage()
    for bucket in [run["tokens"]["main_loop"], run["tokens"]["sidechain_inline"], *run["tokens_by_agent"].values()]:
        add_usage(total, bucket)
    run["tokens"]["total"] = total
    for k in ("_notif_tokens", "_seen_agent_files", "_agent_id_type"):
        run.pop(k, None)

    os.makedirs(RUNS_DIR, exist_ok=True)
    # slug 已以 YYYYMMDD- 開頭時不再重複加日期前綴
    fname = args.slug if re.match(r"^\d{8}-", args.slug) else f"{run['date'].replace('-', '')}-{args.slug}"
    out = os.path.join(RUNS_DIR, f"{fname}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(run, f, ensure_ascii=False, indent=2)

    t = run["tokens"]["total"]
    print(f"run 記錄已寫入 {out}")
    print(f"total: in={t['input_tokens']:,} out={t['output_tokens']:,} "
          f"cache_write={t['cache_creation_input_tokens']:,} cache_read={t['cache_read_input_tokens']:,}")
    print(f"agent 派遣: {run['agent_calls'] or '（無）'}")
    for st, u in sorted(run["tokens_by_agent"].items(), key=lambda x: -x[1]["output_tokens"]):
        print(f"  {st}: out={u['output_tokens']:,} in={u['input_tokens']:,}")


if __name__ == "__main__":
    main()
