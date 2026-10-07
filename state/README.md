# state/ — 任務檢查點與看門狗

斷線自我恢復 + 跨 session 接續的共用基建。骨架規約見 `~/.claude/CLAUDE.md`「檢查點與切批」節；執行細節即本檔＋dev skill。

## 檢查點檔 `<任務slug>.json`

主 Claude 在五步驟每個 gate 轉換時更新（一行 Bash）。欄位：

```json
{
  "task": "20260706-xxx",
  "session_id": "<當前 session transcript 檔名的 UUID>",
  "product": "example_product",
  "config_dir": "~/.ai-profiles/claude/<profile>",
  "current_step": "2",
  "next_action": "QA 本地驗證 A3-A5",
  "status": "running",
  "started_at": "2026-08-22T10:15:00+08:00",
  "ended_at": null,
  "restart_count": 0,
  "updated_at": 1751800000
}
```

- `session_id` 取法（任務開始時取一次；換 session 接續時要更新）：**直接讀環境變數** `echo "$CLAUDE_CODE_SESSION_ID"`
  - 舊寫法 `ls -t ~/.claude/projects/<專案目錄 slug>/*.jsonl | head -1` **會失準**：用 profile 機制（`CLAUDE_CONFIG_DIR=~/.ai-profiles/claude/<profile>`）時 transcript 實體在 `~/.ai-profiles/<tool>/<profile>/projects/`，舊路徑只剩歷史檔，取到的是某個陳年 session。收錯 session＝整筆遙測記到別的任務頭上（`<專案目錄 slug>` 是 Claude Code 依工作目錄產生的目錄名）
  - 環境變數不存在時的退路（跨兩個根目錄取最新）：`basename "$(ls -t ~/.ai-profiles/claude/*/projects/*/*.jsonl ~/.claude/projects/*/*.jsonl 2>/dev/null | head -1)" .jsonl`
- `config_dir`：`echo "$CLAUDE_CONFIG_DIR"`（空字串代表 `~/.claude`）。看門狗復活 / 接續時用它啟動**同一個 profile**；缺欄時由 transcript 路徑推回，再缺才用 `watchdog.conf` 的 `DEFAULT_CONFIG_DIR`。2026-09-13 前沒這欄，看門狗一律用 `~/.claude` 起 claude，對 profile 內的 session 全部回「No conversation found」
- **state 檔只放本節欄位＋短字串（單欄 ≤ 300 字）**：決策紀錄、commit 清單、審查回合內容一律寫 `<task>-handoff.md`，不得把 state 當日誌（2026-09-13 實例：一份 state 長到 47KB，每次 `/dev 繼續` 整份進 context）
- `started_at` / `ended_at`：ISO8601（`date -Iseconds`）。**遙測分帳的唯一依據**——一個 session 常連續做多個任務，`collect-run-metrics.py` 靠這兩欄切出本任務的時間窗；缺了就退化成「整段 session 全額計給本任務」，同 session 的每個任務都會拿到同一組數字（2026-08-22 複盤實測：61 筆 run 有 31 筆被這樣重複計算）
  - `started_at` 步驟 0 建立檔案時就寫；`ended_at` 在標 `done` / `awaiting_user` 時補
  - 跨 session 接續的任務：`started_at` **不要覆寫**，維持第一批的起點；`sessions` 陣列則累加新的 session id
- `status` 語義：
  - `running`：進行中。心跳（updated_at）逾期且 transcript 也沒在動 → 看門狗 `claude --resume` 復活
  - `awaiting_user`：**真的需要使用者拍板**（方案確認、白名單提問）才用。看門狗不動它
  - `reported`：做完回報、等下一個指令（是否合 prod、是否加功能）。看門狗不動它；與 `awaiting_user` 分開是為了讓使用者一眼分出「要我決定」和「只是做完了」
  - `awaiting_next_batch`：本批完成、等接續。看門狗會開**新 session** 跑「/dev 繼續 <task>」（新 process = 乾淨 context）
  - `done`：使用者確認收工。看門狗保留 N 天後連同 handoff / questions 檔一起搬到 `archive/`
  - 任何狀態的 state 檔 mtime 超過 `IDLE_ARCHIVE_DAYS`（預設 14 天）→ 看門狗搬到 `state/archive/`（不刪）；殭屍 running（已達重啟上限、缺 session_id）靠這條退場
- `updated_at` 一律 epoch 秒（`date +%s`）

## 外部規格模式追加欄位（`spec_mode: external`；協定見 `~/.claude/acceptance/EXTERNAL_SPEC_PROTOCOL.md`）

原生模式 state 完全不變、不需要這些欄位。外部規格 run 由 `verify-external-spec.py` 的輸出 jq 合成，至少多這些：

```json
{
  "run_id": "RUN-20260908-001",
  "spec_mode": "external",
  "spec_id": "SPC-EX-20260908-001",
  "spec_version": "1.0",
  "spec_path": "~/.claude/specs/example_product/SPC-EX-20260908-001/v1.0/SPEC.md",
  "spec_sha256": "<64 hex>",
  "manifest_path": "~/.claude/specs/example_product/SPC-EX-20260908-001/v1.0/manifest.json",
  "target_environment": "dev",
  "acceptance": "<同 spec_path；看門狗復活提示會叫它讀「對應 acceptance 清單」>",
  "acceptance_ids": ["A1", "A2"],
  "evidence_root": "~/.claude/acceptance/SPC-EX-20260908-001/RUN-20260908-001",
  "environment_confirmed": "<只有使用者明確確認 prod 時才寫 prod；spec-gate 會帶給驗證器>",
  "last_spec_gate": {"gate": "reviewer r1 前", "at": "2026-09-08T10:00:00+08:00", "result": "pass"},
  "change_requests": [],
  "spec_drift": null,
  "blocked_reason": null
}
```

- `spec_sha256` 一旦寫入就是本 run 的綁定值，**不得更新**；規格改版要由使用者重新啟動新 run
- 每個 gate 轉換前跑 `bash ~/.claude/scripts/spec-gate.sh <state.json> "<gate>"`：通過寫 `last_spec_gate`；hash 漂移把 `status` 改 `blocked_spec_drift` 並填 `spec_drift`（gate / 舊 hash / 新 hash）；其他驗證錯誤改 `blocked_spec_invalid` 並填 `blocked_reason`
- 追加的 status 值：`blocked_spec_drift`、`blocked_spec_invalid`——看門狗對未知狀態一律不動，所以這兩種 run 不會被自動復活，需使用者處置後重新啟動
- 外部規格 run 的 `<task>-handoff.md` 開頭必含同一組 spec metadata（spec_id / spec_version / spec_sha256 / spec_path / run_id / target_environment），接續 session 第一步先跑 spec-gate

## 配套檔（同目錄、同 slug）

- `<task>-handoff.md`：批次交接檔（本批完成內容、commit hash、下一批輸入、地雷）
- `<task>-questions.md`：**只收「需要使用者決定」的項目**，每條固定四行：`問題` / `我暫採`（現在先怎麼做） / `影響`（選錯會怎樣、改回來的成本） / `選項`（A / B 各一句白話）。裁決過程、reviewer 回合判定、決策理由寫 handoff.md 的「決策紀錄」節或 ADR，不寫進這裡（2026-09-13 實例：一份 questions.md 長到 92KB、80 條，使用者要讀完才能拍板，等於沒回報）
- `<task>.resume.log`：看門狗復活該任務時的無頭輸出

## 看門狗

- 核心：`~/.claude/scripts/watchdog.sh`（平台無關，冪等，可手動執行測試）
- 排程注入：`~/.claude/scripts/install-watchdog.sh` 偵測平台安裝 launchd（macOS）/ cron（Linux、WSL）/ 印出 Windows 工作排程器指令
- 設定：`watchdog.conf`（STALE_SECONDS / MAX_RESTART / PERMISSION_FLAGS / CLAUDE_BIN）
- 防呆：單實例鎖、transcript mtime 活性判定（長工具呼叫不誤殺；transcript 同時掃 `~/.ai-profiles/claude/*/projects/` 與 `~/.claude/projects/`）、重啟上限 3 次後停手留 log（同一則警告 24 小時只記一次）、log 超過 2MB 自動輪替
- 復活 / 接續一律帶 `CLAUDE_CONFIG_DIR`（取法見上方 `config_dir` 欄），確保回到同一個 profile
