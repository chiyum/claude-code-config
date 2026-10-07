#!/usr/bin/env python3
"""new-completion-report.py — 外部規格模式的交付完成報告產生器

從 state.json、SPEC 與兩份 evidence-index.json 填入模板 ~/.claude/acceptance/COMPLETION_REPORT_TEMPLATE.md，
輸出到 ~/.claude/specs/<product>/<spec_id>/runs/<run_id>/completion-report.md（可用 --out 覆寫）。

用法：
  python3 new-completion-report.py --state ~/.claude/state/<slug>.json \
      [--final] [--local-index p] [--dev-index p] [--out p] [--set key=value ...] [--dry-run]

規則：
  - 只有 --final 且 state.status=done 且本地與 dev 索引每條 A 都 PASS，status 才是 DEV_ACCEPTED（標題「交付完成報告」）
  - 其餘一律 status: BLOCKED 的 partial report，標題不含「完成」
  - 產出前掃描常見機敏字樣（password= / token= / sk- / AKIA / PRIVATE KEY 等），命中即拒絕寫檔
  - 未填的欄位留 <待填>，由主 Claude 以 --set 或事後編輯補上；本報告不是規格來源
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

HOME = os.path.expanduser("~")
TEMPLATE = os.path.join(HOME, ".claude", "acceptance", "COMPLETION_REPORT_TEMPLATE.md")
AC_HEADING_RE = re.compile(r"^### (A[0-9]+)(?:\s|$)")
# 2026-09-27：外部 SPEC 也可能把驗收條目寫成表格列（| AC130 | ... |），一併接受
AC_TABLE_RE = re.compile(r"^\|\s*(AC[0-9]+)\s*\|")
SECRET_PATTERNS = [
    re.compile(r"(?i)\b(password|passwd|pwd)\s*[:=]\s*\S{4,}"),
    re.compile(r"(?i)\b(api[_-]?key|secret|token)\s*[:=]\s*[A-Za-z0-9_\-\.]{12,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bghp_[A-Za-z0-9]{30,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),
]


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_json(path):
    with open(path, "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def spec_ids(spec_path):
    if not spec_path or not os.path.isfile(spec_path):
        return []
    ids = []
    with open(spec_path, "rb") as f:
        for line in f.read().decode("utf-8", errors="replace").split("\n"):
            m = AC_HEADING_RE.match(line) or AC_TABLE_RE.match(line)
            if m and m.group(1) not in ids:
                ids.append(m.group(1))
    return ids


def ac_status(idx, aid):
    if not idx:
        return "—", []
    entry = (idx.get("acceptance") or {}).get(aid) or {}
    return str(entry.get("status", "—")).upper() or "—", list(entry.get("evidence") or [])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--final", action="store_true", help="宣告七道 gate 皆已通過；不符條件時拒絕產出完成報告")
    ap.add_argument("--local-index", default="")
    ap.add_argument("--dev-index", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--template", default=TEMPLATE)
    ap.add_argument("--set", action="append", default=[], metavar="key=value")
    ap.add_argument("--dry-run", action="store_true", help="只印到 stdout，不寫檔")
    args = ap.parse_args()

    state = load_json(os.path.expanduser(args.state))
    if state.get("spec_mode") != "external":
        print("state 非外部規格模式（spec_mode != external），完成報告只適用外部規格 run", file=sys.stderr)
        sys.exit(64)
    for k in ("spec_id", "spec_version", "spec_sha256", "spec_path", "product", "run_id"):
        if not state.get(k):
            print(f"state 缺 {k}", file=sys.stderr)
            sys.exit(64)

    spec_id, run_id, product = state["spec_id"], state["run_id"], state["product"]
    run_dir = os.path.join(HOME, ".claude", "acceptance", spec_id, run_id)
    local_p = os.path.expanduser(args.local_index) if args.local_index else os.path.join(run_dir, "local", "evidence-index.json")
    dev_p = os.path.expanduser(args.dev_index) if args.dev_index else os.path.join(run_dir, "dev", "evidence-index.json")
    local_idx = load_json(local_p) if os.path.isfile(local_p) else None
    dev_idx = load_json(dev_p) if os.path.isfile(dev_p) else None

    # 索引必須綁定同一份 SPEC；不符的索引不採用
    for name, idx in (("local", local_idx), ("dev", dev_idx)):
        if idx and str(idx.get("spec_sha256", "")).lower() != str(state["spec_sha256"]).lower():
            print(f"{name} evidence-index 的 spec_sha256 與 state 不符，拒絕採用", file=sys.stderr)
            sys.exit(1)

    ids = spec_ids(state["spec_path"])
    rows, all_pass = [], bool(ids) and local_idx is not None and dev_idx is not None
    for aid in ids:
        ls, lev = ac_status(local_idx, aid)
        ds, dev_ev = ac_status(dev_idx, aid)
        # N_A（PM 判定本環境不適用，附 reason）不算失敗；其餘非 PASS 皆使 all_pass=False
        if ls not in ("PASS", "N_A") or ds not in ("PASS", "N_A"):
            all_pass = False
        ev = [f"local/{e}" if not e.startswith("local/") else e for e in lev] + [f"dev/{e}" if not e.startswith("dev/") else e for e in dev_ev]
        rows.append(f"| {aid} | {ls} | {ds} | {'<br>'.join(ev) if ev else '—'} |")

    done = state.get("status") == "done"
    if args.final and not (done and all_pass):
        print("拒絕產出完成報告：--final 需 state.status=done 且本地與 dev 索引每條 A 皆 PASS。"
              f"（status={state.get('status')!r}, all_pass={all_pass}）改用不帶 --final 產出 partial report。", file=sys.stderr)
        sys.exit(1)
    final = args.final and done and all_pass
    status = "DEV_ACCEPTED" if final else "BLOCKED"
    title = "交付完成報告（dev 驗收完成）" if final else "交付報告（partial，未完成）"

    commits = state.get("commits") or []
    blocked_lines = []
    if not final:
        blocked_lines.append(f"- state.status：{state.get('status')}")
        if state.get("blocked_reason"):
            blocked_lines.append(f"- 阻擋原因：{state.get('blocked_reason')}")
        if state.get("spec_drift"):
            d = state["spec_drift"]
            blocked_lines.append(f"- SPEC_DRIFT：gate={d.get('gate')} 舊 hash={d.get('expected_sha256')} 新 hash={d.get('actual_sha256')}")
        if state.get("next_action"):
            blocked_lines.append(f"- 停在：{state.get('next_action')}")
        if not all_pass:
            blocked_lines.append("- 驗收未全數 PASS（見上表）")

    values = {
        "status": status,
        "title": title,
        "generated_at": now_iso(),
        "spec_id": spec_id,
        "spec_version": state["spec_version"],
        "spec_sha256": state["spec_sha256"],
        "spec_path": state["spec_path"],
        "product": product,
        "run_id": run_id,
        "target_environment": state.get("target_environment", "<待填>"),
        "repo": state.get("repo") or state.get("worktree") or "<待填>",
        "branch": state.get("branch", "<待填>"),
        "commit": commits[-1] if commits else (dev_idx or local_idx or {}).get("implementation_commit", "<待填>"),
        "acceptance_rows": "\n".join(rows) if rows else "| — | — | — | SPEC 無法解析或無條目 |",
        "reviewer_rounds": str(state.get("reviewer_round", "<待填>")),
        "change_request": "是" if state.get("change_requests") else "否",
        "spec_drift": "是" if state.get("spec_drift") else "否",
        "deploy_backend": (dev_idx or {}).get("deployed_commit") or (dev_idx or {}).get("deployed_version") or "<待填>",
        "blocked_section": "\n".join(blocked_lines) if blocked_lines else "無",
    }
    for kv in args.set:
        k, _, v = kv.partition("=")
        if not k:
            continue
        values[k.strip()] = v

    with open(os.path.expanduser(args.template), "rb") as f:
        tpl = f.read().decode("utf-8")
    text = re.sub(r"\{\{(\w+)\}\}", lambda m: str(values.get(m.group(1), "<待填>")), tpl)

    hits = []
    for i, line in enumerate(text.split("\n"), 1):
        if any(p.search(line) for p in SECRET_PATTERNS):
            hits.append(i)
    if hits:
        print(f"拒絕寫檔：報告第 {', '.join(map(str, hits))} 行疑似含機敏字樣（密碼 / token / 金鑰）。改為引用 SECRETS.local.md 的 reference。", file=sys.stderr)
        sys.exit(2)

    if args.dry_run:
        print(text)
        return
    out = os.path.expanduser(args.out) if args.out else os.path.join(HOME, ".claude", "specs", product, spec_id, "runs", run_id, "completion-report.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        f.write(text.encode("utf-8"))
    print(json.dumps({"ok": True, "status": status, "out": out, "acceptance_count": len(ids), "all_pass": all_pass}, ensure_ascii=False))


if __name__ == "__main__":
    main()
