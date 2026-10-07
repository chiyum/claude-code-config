# run-metrics/ — 任務級 run 遙測（制度改動的量化比對基準）

目的：每次調整全域架構（CLAUDE.md / agents / 流程）後，能用數據回答「這次改動讓 agent 更省 token、更少來回了嗎？」。每筆五步驟任務結束時落一筆 run 記錄，累積後按 config 版本分組看趨勢。

## 檔案

- `runs/<YYYYMMDD>-<任務slug>.json` — 每任務一筆 run 記錄（上 git）
- `../scripts/collect-run-metrics.py` — 收集器：解析 session transcript ＋ subagent transcript，零 token 開銷
- `../scripts/report-runs.py` — 報表：逐筆對照 ＋ 按 config commit 分組均值
- `../scripts/rate-run.py` — 把使用者的一行驗收評分寫回 run 記錄

## SOP

1. **收集（步驟 5 回報前，主 Claude 跑）**：
   `python3 ~/.claude/scripts/collect-run-metrics.py --slug <任務slug> --sessions <session id> [--started-at ISO --ended-at ISO] [--tasks-dir <scratch>/tasks] [--product <代號>] [--outcome done|blocked] [--notes "一句話"]`
   session id 與時間窗省略時自動從 `state/<slug>.json` 的 `session_id` / `started_at` / `ended_at` 取，所以檢查點寫好就不必手打。
   把輸出的 token 分帳與 agent 派遣摘要附進最終回報。**必須在任務結束當下跑**——transcript 有清理週期（預設約 30 天），事後補不回來。
   輸出末行會標明分帳狀態：`分帳: 已切窗 …` 才可當跨任務比較依據；`[warn] 分帳: 未切窗` 代表本筆是整段 session 全額，同 session 的其他任務會拿到同一組數字
2. **評分（使用者驗收後）**：口頭給 good / ok / bad ＋一句評語，主 Claude 跑 `rate-run.py --slug <slug> --verdict <v> --comment "<評語>"` 寫回
3. **比對（要看趨勢時）**：`python3 ~/.claude/scripts/report-runs.py [--last N]`

## run 記錄欄位語義

- `config_commit`：「制度檔案」（CLAUDE.md / agents / skills / scripts / DECISION_LOG.md / DESIGN_FLOW.md）最後一次被改動的 commit——把 run 綁到當時的制度版本，分組比較的 key。**不是 repo HEAD**：知識卡、驗收清單、產品配置的 commit 不改變此值，否則每補一張知識卡分組 key 就跳一次，永遠湊不滿同組樣本（2026-07-15 修正）
- `tokens.main_loop` / `tokens_by_agent.<type>`：主迴圈與各 agent 類型的 token 分帳（in / out / cache write / cache read）
- `tokens.total`：全部加總。**注意成本主體通常是 cache read**，比較時 out 與 cache read 都要看
- `agent_calls`：各 agent 類型派遣次數；`reviewer` 次數 ≈ 審查回合數、`qa`/`pm` 多次 ≈ 有退回重驗——這些是「流程順不順」的 proxy 指標
- `verdict` / `verdict_comment`：使用者的人工判定（good / ok / bad），機器指標無法涵蓋「流程順但結果爛」的情況，靠這欄補
- `outcome`：done / blocked / aborted
- `attribution`：`windowed`（已按任務時間窗切分，可比較）／`session-wide (unpartitioned)`（整段 session 全額，**不可**當跨任務比較依據）
- `window`：實際採用的 `started_at` / `ended_at`；兩者皆 null 即未切窗
- `shared_session_with`：本筆與哪些 run 共用 session id。有值代表這幾筆的 token 與 agent 次數彼此重複計算

## 已知限制

- 兩次 run 的任務不同，**不做逐筆硬比**；靠 config_commit 分組看均值趨勢，樣本 ≥5 筆才有意義
- **2026-08-22 之前的 run 一律未切窗**：當時收集器不支援時間窗，一個 session 做多個任務時整段全額計給每一筆。這些檔案應回填 `attribution: session-wide (unpartitioned)` 並標 `shared_session_with`。做趨勢分析時應排除、或至少不與切窗後的新資料混算
- subagent transcript 位置隨 harness 版本不同（inline sidechain / `~/.claude/tasks/` / session scratch `tasks/`），收集器三源都掃；歸不了戶的記在 `unknown`
- task-notification 的 `subagent_tokens` 是備援概數（記入 output_tokens），有 transcript 檔時以檔案為準
