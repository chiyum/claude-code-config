# Claude Code Configuration Template

我的 Claude Code（Anthropic CLI）完整配置範本，涵蓋開發流程規範、多 Agent 協作、自訂 Skill、產品驗收體系與 Hook 整合。

> 這份設定從個人實際工作環境脫敏而來，移除了所有帳密、URL、路徑等敏感資訊，保留架構與邏輯供參考。

**第一次使用？** 請先看 [安裝與設定指南（SETUP_GUIDE.md）](SETUP_GUIDE.md)，裡面有一步步的操作說明。

**想先看全貌？** [工作流程圖（WORKFLOW.md）](WORKFLOW.md) 把「編排協定 + 五步驟開發流程」畫成一張 Mermaid 流程圖。

## 目錄結構

```
claude-code-config/
├── CLAUDE.md                  # 全域開發規範（主 Claude 指令集）：編排協定 + 開發流程步驟 0~5
├── SETUP_GUIDE.md             # 一步步的安裝與設定指南
├── DECISION_LOG.md            # ADR 決策紀錄制度的單一真相來源
├── settings.json              # Claude Code 設定檔（權限 / Stop hook / plugin）
├── mcp.json                   # MCP Server 配置
├── .gitignore                 # 排除對話/快取/機密
├── agents/                    # 自訂 Agent 定義
│   ├── architect.md           # 架構師：三方案分析 + 實作
│   ├── pm.md                  # 產品經理：規格驗收
│   ├── qa.md                  # QA：本地 + 線上測試
│   └── reviewer.md            # 審查員：code review
├── hooks/
│   └── slack-notify.sh        # Stop hook：完成回覆後推 Slack
├── scripts/                   # 流程用確定性腳本
│   ├── verify-deploy.sh       # 事件驅動部署驗證：輪詢 version endpoint 確認新版本上線
│   ├── pre-review.sh          # reviewer 前的確定性預檢（lint / go vet / Redis TTL 掃描）
│   ├── verify-evidence.sh     # 驗收放行前的證據完整性檢查（每條 A<n> 至少一個證據檔）
│   ├── watchdog.sh            # 斷線看門狗核心（平台無關）：復活中斷任務、接續下一批
│   ├── install-watchdog.sh    # 看門狗排程安裝器（launchd / cron / Windows 排程器）
│   └── codex-probe.sh         # （選用）Codex 呼喚前的可用性/額度探測（未裝 Codex 則永遠 exit 2 安全跳過）
├── acceptance/                # 凍結驗收清單 + 驗收證據（步驟 0 產生，PM 驗收唯一依據）
│   └── README.md              # 三段式清單格式 / 證據規約 / 任務憲章格式 / 凍結規則
├── state/                     # 任務檢查點與看門狗（斷線自我恢復 + 跨 session 接續）
│   ├── README.md              # 檢查點檔格式與 status 語義
│   └── watchdog.conf          # 看門狗參數（心跳門檻 / 重啟上限 / 權限旗標）
├── knowledge/                 # 工程知識庫（跨專案可複用的教訓 / 模式）
│   ├── INDEX.md               # 知識卡索引（Playbook 層 + 依技術 / 問題類別分類）
│   ├── example-card.md        # 範例知識卡
│   └── playbooks/             # Playbook 蒸餾層（每個技術域一份設計框架）
│       └── PLAYBOOK_TEMPLATE.md   # Playbook 結構範本
├── products/                  # 產品配置（PM/QA 用，含各產品「部署驗證」章節）
│   ├── INDEX.md               # 產品索引
│   └── example_product.md     # 範例產品配置
└── skills/                    # 自訂 Skill
    ├── dev/                   # /dev 一鍵自主開發管線（五步驟入口）
    ├── merge-prod/            # 合併正式站
    ├── test-line-message-integrity/   # LINE 訊息完整性壓測
    ├── test-web-message-integrity/    # Web 訊息完整性壓測
    └── verify-ocr-version/    # OCR sidecar 版本驗證
```

## 核心設計理念

### 1. 編排協定（凌駕於五步驟之上）

走「骨架確定性、葉子按需委派」路線：五步驟骨架、所有 gate、回退條件一律由 CLAUDE.md 確定性控制，不交給模型自動編排。

- **Session 基準 effort 固定 `high`**：日常主迴圈與所有 subagent 都跑 high，不整段開 xhigh 自動編排。
- **火力靠「加人手」而非「加單人腦力」**：重活（大改、三方案、對抗式 review）由 orchestrator 單點展開 **Dynamic Workflow**，以多個平行 agent（每隻仍 high）分工。
- **例外可「單葉」升 xhigh**：極難的單線推理（複雜演算法、深層 race condition）可把「那一隻」agent 單獨拉高，需先向使用者宣告理由。
- **兩道護欄**：(A) architect ↔ reviewer 外層 3 回合上限與各 gate 由骨架決定，模型不得自行跳過或加碼；(B) one-agent-one-partition — 平行 agent 一律唯讀且維度互斥，只允許最後單一 convergence step 匯總。

### 2. 標準開發流程（CLAUDE.md）

所有「修改 code」的任務走固定步驟（0~5），主 Claude 是 orchestrator：

```
⓪ 驗收條件凍結 → ① architect 開發 → pre-review 預檢 → reviewer 審查
→ ② 本地 QA + PM 驗收 → ③ push 觸發部署 → ④ 部署驗證 + 線上 QA → ⑤ 回報
```

主 Claude 不直接改 code，而是把需求、上下文、約束打包交給對應 agent。architect 實作時，**code + 規格書更新 + （必要時）ADR / 知識卡放在同一個 commit**。

四個確定性關卡讓流程更穩：**步驟 0 凍結驗收清單**（破除「architect 自己出題自己改考卷」的循環依賴，PM 驗收以凍結清單為唯一依據；每條三段式「行為 + 驗證步驟 + 預期結果」，驗法凍結時就定案）、**pre-review 腳本**（lint / go vet / Redis TTL 等可規則化的錯誤在 reviewer 前攔截，不佔 reviewer 回合）、**證據落地 gate**（見下方「反假驗收三層 gate」）、**事件驅動部署驗證**（`verify-deploy.sh` 輪詢 version endpoint 確認新版本上線才放行 QA，取代固定等 5 分鐘；未設定 version endpoint 的產品自動沿用舊行為）。

流程尾端還有一道「**1 分鐘複驗指引**」：最終回報必附確切 URL + 帳號 + 3 步以內操作 + 應看到什麼，使用者照著走走不通就視為流程缺陷退回修正，不歸因於使用者操作。

### 2.1 反假驗收三層 gate（證據落地）

QA/PM 說「通過」不算數，要能被確定性驗證：

1. **證據落地**：QA/PM 每驗一條 `A<n>` 必須落地證據檔（截圖 / curl 輸出）到 `acceptance/<任務>/evidence/`，檔名含 `A<n>-`；主 Claude 放行前跑 `verify-evidence.sh`，任一條零證據就不放行
2. **抽驗**：腳本通過後主 Claude 親自 Read 抽驗 1-2 張關鍵截圖，畫面內容對不上條目宣稱 → 整份驗收報告降級為不可信，全部重驗
3. **反方 PM**：大改動加開一隻以「證明功能沒完成」為目標的獨立 agent，專挑反例（換帳號、換租戶、重整、斷線重連）；反方找不到反例才算真通過

### 2.2 任務憲章（大型 / 自主任務）

步驟 0 凍結清單時同檔加一份「任務憲章」：範圍、非目標、**預授權決策表**（把可預期的問題先答掉）、**必問白名單**（不可逆刪資料 / 花錢 / 資安 / 碰 prod / 需求自相矛盾——只有這些准中斷）。憲章凍結後 agent 想提問先對照憲章：能自答就自答並記入決策紀錄，白名單外的疑問寫進 `state/<task>-questions.md` 批次結束一併呈報，不中斷流程。

### 2.3 檢查點與看門狗（斷線自我恢復）

走五步驟的任務都維護檢查點檔 `state/<任務slug>.json`（current_step / next_action / status / 心跳），每個 gate 轉換更新一次。`scripts/watchdog.sh` 由排程器每 10 分鐘喚醒（`install-watchdog.sh` 依平台注入 launchd / cron / Windows 工作排程器）：`running` 且心跳逾期且 transcript 沒在動 → `claude --resume` 復活（上限 3 次，transcript mtime 活性判定防誤殺長工具呼叫）；`awaiting_user` 一律不動；`done` 過期自動清理。

> ⚠️ **安全警示（--dangerously-skip-permissions）**：看門狗預設以 `--dangerously-skip-permissions` 無頭復活 session——復活絕不會卡在權限提示，但代價是**該 session 在無人監督下擁有完整權限**（可執行任意指令、改任意檔案、對外連線）。這是為「全自主開發」情境做的取捨，套用前請確認你接受此風險；若在共用機器、含敏感資料的環境，或你不完全信任任務內容，請在 `state/watchdog.conf` 改為 `PERMISSION_FLAGS=""`（保守模式：復活 session 碰到未在 `settings.json` `permissions.allow` 白名單的工具會停下等人）。

### 2.4 大型任務切批（批次 = Session）

大改動可分解為多批時，步驟 0 就切批寫進驗收清單。每批結束寫交接檔 `state/<task>-handoff.md`（完成內容、commit hash、下一批輸入、地雷），state 標 `awaiting_next_batch` 後結束本 session；看門狗自動開**新 session** 接續下一批——新 process = 乾淨 context，資訊靠交接檔 + 檢查點無損傳遞，從根本上控制 context 膨脹。

### 3. Agent 分工

| Agent | 職責 | 特色 |
|-------|------|------|
| **architect** | 設計 + 實作 | 自動判斷任務複雜度：小改動直接做，大改動先產出三方案分析等使用者選 |
| **reviewer** | Code review | 涵蓋安全、效能、Redis 殭屍、Cache invalidation、Race condition 等 10+ 維度 |
| **qa** | 測試 | API curl + Playwright MCP 雙軌，本地→線上分階段 |
| **pm** | 驗收 | 產品無關設計，每次從 INDEX.md 載入對應產品配置 |

### 4. 產品配置體系

PM / QA agent 不硬寫任何產品資訊，而是透過 `products/INDEX.md` 索引找到目標產品的 `.md` 配置檔，動態載入：

- 規格書路徑
- 測試環境 URL / Port
- 測試帳號
- 重要規約（驗收 checklist）
- 截圖存放路徑

新增產品只需加一份 `.md` + 在 INDEX 加一行。

### 5. ADR 決策紀錄制度（DECISION_LOG.md）

把每一次「為什麼這樣決定」留存下來，供未來的人或 Claude 回頭查證。採**混合存放**：

- **產品相關決策**（綁某個 repo）→ 該 repo 內 `docs/adr/NNNN-*.md`，並在對應產品配置加一行索引
- **跨產品 / 個人工作流決策** → 放 `~/.claude/`

判斷原則：「這個決策換到別的專案還成立嗎？」成立就放 `~/.claude`，只對這個產品成立就放該 repo。走「決策當下立即記」——選型 / 重大架構 / 不可逆或高回滾成本 / 推翻先前決策時，architect 在同一個 commit 內補一筆 ADR。一般 bug 修復、小重構、照既有規格實作不需寫。`DECISION_LOG.md` 是這套制度的單一真相來源（含觸發門檻與範本）。

### 6. 工程知識庫（knowledge/）

一套**跨專案、可複用的工程教訓 / 模式知識庫**，是 architect / reviewer 的「成長引擎」。與 memory、ADR 的分工：

- **memory** 記「發生過什麼」、**ADR** 記「為什麼這樣決定」、**知識卡** 記「下次碰到 X 技術，照這個做 / 別踩這個坑」

agent 接到任務時先讀 `knowledge/INDEX.md`，**優先讀命中技術域的 Playbook**（`knowledge/playbooks/`），需要事故細節再深入個別知識卡；工作中撞到非顯而易見的坑或學到有效模式時，當下補一張卡並回 INDEX 補列。專案越累積，agent 越「有經驗」。

**Playbook 蒸餾層**：同一技術域累積 3~5 張卡後，把它們蒸餾成一份 playbook——「設計決策流程 + 必過檢查清單 + 已知坑速查」，讓 agent 一次 Read 拿到整套框架，而不是每次翻 N 張零散的卡（結構範本見 `knowledge/playbooks/PLAYBOOK_TEMPLATE.md`）。playbook 是活的：新卡屬於某 playbook 的域時，同一 commit 在該 playbook 補一列檢查項並連回新卡，保證蒸餾層不過時。

### 7. Skill 系統

Skill 是可重複使用的自動化腳本，用自然語言觸發：

- `/dev`：**一鍵自主開發管線**——五步驟流程的統一入口，三種模式：`/dev <需求>`（凍結清單前停一次確認）、`/dev auto <需求>`（零停頓全自主，靠任務憲章自答問題）、`/dev 繼續 <任務slug>`（接續中斷任務或下一批）。使用者用自然語言授權自主開發（「不用問做完再回報」等語意）時，主 Claude 也必須主動 invoke 此 skill，等同 `/dev auto`
- `/merge-prod`：自動把三個 repo 的 main 合併到 prod 部署分支
- `/test-line-message-integrity`：模擬多訪客 + 客服切換壓力測試
- `/test-web-message-integrity`：Web WebSocket 版的訊息完整性壓測
- `/verify-ocr-version`：給出一組指令驗證線上 sidecar 是否部署到最新版

### 8. Hook 整合

`hooks/slack-notify.sh` 在每次 Claude 回覆後，自動把回覆內容推到 Slack channel，方便不在電腦前時追蹤進度。

### 9. 選用整合：Codex 異模型第二意見（預設停用）

同模型的 reviewer 有系統性盲點，異模型（OpenAI Codex CLI）在四種關鍵場景提供第二視角：重大改動的異模型加掃、卡關 3 次後的破局第二腦、極難推理的獨立解交叉比對、OpenAI 生態系問題。設計重點是**選用且 non-blocking**：

- 呼喚前必跑 `scripts/codex-probe.sh` 做可用性/額度探測——未安裝、未登入、額度不足、逾時任一情況都直接跳過 Codex 走原流程，避免正式任務跑到一半沒額度卡住
- Codex 產出只是參考意見，不作任何 gate 的放行依據；中途失敗即棄，自家 agent 無縫接續
- **預設停用**——沒裝 Codex 的環境完全不受影響；啟用方式與完整規約見 `CLAUDE.md`「選用模組：Codex CLI 異模型第二意見」

## 如何使用

1. **複製到 `~/.claude/`**：把需要的檔案放到你的 Claude Code 設定目錄
2. **客製化 CLAUDE.md**：根據你的技術棧、團隊規範、專案結構修改
3. **建立產品配置**：在 `products/` 下為每個專案建配置檔
4. **設定 Hook**：如果要用 Slack 通知，建立 `hooks/slack-webhook.url` 放 webhook URL

## 注意事項

- 所有路徑已替換為 `$HOME` 或 `<your-path>` 佔位符
- 所有帳密、API URL、webhook URL 已移除
- Skill 內的腳本保留邏輯但移除了硬編碼的環境資訊
- `settings.local.json` 不在此 repo 中（放個人覆寫設定用，不應公開）

## 技術棧參考

這份設定是為以下技術棧量身打造，但 agent / skill 架構可套用到任何專案：

- **前端**：Vue 3 + TypeScript + Vite + Pinia + Quasar
- **後端**：Go + Gin
- **測試**：Playwright MCP（瀏覽器自動化）+ curl API 測試
- **部署**：Docker Compose + CI/CD 自動部署

## License

MIT
