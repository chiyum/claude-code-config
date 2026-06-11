# Claude Code Configuration Template

我的 Claude Code（Anthropic CLI）完整配置範本，涵蓋開發流程規範、多 Agent 協作、自訂 Skill、產品驗收體系與 Hook 整合。

> 這份設定從個人實際工作環境脫敏而來，移除了所有帳密、URL、路徑等敏感資訊，保留架構與邏輯供參考。

**第一次使用？** 請先看 [安裝與設定指南（SETUP_GUIDE.md）](SETUP_GUIDE.md)，裡面有一步步的操作說明。

## 目錄結構

```
claude-code-config/
├── CLAUDE.md                  # 全域開發規範（主 Claude 指令集）
├── settings.json              # Claude Code 設定檔
├── mcp.json                   # MCP Server 配置
├── .gitignore                 # 排除對話/快取/機密
├── agents/                    # 自訂 Agent 定義
│   ├── architect.md           # 架構師：三方案分析 + 實作
│   ├── pm.md                  # 產品經理：規格驗收
│   ├── qa.md                  # QA：本地 + 線上測試
│   └── reviewer.md            # 審查員：code review
├── hooks/
│   └── slack-notify.sh        # Stop hook：完成回覆後推 Slack
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

### 1. 標準開發流程（CLAUDE.md）

所有「修改 code」的任務走固定五步驟，主 Claude 是 orchestrator：

```
architect 開發 → reviewer 審查 → 本地 QA + PM 驗收 → push 觸發部署 → 線上 QA
```

主 Claude 不直接改 code，而是把需求、上下文、約束打包交給對應 agent。

### 2. Agent 分工

| Agent | 職責 | 特色 |
|-------|------|------|
| **architect** | 設計 + 實作 | 自動判斷任務複雜度：小改動直接做，大改動先產出三方案分析等使用者選 |
| **reviewer** | Code review | 涵蓋安全、效能、Redis 殭屍、Cache invalidation、Race condition 等 10+ 維度 |
| **qa** | 測試 | API curl + Playwright MCP 雙軌，本地→線上分階段 |
| **pm** | 驗收 | 產品無關設計，每次從 INDEX.md 載入對應產品配置 |

### 3. 產品配置體系

PM / QA agent 不硬寫任何產品資訊，而是透過 `products/INDEX.md` 索引找到目標產品的 `.md` 配置檔，動態載入：

- 規格書路徑
- 測試環境 URL / Port
- 測試帳號
- 重要規約（驗收 checklist）
- 截圖存放路徑

新增產品只需加一份 `.md` + 在 INDEX 加一行。

### 4. Skill 系統

Skill 是可重複使用的自動化腳本，用自然語言觸發：

- `/merge-prod`：自動把三個 repo 的 main 合併到 prod 部署分支
- `/test-line-message-integrity`：模擬多訪客 + 客服切換壓力測試
- `/test-web-message-integrity`：Web WebSocket 版的訊息完整性壓測
- `/verify-ocr-version`：給出一組指令驗證線上 sidecar 是否部署到最新版

### 5. Hook 整合

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
