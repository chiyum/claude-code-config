#!/usr/bin/env python3
"""report-runs.py — run 遙測對照報表

讀 ~/.claude/run-metrics/runs/*.json，輸出兩張 markdown 表：
1. 逐筆 run 對照（新→舊）
2. 按 config commit 分組的均值（看制度改動前後的趨勢）

用法：python3 report-runs.py [--last N] [--md 輸出檔]
      python3 report-runs.py --pilot      # lane 試行 run 對照 9 月基線（acceptance/LANE_PROTOCOL.md §6）
"""
import argparse, glob, json, os, sys

RUNS_DIR = os.path.join(os.path.expanduser("~"), ".claude", "run-metrics", "runs")
BASELINE = os.path.join(os.path.expanduser("~"), ".claude", "run-metrics", "baseline-202609.json")


def fmt(n):
    return f"{n/1000:.0f}k" if n >= 10000 else str(n)


def agent_summary(run):
    calls = run.get("agent_calls") or {}
    return " ".join(f"{k}×{v}" for k, v in sorted(calls.items())) or "—"



def median(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def fmt_num(v):
    if v is None:
        return "—"
    return fmt(int(v)) if v >= 10000 else (f"{v:.0f}" if float(v).is_integer() else f"{v:.1f}")


def pilot_report():
    """lane 試行 run 對照凍結基線；沒有 lane 的 run 一律不算試行"""
    try:
        base = json.load(open(BASELINE))
    except Exception as e:
        print(f"讀不到基線 {BASELINE}：{e}")
        return
    runs = []
    for p in sorted(glob.glob(os.path.join(RUNS_DIR, "*.json"))):
        try:
            r = json.load(open(p))
        except Exception:
            continue
        if r.get("lane"):
            runs.append(r)

    def stats(rs):
        calls = [r.get("agent_calls") or {} for r in rs]
        return {
            "minutes": median([r.get("actual_minutes") for r in rs]),
            "reviewer_calls": median([c.get("reviewer", 0) for c in calls]),
            "qa_pm_calls": median([c.get("qa", 0) + c.get("pm", 0) for c in calls]),
            "agent_calls": median([sum(c.values()) for c in calls]),
            "out_tokens": median([((r.get("tokens") or {}).get("total") or {}).get("output_tokens", 0) for r in rs]),
            "bad_rate": (sum(1 for r in rs if r.get("self_verdict") == "bad") / len(rs)) if rs else None,
            "live_regressions": sum(int(r.get("live_regressions") or 0) for r in rs) if rs else None,
        }

    bm = base.get("median", {})
    cols = [("基線 9 月", {**bm, "bad_rate": None, "live_regressions": None}, base.get("runs", 0))]
    cols.append(("試行全部", stats(runs), len(runs)))
    for lane in ("S", "M", "L"):
        rs = [r for r in runs if r.get("lane") == lane]
        cols.append((f"lane {lane}", stats(rs), len(rs)))

    print("## lane 試行對照（中位數；決策點：10 筆 lane run 或 2026-10-13）\n")
    print("| 指標 | " + " | ".join(f"{n}（{c} 筆）" for n, _, c in cols) + " |")
    print("|---|" + "---|" * len(cols))
    labels = [("minutes", "時長（分）"), ("reviewer_calls", "reviewer 派遣"), ("qa_pm_calls", "qa+pm 派遣"),
              ("agent_calls", "agent 派遣"), ("out_tokens", "out tokens"), ("bad_rate", "self_verdict bad 率"),
              ("live_regressions", "線上回歸總數")]
    for key, label in labels:
        cells = []
        for _, s, _ in cols:
            v = s.get(key)
            cells.append(f"{v:.0%}" if key == "bad_rate" and v is not None else fmt_num(v))
        print(f"| {label} | " + " | ".join(cells) + " |")

    print("\n## 試行 run 逐筆\n")
    if not runs:
        print("尚無帶 lane 欄位的 run。")
        return
    print("| 日期 | 任務 | lane | 預估/實際（分） | reviewer | qa+pm | gate 重跑 | 線上回歸 | self | 使用者 |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in runs:
        c = r.get("agent_calls") or {}
        print(f"| {r.get('date','?')} | {r.get('slug','?')} | {r.get('lane')}"
              f"{'←'+r['lane_changed_from'] if r.get('lane_changed_from') else ''} | "
              f"{r.get('estimated_minutes') or '—'}/{fmt_num(r.get('actual_minutes'))} | {c.get('reviewer',0)} | "
              f"{c.get('qa',0)+c.get('pm',0)} | {r.get('gate_reruns',0)} | {r.get('live_regressions',0)} | "
              f"{r.get('self_verdict') or '—'}{'（'+r['self_verdict_reason']+'）' if r.get('self_verdict_reason') else ''} | "
              f"{r.get('verdict') or '未評'} |")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--last", type=int, default=20)
    ap.add_argument("--md", default="")
    ap.add_argument("--pilot", action="store_true", help="lane 試行 run 對照 9 月基線")
    args = ap.parse_args()
    if args.pilot:
        pilot_report()
        return

    runs = []
    for p in sorted(glob.glob(os.path.join(RUNS_DIR, "*.json")), reverse=True)[: args.last]:
        try:
            runs.append(json.load(open(p)))
        except Exception as e:
            print(f"[warn] 讀取失敗 {p}: {e}", file=sys.stderr)
    if not runs:
        print("尚無 run 記錄")
        return

    lines = ["## 逐筆 run 對照（新 → 舊）", "",
             "| 日期 | 任務 | lane | 時長(分) | config | 分帳 | out tokens | cache read | agent 派遣 | reviewer 回合 | 結果 | self | verdict |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in runs:
        t = (r.get("tokens") or {}).get("total") or {}
        # 未切窗的 run：整段 session 全額，同 session 多任務會拿到同一組數字，標出來避免被當成可比數據
        windowed = r.get("attribution") == "windowed"
        att = "切窗" if windowed else ("⚠未分帳×%d" % (len(r["shared_session_with"]) + 1)
                                       if r.get("shared_session_with") else "⚠未分帳")
        lines.append("| {d} | {s} | {ln} | {mn} | `{c}` | {att} | {o} | {cr} | {a} | {rv} | {oc} | {sv} | {v} |".format(
            d=r.get("date", "?"), s=r.get("slug", "?"), ln=r.get("lane") or "—", mn=fmt_num(r.get("actual_minutes")),
            sv=r.get("self_verdict") or "—",
            c=r.get("config_commit", "?"), att=att,
            o=fmt(t.get("output_tokens", 0)), cr=fmt(t.get("cache_read_input_tokens", 0)),
            a=agent_summary(r), rv=(r.get("agent_calls") or {}).get("reviewer", 0),
            oc=r.get("outcome", "?"),
            v=(r.get("verdict") or "未評") + (f"（{r['verdict_comment']}）" if r.get("verdict_comment") else "")))

    groups = {}
    for r in runs:
        groups.setdefault(r.get("config_commit", "?"), []).append(r)
    lines += ["", "## 按 config 版本分組（制度改動前後趨勢）", "",
              "> 均值含未切窗的 run（2026-08-22 前全數如此），與切窗後資料混算會偏高，趨勢僅供參考",
              "",
              "| config | runs | 平均 out tokens | 平均 reviewer 回合 | verdict 分佈 |",
              "|---|---|---|---|---|"]
    for c, rs in groups.items():
        outs = [((r.get("tokens") or {}).get("total") or {}).get("output_tokens", 0) for r in rs]
        revs = [(r.get("agent_calls") or {}).get("reviewer", 0) for r in rs]
        vd = {}
        for r in rs:
            vd[r.get("verdict") or "未評"] = vd.get(r.get("verdict") or "未評", 0) + 1
        lines.append(f"| `{c}` | {len(rs)} | {fmt(sum(outs)//max(len(outs),1))} | "
                     f"{sum(revs)/max(len(revs),1):.1f} | {' '.join(f'{k}×{v}' for k, v in vd.items())} |")

    out = "\n".join(lines)
    print(out)
    if args.md:
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(out + "\n")
        print(f"\n（已寫入 {args.md}）", file=sys.stderr)


if __name__ == "__main__":
    main()
