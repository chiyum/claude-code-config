# 安裝與設定指南（給非工程師）

這份指南會教你怎麼把這套 Claude Code 設定套到你的電腦上。不需要寫程式能力，只要會用終端機（Terminal）貼上指令就行。

## 什麼是 Claude Code？

Claude Code 是 Anthropic 推出的 AI 程式助手。它可以：
- 幫你寫程式、改 bug、做 code review
- 用瀏覽器幫你測試網站功能
- 自動化部署流程

這套設定讓 Claude Code 變成一個**團隊**：有架構師、審查員、QA 測試員、產品經理，各司其職。

## 先決條件

1. **已安裝 Claude Code**：[官方安裝教學](https://docs.anthropic.com/en/docs/claude-code)
2. **已安裝 Node.js**（v22+）：壓力測試腳本需要
3. **已安裝 git**：版本控制用

## 安裝步驟

### 第 1 步：備份你現有的設定（如果有的話）

```bash
# 如果你之前用過 Claude Code，先備份
cp -r ~/.claude ~/.claude-backup-$(date +%Y%m%d)
```

### 第 2 步：複製設定檔

```bash
# 把這個 repo 的檔案複製到 Claude Code 設定目錄
# 注意：只複製你需要的，不要整個覆蓋

# 核心設定（建議全裝）
cp CLAUDE.md ~/.claude/CLAUDE.md
cp settings.json ~/.claude/settings.json
cp mcp.json ~/.claude/mcp.json
cp .gitignore ~/.claude/.gitignore
cp DECISION_LOG.md ~/.claude/DECISION_LOG.md

# Agent 定義（建議全裝）
mkdir -p ~/.claude/agents
cp agents/*.md ~/.claude/agents/

# 工程知識庫（成長系統，建議裝範本，之後由 agent 隨專案累積知識卡）
mkdir -p ~/.claude/knowledge
cp knowledge/*.md ~/.claude/knowledge/

# Hook 腳本（建議跟著 settings.json 一起裝——settings.json 的 Stop hook 指向這支腳本，
# 沒複製會每回合報「找不到腳本」。腳本本身是安全 no-op：沒設定 Slack webhook 就靜默跳過，
# 裝了它「不等於」會發通知；真的要通知才做下面第 3 步的「選做：設定 Slack 通知」。
# 完全不想要這個 hook：跳過這裡，並把 ~/.claude/settings.json 的 hooks.Stop 區塊整段刪掉）
mkdir -p ~/.claude/hooks
cp hooks/slack-notify.sh ~/.claude/hooks/
chmod +x ~/.claude/hooks/slack-notify.sh

# 產品配置（建議裝 INDEX + 範例，再依你的專案新增）
mkdir -p ~/.claude/products
cp products/INDEX.md ~/.claude/products/
cp products/example_product.md ~/.claude/products/

# Skill（選裝，按需要；skills/dev 是五步驟一鍵入口，建議裝）
cp -r skills/ ~/.claude/skills/

# 流程腳本 + 看門狗（建議全裝：pre-review 預檢、verify-deploy 部署驗證、
# verify-evidence 驗收證據檢查、watchdog 斷線自我恢復）
mkdir -p ~/.claude/scripts ~/.claude/state
cp scripts/*.sh ~/.claude/scripts/ && chmod +x ~/.claude/scripts/*.sh
cp state/README.md state/watchdog.conf ~/.claude/state/

# 驗收清單制度（規則檔）
mkdir -p ~/.claude/acceptance
cp acceptance/README.md ~/.claude/acceptance/
```

### 第 3 步：客製化

**必做：修改 CLAUDE.md**

打開 `~/.claude/CLAUDE.md`，把以下內容改成你的：

1. **技術棧**：如果你不是用 Vue 3 + Go，改成你的框架
2. **命名慣例**：依你團隊的規範
3. **語言設定**：如果你要英文註解，改掉「繁體中文」
4. **GitHub 多帳號**：如果你只有一個帳號，可以刪掉整個段落

**必做：建立你的產品配置**

複製 `products/example_product.md` 成 `products/<你的專案>.md`，填入：
- 規格書路徑
- 測試環境 URL 和 Port
- 測試帳號密碼
- 重要的業務規則

然後在 `products/INDEX.md` 加一行。

**選做：設定 Slack 通知**

如果你想讓 Claude 每次回覆後都推 Slack 通知：

```bash
# 1. 在 Slack 建一個 Incoming Webhook
# 2. 把 Webhook URL 存進這個檔案
echo "https://hooks.slack.com/services/YOUR/WEBHOOK/URL" > ~/.claude/hooks/slack-webhook.url
```

### 第 4 步：驗證

開一個新的 Claude Code session，試試看：

```bash
claude
```

然後跟它說：「請幫我看一下 agents 目錄有什麼」，它應該會列出 architect、pm、qa、reviewer、ui-designer、design-reviewer 六個 agent。

## 各檔案用途說明

| 檔案 | 做什麼的 | 一定要裝嗎？ |
|------|---------|------------|
| `CLAUDE.md` | Claude 的「行為守則」，定義開發流程、編碼規範、交棒規則 | ✅ 核心 |
| `settings.json` | Claude Code 的設定（權限、插件、Hook） | ✅ 核心 |
| `mcp.json` | MCP Server 設定（目前只有 Playwright 瀏覽器自動化） | ✅ 推薦 |
| `.gitignore` | 讓 git 忽略對話紀錄、快取、密碼等敏感檔案 | ✅ 推薦 |
| `agents/architect.md` | 架構師 agent：分析需求 → 提出三方案 → 選定後實作 | ✅ 推薦 |
| `agents/reviewer.md` | 審查員 agent：code review，抓安全、效能、邊界問題 | ✅ 推薦 |
| `agents/qa.md` | QA agent：用 API + 瀏覽器自動化跑測試 | ✅ 推薦 |
| `agents/pm.md` | PM agent：對照規格書做驗收，截圖回報 | ✅ 推薦 |
| `agents/ui-designer.md` | 視覺設計師（正方）：設計任務動 code 前產設計規格 / 三 direction 預覽 | ✅ 推薦 |
| `agents/design-reviewer.md` | 視覺審查員（反方）：三視口截圖六維度驗收，與正方成對觸發 | ✅ 推薦 |
| `DECISION_LOG.md` | ADR 決策紀錄制度：重大技術決策當下立即記，供日後查證 | ✅ 推薦 |
| `knowledge/` | 工程知識庫（成長系統）：跨專案教訓 / 踩坑卡，agent 接任務先查、撞坑即補 | ✅ 推薦 |
| `products/INDEX.md` | 產品索引，PM 用來查對應的產品配置 | ✅ 推薦 |
| `products/example_product.md` | 範例產品配置（複製來用） | 📋 參考 |
| `hooks/slack-notify.sh` | 每次 Claude 回覆後推 Slack 通知（沒設 webhook 時自動 no-op；settings.json 的 Stop hook 指向它，故建議連同 settings.json 一起裝） | 🔔 通知選用、腳本建議裝 |
| `skills/merge-prod/` | 自動化合併正式站部署分支 | 🔧 選裝 |
| `skills/test-*-integrity/` | 訊息系統壓力測試腳本 | 🔧 選裝 |
| `skills/verify-ocr-version/` | 驗證 sidecar 部署版本 | 🔧 選裝 |
| `skills/retro/` + `scripts/retro-digest.py` | 宏觀自我複盤迴圈：任務完成主動收評分，累積 ≥8 個 verdict 提議複盤，找跨任務流程反模式、產提案由使用者圈選才改規則 | 🔧 選裝（推薦） |

## 常見問題

### Q: 我不是用 Vue + Go，這套設定能用嗎？

可以。Agent 的核心邏輯（三方案分析、規格驗收、分階段測試）跟語言無關。你只需要改 `CLAUDE.md` 裡的技術棧和 `agents/` 裡的技術相關描述。

### Q: 我沒有 Playwright MCP，PM 和 QA 還能用嗎？

可以，但功能會降級 — 它們沒辦法自動操作瀏覽器，只能跑 API 測試。建議裝 Playwright MCP：

```bash
# 在 mcp.json 裡已經設定好了，只需確保 npx 可用
npx @anthropic-ai/mcp-playwright --help
```

### Q: 我怎麼新增自己的 Skill？

在 `~/.claude/skills/` 下建一個資料夾，裡面放 `SKILL.md`（遵循 frontmatter 格式）。參考 `merge-prod/SKILL.md` 的結構。

### Q: settings.json 裡的 `skipDangerousModePermissionPrompt` 和 `skipAutoPermissionPrompt` 是什麼？

這兩個設定讓 Claude 執行工具時不用每次都問你「可以嗎？」。適合信任 Claude 的進階使用者。如果你想保守一點，把它們改成 `false`。

### Q: 看門狗（斷線自我恢復）怎麼啟用？

看門狗讓「session 被強制中斷（斷網、當機、睡眠）的任務」能被自動復活，並支援大型任務「批次=Session」的自動接續。安裝：

```bash
# 前置：需要 jq（macOS: brew install jq / Linux: apt install jq）
bash ~/.claude/scripts/install-watchdog.sh
```

安裝器會偵測平台：macOS 裝 launchd（每 600 秒喚醒）、Linux/WSL 裝 cron（每 10 分鐘）；WSL 環境另會印出 Windows 原生工作排程器的替代指令（WSL 沒開也拉得起來）。

- 運作原理與 state 檔格式見 `state/README.md`；骨架規約見 `CLAUDE.md`「檢查點與切批」節
- **權限模式**：預設全自動（`--dangerously-skip-permissions`，復活絕不卡在權限提示）——⚠️ 代價是復活的 session 在無人監督下擁有完整權限，風險說明見 README「安全警示」。要保守一點，在 `state/watchdog.conf` 改 `PERMISSION_FLAGS=""` 並搭配 `settings.json` 的 `permissions.allow` 白名單
- 驗證：手動跑一次 `bash ~/.claude/scripts/watchdog.sh`，看 `~/.claude/state/watchdog.log`

### Q: Codex 整合是什麼？我需要裝嗎？

**不需要，預設停用。** 這是選用整合：把 OpenAI 的 Codex CLI 當作「異模型第二意見」，只在重大 review、卡關 3 次、極難推理交叉比對等關鍵場景由主 Claude 呼喚一次。沒裝 Codex 的環境完全不受影響——探測腳本 `scripts/codex-probe.sh` 偵測到未安裝會直接跳過。

要啟用：

```bash
# 1. 安裝並登入 Codex CLI
brew install codex        # 或參考 OpenAI 官方安裝方式
codex login               # ChatGPT 帳號或 API key

# 2. 驗證探測腳本（exit 0 = 可用）
bash ~/.claude/scripts/codex-probe.sh

# 3. 把 CLAUDE.md「選用模組：Codex CLI」節的啟用狀態改為 enabled
```

設計上 Codex 永遠是 non-blocking：呼喚前先探測額度（額度不足直接跳過，避免跑到一半卡住）、產出只作參考不作 gate 依據、中途失敗即棄由原流程接續。完整規約見 `CLAUDE.md` 該節。
