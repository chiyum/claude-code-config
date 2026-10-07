#!/usr/bin/env python3
"""verify-evidence-external.py — 外部規格模式的證據 gate（verify-evidence.sh --spec 的實作層）

用法（通常由 verify-evidence.sh 轉呼叫，也可直接執行）：
  python3 verify-evidence-external.py --spec <SPEC.md> --evidence-dir <run>/local \
      [--environment local|dev] [--index <evidence-index.json>] \
      [--expected-sha256 <state hash>] [--run-id RUN-...]

檢查（任一項失敗 → exit 1，不得放行）：
  1. SPEC 每個 ### A<n> 至少一個非空證據檔（檔名含 A<n>-）
     表格式 AC（見下方「AC 來源」）改為：檔名含正規化 AC 記號，或 index 該條 evidence 引用的檔，至少一個非空
     （index 狀態 N_A 的表格式條目不要求檔案，理由由第 8 項的 reason 把關）
  2. evidence-index.json 的 spec_id / spec_version / spec_sha256 與 SPEC + manifest（及 state hash）一致
  3. index 內每個證據路徑都落在本 run 的證據目錄內（不得拿其他 run / 版本的檔充數）
  4. 證據檔實際存在且非空
  5. SPEC 的「所需證據」同時要求 API 與 UI 時，兩類檔案都要有
  6. index.environment 必須等於本次目錄的環境（local 不得冒充 dev）
  7. dev 證據必須記錄 implementation_commit 與 deployed_version / deployed_commit
  8. 每條 A 在 index 內狀態為 PASS 才算通過；PASS 必附 expected / observed / evidence

AC 來源（2026-09-29 起支援兩種，擇一，不混用）：
  A. 標題式：「### A<n> ...」。SPEC 只要有任何一條，就只用這種，行為與舊版完全相同（原樣比對 A<n>、
     檔名比對只看證據目錄第一層、「所需證據」列判斷雙軌）。
  B. 表格式：SPEC 沒有任何標題式條目時，改讀 Markdown 表格列——首欄是 AC 編號的列即一條驗收條件
     （例：| AC01 | FR01 | 操作 | 通過條件 |）。表頭列（首欄只有「AC」）與分隔列自動略過。
     AC 編號正規化：去掉首欄的 ** / ` / 空白 → 不分大小寫比對 AC[-_ ]?<數字>
       → 正規化鍵＝「AC」＋去前導零的數字（AC01、ac-1、AC001 都是 AC1）。
     SPEC 條目與 index.acceptance 的鍵都先正規化再對應；輸出沿用 SPEC 原字樣（AC01）。
     證據檔名比對：證據目錄（含子目錄）內檔名含 AC[-_]?0*<數字> 且前後不接英數字者（AC1 不會誤配 AC10 / AC12）。
     同一編號重複出現只取第一列並警告。表格列沒有「所需證據」欄，不做雙軌檢查（雙軌由 SPEC 明文與 PM 判定把關）。

不做：截圖內容真偽（主 Claude 抽驗）、反方 PM（另開 agent）。
"""
import argparse
import hashlib
import json
import os
import re
import sys

AC_HEADING_RE = re.compile(r"^### (A[0-9]+)(?:\s|$)")
# 表格式 AC：首欄 AC 編號（大小寫、連字號／底線／空白、前導零皆容忍）
AC_TABLE_ID_RE = re.compile(r"^AC[-_ ]?([0-9]+)$", re.IGNORECASE)
API_HINTS = ("api", "curl", "http", ".json", ".txt", ".log", "response")
UI_HINTS = (".png", ".jpg", ".jpeg", ".webp", "ui", "screenshot", "screen", "畫面", "截圖")
INDEX_REQUIRED = ("run_id", "spec_id", "spec_version", "spec_sha256", "implementation_commit", "environment", "acceptance")


def fail(msgs, code):
    for m in msgs:
        print(f"❌ {m}")
    print(f"\nRESULT: FAIL {code}")
    print("❌ 證據 gate 未通過：不得放行。退回 QA/PM 補做該條驗證並落地證據，不要只補檔名或改索引。")
    sys.exit(1)


def parse_spec(spec_path):
    with open(spec_path, "rb") as f:
        raw = f.read()
    sha = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8")
    ids, blocks, cur = [], {}, None
    for line in text.split("\n"):
        m = AC_HEADING_RE.match(line)
        if m:
            cur = m.group(1)
            ids.append(cur)
            blocks[cur] = []
            continue
        if re.match(r"^##\s", line):
            cur = None
        if cur:
            blocks[cur].append(line)
    if ids:
        # 標題式：與舊版完全相同
        return sha, ids, {k: "\n".join(v) for k, v in blocks.items()}, "heading"
    ids, blocks = parse_table_acs(text)
    return sha, ids, blocks, "table"


def normalize_ac_id(raw):
    """表格式 AC 編號正規化：'**AC01**' / 'ac-1' / 'AC001' → 'AC1'；不是 AC 編號回 None。"""
    t = raw.strip().strip("*`").strip()
    m = AC_TABLE_ID_RE.match(t)
    return f"AC{int(m.group(1))}" if m else None


def parse_table_acs(text):
    """讀 Markdown 表格列：首欄是 AC 編號的列視為一條驗收條件。回傳（SPEC 原字樣清單, {原字樣: 該列文字}）。"""
    ids, blocks, seen = [], {}, {}
    for line in text.split("\n"):
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = s.strip("|").split("|")
        if not cells:
            continue
        raw = cells[0].strip().strip("*`").strip()
        norm = normalize_ac_id(raw)
        if not norm:
            continue
        if norm in seen:
            print(f"[warn] SPEC 表格 AC 編號重複：{raw}（與 {seen[norm]} 同為 {norm}），只取第一列")
            continue
        seen[norm] = raw
        ids.append(raw)
        blocks[raw] = s
    return ids, blocks


def needs_dual_track(block):
    """所需證據列同時提到 API 與 UI/截圖 → 雙軌。"""
    for line in block.split("\n"):
        if "所需證據" in line:
            low = line.lower()
            has_api = "api" in low or "curl" in low
            has_ui = any(k in low for k in ("ui", "截圖", "畫面", "screenshot"))
            return has_api and has_ui
    return False


def files_for(aid, evidence_dir):
    out = []
    for name in sorted(os.listdir(evidence_dir)):
        p = os.path.join(evidence_dir, name)
        if os.path.isfile(p) and f"{aid}-" in name and name != "evidence-index.json":
            out.append(p)
    return out


def table_files_for(aid, evidence_dir):
    """表格式 AC 的檔名比對：遞迴、正規化，AC1 不誤配 AC10。"""
    n = int(AC_TABLE_ID_RE.match(normalize_ac_id(aid)).group(1))
    pat = re.compile(rf"(?<![A-Za-z0-9])AC[-_]?0*{n}(?![0-9])", re.IGNORECASE)
    out = []
    for root, _dirs, names in os.walk(evidence_dir):
        for name in sorted(names):
            if name != "evidence-index.json" and pat.search(name):
                out.append(os.path.join(root, name))
    return sorted(out)


def resolve_evidence(rel, run_root, evidence_dir):
    """index 的 evidence 相對路徑：先以 run 根目錄、再以證據目錄解析（與索引層同規則）。"""
    cand = [os.path.realpath(os.path.join(run_root, rel)), os.path.realpath(os.path.join(evidence_dir, rel))]
    return next((c for c in cand if os.path.isfile(c)), None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--evidence-dir", required=True)
    ap.add_argument("--environment", default="", help="local / dev；省略時取證據目錄名")
    ap.add_argument("--index", default="", help="evidence-index.json 路徑；省略時取 <evidence-dir>/evidence-index.json")
    ap.add_argument("--expected-sha256", default="")
    ap.add_argument("--run-id", default="")
    args = ap.parse_args()

    spec_path = os.path.realpath(os.path.expanduser(args.spec))
    evidence_dir = os.path.realpath(os.path.expanduser(args.evidence_dir))
    errors = []

    if not os.path.isfile(spec_path):
        fail([f"找不到 SPEC：{spec_path}"], "SPEC_NOT_FOUND")
    if not os.path.isdir(evidence_dir):
        fail([f"證據目錄不存在：{evidence_dir}", "QA/PM 必須把截圖 / curl 輸出以「<qa|pm>-A<n>-<說明>」命名存入該目錄"], "EVIDENCE_DIR_MISSING")

    environment = (args.environment or os.path.basename(evidence_dir)).strip().lower()
    spec_sha, ids, blocks, ac_mode = parse_spec(spec_path)
    if not ids:
        fail(["SPEC 內找不到任何「### A<n>」驗收條件，也沒有首欄為 AC 編號（如 | AC01 |）的表格列"], "SPEC_INVALID")
    if ac_mode == "table":
        print(f"[info] AC 來源：表格列（{len(ids)} 條，{ids[0]}…{ids[-1]}）；比對鍵正規化為 AC<去前導零數字>")

    manifest_path = os.path.join(os.path.dirname(spec_path), "manifest.json")
    manifest = {}
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, "rb") as f:
                manifest = json.loads(f.read().decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            errors.append(f"manifest.json 無法解析：{e}")
    else:
        errors.append(f"SPEC 同目錄缺 manifest.json：{manifest_path}")

    if manifest and str(manifest.get("spec_sha256", "")).lower() != spec_sha:
        errors.append(f"SPEC 實際 hash {spec_sha[:12]}… 與 manifest 記錄 {str(manifest.get('spec_sha256', ''))[:12]}… 不符（SPEC_DRIFT）")
    if args.expected_sha256 and args.expected_sha256.strip().lower() != spec_sha:
        errors.append(f"SPEC 實際 hash {spec_sha[:12]}… 與 state 綁定 {args.expected_sha256.strip()[:12]}… 不符（SPEC_DRIFT）")
    if errors:
        fail(errors, "SPEC_DRIFT")

    index_path = os.path.realpath(os.path.expanduser(args.index)) if args.index else os.path.join(evidence_dir, "evidence-index.json")
    run_root = os.path.dirname(evidence_dir)

    # 表格式：檔案層需要 index 的狀態與引用清單，先寬鬆預讀（嚴格檢查仍在索引層）
    pre_acc = {}
    if ac_mode == "table" and os.path.isfile(index_path):
        try:
            with open(index_path, "rb") as f:
                _pre = json.loads(f.read().decode("utf-8"))
            if isinstance(_pre, dict) and isinstance(_pre.get("acceptance"), dict):
                pre_acc = {normalize_ac_id(k) or k: v for k, v in _pre["acceptance"].items()}
        except (ValueError, UnicodeDecodeError):
            pre_acc = {}

    # 1. 檔案層
    print(f"=== 檔案層：{evidence_dir}（{environment}）===")
    for aid in ids:
        if ac_mode == "table":
            entry = pre_acc.get(normalize_ac_id(aid))
            entry = entry if isinstance(entry, dict) else {}
            if str(entry.get("status", "")).strip().upper() == "N_A":
                print(f"➖ {aid}: index 標 N_A，不要求本環境證據檔（reason 於索引層檢查）")
                continue
            matches = set(table_files_for(aid, evidence_dir))
            ev = entry.get("evidence")
            for rel in (ev if isinstance(ev, list) else []):
                found = resolve_evidence(str(rel), run_root, evidence_dir)
                if found and (found + os.sep).startswith(evidence_dir + os.sep):
                    matches.add(found)
            matches = sorted(matches)
            nonempty = [p for p in matches if os.path.getsize(p) > 0]
            empty = [p for p in matches if os.path.getsize(p) == 0]
            if not nonempty:
                errors.append(f"條目 {aid} 沒有任何非空證據檔（需檔名含 {aid} 記號，或 index 該條 evidence 引用 {evidence_dir} 內的檔）")
                continue
            for p in empty:
                errors.append(f"條目 {aid} 的證據檔為空：{os.path.relpath(p, evidence_dir)}")
            print(f"✅ {aid}: {len(nonempty)} 個證據檔")
            for p in nonempty:
                print(f"     - {os.path.relpath(p, evidence_dir)}")
            continue
        matches = files_for(aid, evidence_dir)
        nonempty = [p for p in matches if os.path.getsize(p) > 0]
        empty = [p for p in matches if os.path.getsize(p) == 0]
        if not nonempty:
            errors.append(f"條目 {aid} 沒有任何非空證據檔（需至少一個 *{aid}-* 檔案於 {evidence_dir}）")
            continue
        for p in empty:
            errors.append(f"條目 {aid} 的證據檔為空：{os.path.basename(p)}")
        print(f"✅ {aid}: {len(nonempty)} 個證據檔")
        for p in nonempty:
            print(f"     - {os.path.basename(p)}")
        if needs_dual_track(blocks.get(aid, "")):
            names = [os.path.basename(p).lower() for p in nonempty]
            has_api = any(any(h in n for h in API_HINTS) for n in names)
            has_ui = any(any(h in n for h in UI_HINTS) for n in names)
            if not (has_api and has_ui):
                errors.append(f"條目 {aid} 要求 API 與 UI 雙軌證據，目前 API={'有' if has_api else '缺'} / UI={'有' if has_ui else '缺'}")

    # 2. 索引層
    print(f"=== 索引層：{index_path} ===")
    if not os.path.isfile(index_path):
        errors.append(f"缺 evidence-index.json：{index_path}")
        fail(errors, "EVIDENCE_INDEX_MISSING")
    try:
        with open(index_path, "rb") as f:
            idx = json.loads(f.read().decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        fail(errors + [f"evidence-index.json 無法解析：{e}"], "EVIDENCE_INDEX_INVALID")
    if not isinstance(idx, dict):
        fail(errors + ["evidence-index.json 頂層必須是物件"], "EVIDENCE_INDEX_INVALID")
    missing = [k for k in INDEX_REQUIRED if k not in idx]
    if missing:
        fail(errors + [f"evidence-index.json 缺欄位：{', '.join(missing)}"], "EVIDENCE_INDEX_INVALID")

    if manifest and str(idx.get("spec_id", "")).strip() != str(manifest.get("spec_id", "")).strip():
        errors.append(f"index.spec_id={idx.get('spec_id')!r} 與 manifest {manifest.get('spec_id')!r} 不符")
    if manifest and str(idx.get("spec_version", "")).strip() != str(manifest.get("version", "")).strip():
        errors.append(f"index.spec_version={idx.get('spec_version')!r} 與 manifest {manifest.get('version')!r} 不符")
    if str(idx.get("spec_sha256", "")).strip().lower() != spec_sha:
        errors.append(f"index.spec_sha256 {str(idx.get('spec_sha256', ''))[:12]}… 與目前 SPEC {spec_sha[:12]}… 不符（不得拿其他版本 / 其他 run 的證據充數）")
    if args.run_id and str(idx.get("run_id", "")).strip() != args.run_id.strip():
        errors.append(f"index.run_id={idx.get('run_id')!r} 與本 run {args.run_id!r} 不符")
    if str(idx.get("environment", "")).strip().lower() != environment:
        errors.append(f"index.environment={idx.get('environment')!r} 與證據目錄環境 {environment!r} 不符（本地證據不得冒充 dev）")
    if not str(idx.get("implementation_commit", "")).strip():
        errors.append("index.implementation_commit 為空")
    if environment == "dev":
        if not (str(idx.get("deployed_version", "")).strip() or str(idx.get("deployed_commit", "")).strip()):
            errors.append("dev 證據必須記錄 deployed_version 或 deployed_commit（實際上線版本）")

    acc = idx.get("acceptance")
    if not isinstance(acc, dict):
        fail(errors + ["index.acceptance 必須是物件"], "EVIDENCE_INDEX_INVALID")

    if ac_mode == "table":
        # 表格式：index 鍵同樣正規化後對應（AC01 / AC1 / ac-001 視為同一條）
        acc_by_norm = {}
        for k, v in acc.items():
            nk = normalize_ac_id(k) or k
            if nk in acc_by_norm:
                errors.append(f"index.acceptance 有正規化後重複的鍵：{k}（{nk}）")
            acc_by_norm.setdefault(nk, v)
    for aid in ids:
        entry = acc_by_norm.get(normalize_ac_id(aid)) if ac_mode == "table" else acc.get(aid)
        if not isinstance(entry, dict):
            errors.append(f"index 缺條目 {aid}")
            continue
        status = str(entry.get("status", "")).strip().upper()
        if status not in ("PASS", "FAIL", "BLOCKED", "N_A"):
            errors.append(f"index {aid}.status={entry.get('status')!r} 不是 PASS / FAIL / BLOCKED / N_A")
            continue
        # 2026-09-27：N_A＝PM 判定「本環境不適用」（例如部署後才有判準的條目在 local、無線上專屬判準的條目在 dev）
        # 必附 reason，不計為失敗；KNOWN_LIMIT／PENDING／NOT_RUN 一律不接受（要嘛 PASS，要嘛如實 FAIL／BLOCKED）
        if status == "N_A":
            if not str(entry.get("reason", "")).strip():
                errors.append(f"index {aid} 狀態 N_A 但缺 reason（必須寫明為何本環境不適用）")
            continue
        if status != "PASS":
            errors.append(f"index {aid} 狀態為 {status}（{entry.get('observed') or entry.get('reason') or '未說明'}），未通過")
            continue
        if not str(entry.get("expected", "")).strip() or not str(entry.get("observed", "")).strip():
            errors.append(f"index {aid} PASS 但缺 expected / observed")
        if "spec" not in str(entry.get("expected_source", "")).lower():
            errors.append(f"index {aid}.expected_source={entry.get('expected_source')!r} 未指向 SPEC（期望值必須來自凍結 SPEC，不得取自受測物）")
        ev = entry.get("evidence")
        if not isinstance(ev, list) or not ev:
            errors.append(f"index {aid} PASS 但 evidence 清單為空")
            continue
        for rel in ev:
            cand = [os.path.realpath(os.path.join(run_root, rel)), os.path.realpath(os.path.join(evidence_dir, rel))]
            found = next((c for c in cand if os.path.isfile(c)), None)
            if found is None:
                errors.append(f"index {aid} 引用的證據不存在：{rel}")
                continue
            if not (found + os.sep).startswith(evidence_dir + os.sep) and found != evidence_dir:
                errors.append(f"index {aid} 引用的證據不在本 run 的 {environment} 證據目錄內：{rel}")
            elif os.path.getsize(found) == 0:
                errors.append(f"index {aid} 引用的證據為空檔：{rel}")
    if ac_mode == "table":
        spec_norm = {normalize_ac_id(a) for a in ids}
        extra = sorted(k for k in acc if (normalize_ac_id(k) or k) not in spec_norm)
    else:
        extra = sorted(set(acc) - set(ids))
    if extra:
        print(f"[warn] index 含 SPEC 沒有的條目：{', '.join(extra)}（忽略，不得當作驗收依據）")

    if errors:
        fail(errors, "EVIDENCE_INCOMPLETE")

    print(f"\nRESULT: PASS environment={environment} spec_sha256={spec_sha} acceptance={','.join(ids)}")
    print("✅ 證據 gate 通過。提醒主 Claude：放行前仍須親自抽驗 1-2 張關鍵截圖；大改動另開反方 PM。")
    sys.exit(0)


if __name__ == "__main__":
    main()
