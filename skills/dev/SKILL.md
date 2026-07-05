---
name: dev
description: 一鍵自主開發管線。對使用者需求自主跑完五步驟（PM 凍結清單+憲章 → architect → pre-review → reviewer → 本地 QA/PM 證據驗收 → push → dev 驗證 → 一次性回報），全程寫檢查點、依憲章自答問題、大任務自動切批。用法：/dev <需求文字>（凍結前停一次確認）、/dev auto <需求文字>（零停頓全自主）、/dev 繼續 <任務slug>（接續中斷任務或下一批）。
---

# /dev — 自主開發管線

本 skill 是 `~/.claude/CLAUDE.md` 五步驟流程的「一鍵入口」。所有既有規則（編排協定、gate、3 回合上限、證據落地、知識庫 playbook、ADR、規格同步）照常適用，本檔只定義入口行為與自主模式差異點。

## 引數解析

- 以 `繼續 ` 開頭 → **接續模式**：Read `~/.claude/state/<slug>.json`、`<slug>-handoff.md`、`<slug>-questions.md`、對應 acceptance 清單，把 state 檔的 `session_id` 更新為本 session 的 transcript UUID、`status` 設 `running`，從 `next_action` / 下一批繼續。
- 以 `auto ` 開頭 → **全自主模式**：步驟 0 憑證（清單+憲章）產出並寫檔後**不停等確認**直接開跑，最後一次性回報。
- 其他 → **標準模式**：步驟 0 產出清單+憲章後呈現一次給使用者，確認即凍結，之後零中斷直到最終回報。

## 開跑時提示使用者疊加 /goal（雙層保險）

任務開跑的第一則回應中，提示使用者（僅提示一次，不強制）：
> 建議同時下 `/goal ~/.claude/state/<slug>.json 的 status 變成 done 或 awaiting_user`
> session 活著時 /goal 秒級續跑（turn 意外停下立刻拉起），session 死掉才輪到看門狗 10 分鐘級復活。

/goal 是使用者層指令，主 Claude 不能代下，只能提示。

## 開跑前置（三件事，依序）

1. 產品上下文偵測與載入（照 CLAUDE.md session 啟動規則）
2. 任務 slug = `<YYYYMMDD>-<簡述>`；建檢查點檔 `~/.claude/state/<slug>.json`（格式見 `~/.claude/state/README.md`；session_id 用 `basename "$(ls -t ~/.claude/projects/<專案目錄 slug>/*.jsonl | head -1)" .jsonl` 取）
3. 步驟 0：PM 產三段式驗收清單；主 Claude 補**任務憲章**寫入同一份 acceptance 檔（格式見 `~/.claude/acceptance/README.md`）

## 自主模式差異點（凌駕日常「先問」條款）

1. **三方案不停等**：architect 產出三方案後，主 Claude 直接採納推薦方案，理由記入最終回報的「我幫你做的決定」清單；屬 ADR 門檻的照常寫 ADR。
2. **提問三分流**：任何 agent（含主 Claude 自己）想提問時，先對照憲章——
   - 憲章預授權決策表能自答 → 自答並記入決策紀錄
   - 命中必問白名單（不可逆刪資料 / 花錢 / 資安 / 碰 prod / 需求自相矛盾）→ 才准中斷（state 標 `awaiting_user`）
   - 其餘 → 寫進 `~/.claude/state/<slug>-questions.md`，不中斷，最終回報一併呈上
3. **3 回合超限不停**：architect↔reviewer 超過 3 回合時，該項凍結記入 blockers、繼續其餘工作、最終回報一併列出（不中途打斷使用者）。
4. **push 帳號**：讀產品配置「git 帳號歸屬」欄；缺欄才問一次，問完立刻寫回產品配置。

## 檢查點紀律

每個 gate 轉換（步驟切換、reviewer 回合結束、push、部署放行、批次結束）用一行 Bash 更新 state 檔的 `current_step` / `next_action` / `updated_at`。這是看門狗斷線復活與跨 session 接續的生命線，不可省略。

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
5. state 檔標 `done`
