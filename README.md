# Claude Code Configuration Template

我的 Claude Code（Anthropic CLI）完整配置範本，涵蓋開發流程規範、多 Agent 協作、自訂 Skill、產品驗收體系與 Hook 整合。

> 這份設定從個人實際工作環境脫敏而來，移除了所有帳密、URL、路徑等敏感資訊，保留架構與邏輯供參考。

**第一次使用？** 請先看 [安裝與設定指南（SETUP_GUIDE.md）](SETUP_GUIDE.md)，裡面有一步步的操作說明。

**想先看全貌？** [工作流程圖（WORKFLOW.md）](WORKFLOW.md) 把「編排協定 + 五步驟開發流程」畫成一張 Mermaid 流程圖。

## 目錄結構

```
claude-code-config/
├── CLAUDE.md                  # 全域開發規範（主 Claude 指令集）：編排協定 + 五步驟開發流程
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
├── knowledge/                 # 工程知識庫（跨專案可複用的教訓 / 模式）
│   ├── INDEX.md               # 知識卡索引（依技術 / 問題類別分類）
│   └── example-card.md        # 範例知識卡
├── products/                  # 產品配置（PM/QA 用）
│   ├── INDEX.md               # 產品索引
│   └── example_product.md     # 範例產品配置
└── skills/                    # 自訂 Skill
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

所有「修改 code」的任務走固定五步驟，主 Claude 是 orchestrator：

```
architect 開發 → reviewer 審查 → 本地 QA + PM 驗收 → push 觸發部署 → 線上 QA
```

主 Claude 不直接改 code，而是把需求、上下文、約束打包交給對應 agent。architect 實作時，**code + 規格書更新 + （必要時）ADR / 知識卡放在同一個 commit**。

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

agent 接到任務時先讀 `knowledge/INDEX.md`，依涉及技術（websocket / redis / go…）與問題類別（高併發 / 快取一致性 / race…）比對標籤，只讀命中的卡；工作中撞到非顯而易見的坑或學到有效模式時，當下補一張卡並回 INDEX 補列。專案越累積，agent 越「有經驗」。

### 7. Skill 系統

Skill 是可重複使用的自動化腳本，用自然語言觸發：

- `/merge-prod`：自動把三個 repo 的 main 合併到 prod 部署分支
- `/test-line-message-integrity`：模擬多訪客 + 客服切換壓力測試
- `/test-web-message-integrity`：Web WebSocket 版的訊息完整性壓測
- `/verify-ocr-version`：給出一組指令驗證線上 sidecar 是否部署到最新版

### 8. Hook 整合

`hooks/slack-notify.sh` 在每次 Claude 回覆後，自動把回覆內容推到 Slack channel，方便不在電腦前時追蹤進度。

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
