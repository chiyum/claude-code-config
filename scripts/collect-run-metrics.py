#!/usr/bin/env python3
"""collect-run-metrics.py — 任務級 run 遙測收集器（telemetry 制度核心）

在五步驟步驟 5 回報前執行，解析本任務相關 session 的 transcript JSONL，
產出一筆 run 記錄到 ~/.claude/run-metrics/runs/<date>-<slug>.json。

用法：
  python3 collect-run-metrics.py --slug <任務slug> \
      [--sessions id1,id2]      # 明確指定 session id；省略時從 state/<slug>.json 的 session_id 取
      [--started-at ISO] [--ended-at ISO]
                                # 任務時間窗；省略時從 state/<slug>.json 的 started_at / ended_at 取。
                                # 一個 session 常連續做多個任務，不切窗會把整段 session 的量
                                # 全額計給每個任務（2026-08-22 複盤：13 組 session 污染 30 筆 run）。
      [--tasks-dir <path>]      # subagent transcript 目錄（可重複；本 harness 為 session scratch 的 tasks/）
      [--product <代號>] [--outcome done|blocked|aborted] [--notes "一句話"]

零 token 開銷：純本地檔案解析。transcript 有清理週期，務必在任務結束當下跑。
"""
import argparse, glob, json, os, re, subprocess, sys
from datetime import datetime, timezone

HOME = os.path.expanduser("~")
CLAUDE = os.path.join(HOME, ".claude")
RUNS_DIR = os.path.join(CLAUDE, "run-metrics", "runs")


def project_roots():
    """所有可能存放 session transcript 的 projects 根目錄。

    2026-08 起 profile 機制把 transcript 實體搬到 ~/.ai-profiles/<tool>/<profile>/projects/，
    ~/.claude/projects/ 只剩少數 symlink 與搬遷前的歷史檔。只找舊路徑會對「當前 session」
    一律落空——而落空以前是靜默寫一筆全 0 紀錄，看起來與「真的零成本」無法區分。
    這裡兩處都找，並在 find_session_files 以 realpath 去重（symlink 與本體同時命中會重複計 token）。
    """
    roots = [os.path.join(CLAUDE, "projects")]
    roots += sorted(glob.glob(os.path.join(HOME, ".ai-profiles", "*", "*", "projects")))
    return [r for r in roots if os.path.isdir(r)]

USAGE_FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def parse_ts(v):
    """ISO8601 → aware datetime（UTC）。無法解析回 None。

    transcript 的 timestamp 形如 2026-08-20T18:15:22.478Z；state 檔的 started_at 由主 Claude
    手寫，可能帶 offset 也可能是裸的本地時間。裸時間一律按本機時區解讀後轉 UTC，
    避免與 Z 結尾的 transcript 時間做出差 8 小時的錯誤比較。
    """
    if not isinstance(v, str) or not v.strip():
        return None
    t = v.strip().replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(t)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.astimezone()
    return d.astimezone(timezone.utc)


def in_window(ts_raw, window):
    """該筆訊息是否落在任務時間窗內。window 為 None 代表不切窗（全收）。

    切窗時無 timestamp 的物件一律排除：無法歸屬的量寧可不計，也不要默默記到別的任務頭上。
    """
    if window is None:
        return True
    lo, hi = window
    d = parse_ts(ts_raw)
    if d is None:
        return False
    if lo is not None and d < lo:
        return False
    if hi is not None and d > hi:
        return False
    return True


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
    """在所有 projects 根目錄找 session 主 transcript。

    回傳 (files, missing_ids)。files 以 realpath 去重：同一份 transcript 可能同時以
    symlink 出現在舊路徑、以本體出現在 profile 路徑，重複解析會讓 token 統計翻倍。
    """
    files, seen, missing = [], set(), []
    for sid in session_ids:
        hits = []
        for root in project_roots():
            hits += glob.glob(os.path.join(root, "*", f"{sid}*.jsonl"))
        fresh = []
        for h in hits:
            real = os.path.realpath(h)
            if real in seen:
                continue
            seen.add(real)
            fresh.append(real)
        if not fresh:
            missing.append(sid)
            print(f"[warn] 找不到 session transcript：{sid}", file=sys.stderr)
        files.extend(fresh)
    return files, missing


def parse_main_transcript(path, run, window=None):
    """主 transcript：主迴圈 usage、工具統計、agent 派遣（tool_use ↔ agentId 對映）、inline sidechain。

    window 為 (lo, hi) aware datetime 時，只計入落在任務時間窗內的訊息。
    """
    agent_calls = run["agent_calls"]          # subagent_type -> 次數
    tool_counts = run["tool_counts"]          # tool name -> 次數
    pending = {}                              # tool_use_id -> subagent_type（等 tool_result 揭曉 agentId）
    agent_id_type = run.setdefault("_agent_id_type", {})  # agentId -> subagent_type
    ts_min, ts_max = run.get("_ts_min"), run.get("_ts_max")

    for o in iter_jsonl(path):
        ts = o.get("timestamp")
        if not in_window(ts, window):
            continue
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


def parse_agent_outputs(tasks_dirs, run, window=None):
    """subagent 獨立 transcript（tasks/<agentId>.output 或 .jsonl）→ 按 agent 類型分帳。

    子 transcript 未必帶 timestamp；帶了就依 window 過濾，沒帶則整檔收下（該檔本就綁定
    單一 agentId，跨任務污染風險遠低於主 transcript）。
    """
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
                if o.get("timestamp") is not None and not in_window(o.get("timestamp"), window):
                    continue
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


# 制度檔案路徑：只有這些路徑的變動才算「制度版本」改變（config_commit 分組 key 的依據）。
# 不能直接用 repo HEAD——每補一張知識卡 / 寫一份驗收清單 HEAD 就跳一次，
# 導致每筆 run 綁到獨一無二的 commit，永遠湊不滿「同一制度版本 ≥5 筆」的比較門檻。
INSTITUTION_PATHS = ["CLAUDE.md", "agents", "skills", "scripts",
                     "DECISION_LOG.md", "DESIGN_FLOW.md"]


def config_commit():
    """取「制度檔案」最後一次被改動的 commit（而非 repo HEAD）作為分組 key。"""
    try:
        out = subprocess.run(
            ["git", "-C", CLAUDE, "log", "-1", "--format=%h", "--"] + INSTITUTION_PATHS,
            capture_output=True, text=True, timeout=10).stdout.strip()
        return out or "unknown"
    except Exception:
        return "unknown"



# ---- lane 試行欄位（~/.claude/acceptance/LANE_PROTOCOL.md §4／§5）----
LANE_QA_PM_QUOTA = {"S": 0, "M": 3, "L": 6}


def window_minutes(started_raw, ended_raw):
    """state 的 started_at~ended_at 換算成分鐘；缺一端或解析失敗回 None"""
    try:
        s = datetime.fromisoformat(started_raw)
        e = datetime.fromisoformat(ended_raw)
        return round((e - s).total_seconds() / 60, 1)
    except Exception:
        return None


def self_verdict(run):
    """機器自評（與使用者的 verdict 分欄）。規則見 LANE_PROTOCOL §5，回 (verdict, reason)"""
    calls = run.get("agent_calls") or {}
    est, act = run.get("estimated_minutes"), run.get("actual_minutes")
    live = int(run.get("live_regressions") or 0)
    reasons = []
    if run.get("user_aborted"):
        reasons.append("使用者中途喊停")
    if est and act and act > 2 * est:
        reasons.append(f"實際 {act:.0f} 分 > 2×預估 {est} 分")
    if live >= 2:
        reasons.append(f"線上回歸 {live} 個")
    if reasons:
        return "bad", "；".join(reasons)
    quota = LANE_QA_PM_QUOTA.get(run.get("lane"), 6)
    qa_pm = calls.get("qa", 0) + calls.get("pm", 0)
    if calls.get("reviewer", 0) > 1:
        reasons.append(f"reviewer {calls['reviewer']} 輪")
    if qa_pm > quota:
        reasons.append(f"qa+pm {qa_pm} 次 > lane 額度 {quota}")
    if live == 1:
        reasons.append("線上回歸 1 個")
    if int(run.get("gate_reruns") or 0) > 0:
        reasons.append(f"gate 重跑 {run['gate_reruns']} 次")
    if reasons:
        return "ok", "；".join(reasons)
    return "good", ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--sessions", default="")
    ap.add_argument("--started-at", default="", help="任務起始 ISO8601；省略時取 state 檔 started_at")
    ap.add_argument("--ended-at", default="", help="任務結束 ISO8601；省略時取 state 檔 ended_at，再省略為「至今」")
    ap.add_argument("--tasks-dir", action="append", default=[])
    ap.add_argument("--product", default="")
    ap.add_argument("--outcome", default="done")
    ap.add_argument("--notes", default="")
    args = ap.parse_args()

    session_ids = [s for s in args.sessions.split(",") if s.strip()]
    started_raw, ended_raw = args.started_at.strip(), args.ended_at.strip()
    state_path = os.path.join(CLAUDE, "state", f"{args.slug}.json")
    st = {}
    if os.path.exists(state_path):
        try:
            st = json.load(open(state_path))
            if not session_ids:
                for key in ("session_id", "session_ids", "sessions"):
                    v = st.get(key)
                    if isinstance(v, str):
                        session_ids.append(v)
                    elif isinstance(v, list):
                        session_ids.extend(v)
            started_raw = started_raw or (st.get("started_at") or "")
            ended_raw = ended_raw or (st.get("ended_at") or "")
        except Exception as e:
            print(f"[warn] 讀 state 檔失敗：{e}", file=sys.stderr)
    if not session_ids:
        print("錯誤：無 session id（--sessions 或 state/<slug>.json 的 session_id 皆空）", file=sys.stderr)
        sys.exit(1)

    lo, hi = parse_ts(started_raw), parse_ts(ended_raw)
    if started_raw and lo is None:
        print(f"[warn] started_at 無法解析，忽略：{started_raw!r}", file=sys.stderr)
    if ended_raw and hi is None:
        print(f"[warn] ended_at 無法解析，忽略：{ended_raw!r}", file=sys.stderr)
    if lo is not None and hi is not None and hi < lo:
        print(f"錯誤：ended_at 早於 started_at（{ended_raw} < {started_raw}）", file=sys.stderr)
        sys.exit(1)
    # 只要有一端就切窗；兩端皆無代表整段 session 全額計入，必須誠實標記。
    window = (lo, hi) if (lo or hi) else None

    run = {
        "slug": args.slug,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config_commit": config_commit(),
        "product": args.product,
        "sessions": session_ids,
        "attribution": "windowed" if window else "session-wide (unpartitioned)",
        "window": {"started_at": started_raw or None, "ended_at": ended_raw or None},
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

    session_files, missing_sessions = find_session_files(session_ids)
    if not session_files:
        # 一份 transcript 都沒找到時絕不寫紀錄：全 0 的 run 與「真的零成本 run」在檔案上
        # 長得一模一樣，retro-digest 會把它當真實資料計入複盤門檻。寧可大聲失敗。
        print("錯誤：指定的 session 一份 transcript 都沒找到，不寫 run 紀錄（避免產生看似成功的全 0 資料）",
              file=sys.stderr)
        print(f"  session id: {', '.join(session_ids)}", file=sys.stderr)
        print(f"  已搜尋根目錄: {', '.join(project_roots()) or '（無）'}", file=sys.stderr)
        print("  排除法：確認 session id 正確；或該 transcript 已過清理週期；"
              "或 profile 路徑有變（見 project_roots()）", file=sys.stderr)
        sys.exit(2)
    if missing_sessions:
        run["missing_sessions"] = missing_sessions
    for f in session_files:
        parse_main_transcript(f, run, window)

    tasks_dirs = list(args.tasks_dir)
    for sid in session_ids:  # 常見兩種歷史位置自動補搜
        tasks_dirs += [os.path.join(CLAUDE, "tasks", sid), os.path.join(CLAUDE, "tasks", f"session-{sid[:8]}")]
    parse_agent_outputs([d for d in tasks_dirs if os.path.isdir(d)], run, window)
    apply_notification_fallback(run)

    if window and run.get("_ts_min") is None:
        print("錯誤：時間窗內找不到任何訊息，不寫 run 紀錄（避免產生看似成功的全 0 資料）", file=sys.stderr)
        print(f"  時間窗: {started_raw or '（無下界）'} ~ {ended_raw or '（無上界）'}", file=sys.stderr)
        print("  排除法：確認 state 檔的 started_at/ended_at 時區與實際作業時間相符", file=sys.stderr)
        sys.exit(3)

    run["duration"] = {"first_ts": run.pop("_ts_min", None), "last_ts": run.pop("_ts_max", None)}
    total = new_usage()
    for bucket in [run["tokens"]["main_loop"], run["tokens"]["sidechain_inline"], *run["tokens_by_agent"].values()]:
        add_usage(total, bucket)
    run["tokens"]["total"] = total
    for k in ("_notif_tokens", "_seen_agent_files", "_agent_id_type"):
        run.pop(k, None)

    # lane 試行欄位：全部從 state 檔帶入；沒有 lane 的 run（舊流程／基線）self_verdict 留空
    lane = (str(st.get("lane") or "")).upper() or None
    run["lane"] = lane
    run["lane_source"] = st.get("lane_source")
    run["lane_changed_from"] = st.get("lane_changed_from")
    run["estimated_minutes"] = st.get("estimated_minutes")
    run["actual_minutes"] = window_minutes(started_raw, ended_raw)
    run["gate_reruns"] = int(st.get("gate_reruns") or 0)
    run["live_regressions"] = int(st.get("live_regressions") or 0)
    run["user_aborted"] = bool(st.get("user_aborted"))
    run["self_verdict"], run["self_verdict_reason"] = self_verdict(run) if lane else (None, None)

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
    if run["lane"]:
        print(f"lane={run['lane']} 預估 {run['estimated_minutes']} 分 / 實際 {run['actual_minutes']} 分 → "
              f"self_verdict={run['self_verdict']}" + (f"（{run['self_verdict_reason']}）" if run['self_verdict_reason'] else ""))
    else:
        print("[info] state 無 lane 欄位：視為舊流程 run，不算 self_verdict（試行規則見 acceptance/LANE_PROTOCOL.md）")
    print(f"agent 派遣: {run['agent_calls'] or '（無）'}")
    if window:
        print(f"分帳: 已切窗 {started_raw or '（無下界）'} ~ {ended_raw or '（無上界）'}")
    else:
        print("[warn] 分帳: 未切窗，本筆為整段 session 全額。同一 session 若做過多個任務，"
              "此數字會重複計給每個任務；請在 state 檔補 started_at / ended_at 後重跑。")
    if run.get("missing_sessions"):
        print(f"[warn] 下列 session 找不到 transcript，本筆為部分資料: {', '.join(run['missing_sessions'])}")
    for st, u in sorted(run["tokens_by_agent"].items(), key=lambda x: -x[1]["output_tokens"]):
        print(f"  {st}: out={u['output_tokens']:,} in={u['input_tokens']:,}")


if __name__ == "__main__":
    main()
