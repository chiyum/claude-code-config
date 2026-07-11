# state/ — 任務檢查點與看門狗

斷線自我恢復 + 跨 session 接續的共用基建。骨架規約見 `~/.claude/CLAUDE.md`「檢查點與切批」節；執行細節即本檔＋dev skill。

## 檢查點檔 `<任務slug>.json`

主 Claude 在五步驟每個 gate 轉換時更新（一行 Bash）。欄位：

```json
{
  "task": "20260706-xxx",
  "session_id": "<當前 session transcript 檔名的 UUID>",
  "product": "example_product",
  "current_step": "2",
  "next_action": "QA 本地驗證 A3-A5",
  "status": "running",
  "restart_count": 0,
  "updated_at": 1751800000
}
```

- `session_id` 取法（任務開始時取一次；換 session 接續時要更新）：
  `basename "$(ls -t ~/.claude/projects/<專案目錄 slug>/*.jsonl | head -1)" .jsonl`
  （`<專案目錄 slug>` 是 Claude Code 依工作目錄產生的目錄名，例如從家目錄啟動時形如 `-Users-<username>`）
- `status` 語義：
  - `running`：進行中。心跳（updated_at）逾期且 transcript 也沒在動 → 看門狗 `claude --resume` 復活
  - `awaiting_user`：等使用者輸入（方案確認、白名單提問）。看門狗不動它
  - `awaiting_next_batch`：本批完成、等接續。看門狗會開**新 session** 跑「/dev 繼續 <task>」（新 process = 乾淨 context）
  - `done`：完成。看門狗保留 N 天後連同 handoff / questions 檔一起清掉
- `updated_at` 一律 epoch 秒（`date +%s`）

## 配套檔（同目錄、同 slug）

- `<task>-handoff.md`：批次交接檔（本批完成內容、commit hash、下一批輸入、地雷）
- `<task>-questions.md`：憲章白名單外的疑問累積（批次結束一併呈報，不中斷流程）
- `<task>.resume.log`：看門狗復活該任務時的無頭輸出

## 看門狗

- 核心：`~/.claude/scripts/watchdog.sh`（平台無關，冪等，可手動執行測試）
- 排程注入：`~/.claude/scripts/install-watchdog.sh` 偵測平台安裝 launchd（macOS）/ cron（Linux、WSL）/ 印出 Windows 工作排程器指令
- 設定：`watchdog.conf`（STALE_SECONDS / MAX_RESTART / PERMISSION_FLAGS / CLAUDE_BIN）
- 防呆：單實例鎖、transcript mtime 活性判定（長工具呼叫不誤殺）、重啟上限 3 次後停手留 log
