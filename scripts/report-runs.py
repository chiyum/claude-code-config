#!/usr/bin/env python3
"""report-runs.py — run 遙測對照報表

讀 ~/.claude/run-metrics/runs/*.json，輸出兩張 markdown 表：
1. 逐筆 run 對照（新→舊）
2. 按 config commit 分組的均值（看制度改動前後的趨勢）

用法：python3 report-runs.py [--last N] [--md 輸出檔]
"""
import argparse, glob, json, os, sys

RUNS_DIR = os.path.join(os.path.expanduser("~"), ".claude", "run-metrics", "runs")


def fmt(n):
    return f"{n/1000:.0f}k" if n >= 10000 else str(n)


def agent_summary(run):
    calls = run.get("agent_calls") or {}
    return " ".join(f"{k}×{v}" for k, v in sorted(calls.items())) or "—"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--last", type=int, default=20)
    ap.add_argument("--md", default="")
    args = ap.parse_args()

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
             "| 日期 | 任務 | config | out tokens | cache read | agent 派遣 | reviewer 回合 | 結果 | verdict |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in runs:
        t = (r.get("tokens") or {}).get("total") or {}
        lines.append("| {d} | {s} | `{c}` | {o} | {cr} | {a} | {rv} | {oc} | {v} |".format(
            d=r.get("date", "?"), s=r.get("slug", "?"), c=r.get("config_commit", "?"),
            o=fmt(t.get("output_tokens", 0)), cr=fmt(t.get("cache_read_input_tokens", 0)),
            a=agent_summary(r), rv=(r.get("agent_calls") or {}).get("reviewer", 0),
            oc=r.get("outcome", "?"),
            v=(r.get("verdict") or "未評") + (f"（{r['verdict_comment']}）" if r.get("verdict_comment") else "")))

    groups = {}
    for r in runs:
        groups.setdefault(r.get("config_commit", "?"), []).append(r)
    lines += ["", "## 按 config 版本分組（制度改動前後趨勢）", "",
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
