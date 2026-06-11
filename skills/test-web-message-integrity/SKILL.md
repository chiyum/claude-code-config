---
name: test-web-message-integrity
description: 在 dev 環境模擬「客服頻繁切換多個 Web 訪客聊天室 + 多 Web 訪客 WebSocket 持續發訊息」，驗證訊息不遺漏、不重複、Messages API 單調遞增。同時搭配 Playwright MCP 開一個客服瀏覽器做視覺驗證。觸發詞：「測試 Web 訊息完整性」「test web message」。
user-invocable: true
allowed-tools:
  - Bash
  - Read
  - Write
  - mcp__plugin_playwright_playwright__browser_navigate
  - mcp__plugin_playwright_playwright__browser_click
  - mcp__plugin_playwright_playwright__browser_snapshot
  - mcp__plugin_playwright_playwright__browser_fill_form
  - mcp__plugin_playwright_playwright__browser_take_screenshot
  - mcp__plugin_playwright_playwright__browser_evaluate
  - mcp__plugin_playwright_playwright__browser_wait_for
  - mcp__plugin_playwright_playwright__browser_close
---

# Web 訊息完整性壓力測試

## 動機

跟 `test-line-message-integrity` 同一個 bug 場景，但訪客端走 Web WebSocket 而非 LINE webhook。Web skill 更簡單 — 不用拿 LINE secret，直接跑。

## 執行流程

### Step 0：前置檢查

`curl -s <your-api-url>/health`

### Step 1：執行測試腳本

```bash
node ~/.claude/skills/test-web-message-integrity/scripts/integrity-test.mjs \
  --api=<your-api-url> \
  --site-code=<your-site-code> \
  --username=<test-username> \
  --password=<test-password> \
  --duration=60 \
  --guests=3 \
  --guest-interval=500 \
  --switch-interval=300
```

### Step 2：同時用 Playwright MCP 開瀏覽器視覺驗證

### Step 3：解讀報告

報告寫到 `/tmp/web-integrity-report.json`。重點看：
- **遺失 = 0**、**重複 = 0**、**Ghost ID = 0**

## 安全提醒

- **絕對不要在 prod 跑**
- 訪客名稱帶 `WebIntegrity_` 前綴，方便事後清理
