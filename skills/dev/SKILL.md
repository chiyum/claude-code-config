---
name: dev
description: 一鍵自主開發管線。對使用者需求自主跑完五步驟（PM 凍結清單+憲章 → architect → pre-review → reviewer → 本地 QA/PM 證據驗收 → push → dev 驗證 → 一次性回報），全程寫檢查點、依憲章自答問題、大任務自動切批。用法：/dev <需求文字>（凍結前停一次確認）、/dev auto <需求文字>（零停頓全自主）、/dev 繼續 <任務slug>（接續中斷任務或下一批）、/dev [auto] --spec <SPEC.md 絕對路徑>（外部凍結規格模式：不產清單，驗 hash 後依 SPEC 開發）。
user-invocable: true
---

# /dev — 自主開發管線

本 skill 是 `~/.claude/CLAUDE.md` 五步驟流程的「一鍵入口」。所有既有規則（編排協定、gate、3 回合上限、證據落地、知識庫 playbook、ADR、規格同步）照常適用，本檔只定義入口行為與自主模式差異點。

## 引數解析

- 含 `--spec <SPEC.md 絕對路徑>` → **外部凍結規格模式**（可與 `auto` 疊加：`/dev auto --spec <路徑>`）。步驟 0 改走下方「外部凍結規格模式」節，步驟 1～5 不變。沒有 `--spec` 一律走原生模式，不得主動把需求轉成外部 SPEC。
- 第一個 token（可在 `auto` 之後）為 `S`／`M`／`L` → **指定 lane**（如 `/dev auto M <需求>`），state 寫 `lane_source: user`；沒有就在開跑前置第 1 項問一次
- 以 `繼續 ` 開頭 → **接續模式**：Read `~/.claude/state/<slug>.json`、`<slug>-handoff.md`、`<slug>-questions.md`、對應 acceptance 清單，把 state 檔的 `session_id` 更新為本 session 的 UUID（`$CLAUDE_CODE_SESSION_ID`）、`config_dir` 更新為 `$CLAUDE_CONFIG_DIR`、`status` 設 `running`（`started_at` **維持第一批的值不覆寫**），從 `next_action` / 下一批繼續。
- 以 `auto ` 開頭 → **全自主模式**：步驟 0 憑證（清單+憲章）產出並寫檔後**不停等確認**直接開跑，最後一次性回報。
- 其他 → **標準模式**：步驟 0 產出清單+憲章後呈現一次給使用者，確認即凍結，之後零中斷直到最終回報。

## 開跑時提示使用者疊加 /goal（雙層保險）

任務開跑的第一則回應中，提示使用者（僅提示一次，不強制）：
> 建議同時下 `/goal ~/.claude/state/<slug>.json 的 status 變成 done、reported 或 awaiting_user`
> session 活著時 /goal 秒級續跑（turn 意外停下立刻拉起），session 死掉才輪到看門狗 10 分鐘級復活。

/goal 是使用者層指令，主 Claude 不能代下，只能提示。

## 開跑前置（四件事，依序）

1. **定級**（試行中，全文見 `~/.claude/acceptance/LANE_PROTOCOL.md`）：引數沒指定 lane 就用 AskUserQuestion 一題三選項確認（auto 模式也問，這是唯一停點；使用者說「直接改」且一句話能描述 diff → 直接 S 不問）。同時估 `estimated_minutes`（改完到上線）。**S 跳過第 4 項的清單與憲章**，直接 architect → build → push → 部署後點一次
2. 產品上下文偵測與載入（照 CLAUDE.md session 啟動規則）
3. 任務 slug = `<YYYYMMDD>-<簡述>`；建檢查點檔 `~/.claude/state/<slug>.json`（格式見 `~/.claude/state/README.md`）
   - `session_id` 用 `echo "$CLAUDE_CODE_SESSION_ID"` 取（**舊的 `ls -t ~/.claude/projects/…` 寫法已失準**，profile 搬遷後會取到陳年 session，遙測就記到別的任務頭上）
   - 同時寫 `started_at`（`date -Iseconds`）——這是遙測分帳切窗的起點，缺了整段 session 的量會全額計給本任務
   - 同時寫 `config_dir`（`echo "$CLAUDE_CONFIG_DIR"`）——看門狗復活時要用同一個 profile，缺了會找不到 session
   - 同時寫 `lane`、`lane_source`、`estimated_minutes`；之後 `gate_reruns`／`live_regressions`／`user_aborted` 發生時即時 +1 或標 true（收尾 `collect-run-metrics.py` 據此算 self_verdict）
4. 步驟 0（M／L）：M／L 先派 Explore 盤點現況（≤ 5 分鐘）；主 Claude 寫「理解回述」四件事＋「現況是什麼」（我理解你要的／我假設的／我不會做的／一個具體例子；≤10 行白話）放 acceptance 檔頂部；PM 產三段式驗收清單；主 Claude 補**任務憲章**寫入同一份 acceptance 檔（格式見 `~/.claude/acceptance/README.md`）。標準模式把回述與清單一起呈現給使用者確認；auto 模式不停等但照樣寫、最終回報照樣列

## 外部凍結規格模式（`--spec`；完整程序見 `~/.claude/acceptance/EXTERNAL_SPEC_PROTOCOL.md`）

規格由外部治理者在 `~/.claude/specs/<product>/<spec_id>/v<ver>/SPEC.md` 凍結，Claude 只驗、只做、只交報告。取代原生步驟 0 的部分：

1. `python3 ~/.claude/scripts/verify-external-spec.py --spec <路徑>` → 非 0 依錯誤碼停止：`SPEC_NOT_FROZEN`（DRAFT，只能 `/spec-check`）、`SPEC_SUPERSEDED`（不建 run、不猜新版路徑）、`SPEC_INVALID` / `SPEC_DRIFT`（不自動修正）、`PRODUCT_MISMATCH`、`ENVIRONMENT_REQUIRES_CONFIRMATION`（prod，必問）
2. 載入產品上下文後以 `--expected-product` 重跑確認一致
3. 產生 `run_id`（`RUN-<YYYYMMDD>-<NNN>`），用驗證器輸出 jq 合成 state（欄位 `spec_mode: external` + spec_id / spec_version / spec_path / spec_sha256 / manifest_path / run_id / target_environment / evidence_root；範例指令在協定第 4 節），建 `~/.claude/acceptance/<spec_id>/<run_id>/{local,dev}/`
4. PM 只做 **acceptance auditor**（可測試性 / 矛盾稽核），不得重寫 A1～An、不再要使用者確認 FROZEN 規格；標準模式在此呈現稽核結論停一次，auto 直接進 architect
5. 每個 gate 轉換前先 `bash ~/.claude/scripts/spec-gate.sh ~/.claude/state/<slug>.json "<gate>"`；exit 7 = `SPEC_DRIFT`，state 已標 `blocked_spec_drift`，原樣回報並停止，不得接受新版
6. 交棒每個 agent 都附協定第 8 節的共同抬頭（spec ID / version / hash / 路徑 / product / environment / run ID / 角色邊界）；architect commit 加 `Spec-ID / Spec-Version / Spec-SHA256 / Acceptance` trailer
7. 證據 gate 改用 `verify-evidence.sh --spec <SPEC.md> --evidence-dir <run>/local|dev --expected-sha256 <state hash> --run-id <run_id>`，每個環境一份 `evidence-index.json`
8. 任何 agent 要動規格 → 主 Claude 輸出 `SPEC_CHANGE_REQUIRED`（協定第 6 節），state 標 `awaiting_user` 停止；不得自行移動球門
9. 收尾：`new-completion-report.py --state <state> --final` 產出 `~/.claude/specs/<product>/<spec_id>/runs/<run_id>/completion-report.md`；阻擋時不帶 `--final` 出 `status: BLOCKED` partial report

## 自主模式差異點（凌駕日常「先問」條款）

1. **三方案不停等**：architect 產出三方案後，主 Claude 直接採納推薦方案，理由記入最終回報的「我幫你做的決定」清單；屬 ADR 門檻的照常寫 ADR。
2. **提問三分流**：任何 agent（含主 Claude 自己）想提問時，先對照憲章——
   - 憲章預授權決策表能自答 → 自答並記入決策紀錄
   - 命中必問白名單（不可逆刪資料 / 花錢 / 資安 / 碰 prod / 需求自相矛盾）→ 才准中斷（state 標 `awaiting_user`）
   - 其餘 → 寫進 `~/.claude/state/<slug>-questions.md`，不中斷，最終回報一併呈上。**questions.md 只收需要使用者決定的項目**，每條四行（問題／我暫採／影響／選項）；憲章內自答的決策、reviewer 回合判定、裁決理由一律寫 handoff.md，不得把 questions.md 寫成日誌
3. **3 回合超限不停**：architect↔reviewer 超過 3 回合時，該項凍結記入 blockers、繼續其餘工作、最終回報一併列出（不中途打斷使用者）。
4. **push 帳號**：讀產品配置「git 帳號歸屬」欄；缺欄才問一次，問完立刻寫回產品配置。

## 檢查點紀律

每個 gate 轉換（步驟切換、reviewer 回合結束、push、部署放行、批次結束）用一行 Bash 更新 state 檔的 `current_step` / `next_action` / `updated_at`。這是看門狗斷線復活與跨 session 接續的生命線，不可省略。

收尾標 `done` / `awaiting_user` 時一併寫 `ended_at`（`date -Iseconds`），步驟 5 的 `collect-run-metrics.py` 會用 `started_at`~`ended_at` 切出本任務的時間窗；沒寫就退化成整段 session 全額計入。

## 大任務切批（批次 = Session）

architect triage 為大改且可分解為多批 → 步驟 0 就切批寫進清單。每批結束：
1. 寫 / 更新 `~/.claude/state/<slug>-handoff.md`（本批完成內容、commit hash、下一批輸入、地雷）
2. state 標 `awaiting_next_batch`，回報本批結果後**結束本 session 的工作**
3. 看門狗會自動開新 session 跑「/dev 繼續 <slug>」（新 process = 乾淨 context）；使用者也可手動下同一指令

## 最終回報（一次性，必含五件事）

1. 驗收結果逐條（A1…An，附證據檔路徑）
2. **1 分鐘複驗指引**（URL + 帳號 + ≤3 步操作 + 應看到什麼）
3. 「我幫你做的決定」清單（含三方案採納理由）
4. questions.md 內容（若有）與 blockers（若有）
5. state 檔標 `reported`（使用者確認收工、或明說不用再回頭時才標 `done`）
