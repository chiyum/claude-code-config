---
name: test-line-message-integrity
description: 在 dev 環境模擬「客服頻繁切換多個 LINE 聊天室 + 多訪客持續發訊息」，驗證訊息不遺漏、不重複、Messages API 單調遞增。同時搭配 Playwright MCP 開一個客服瀏覽器做視覺驗證。觸發詞：「測試訊息完整性」「test line message」。
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

# LINE 訊息完整性壓力測試

## 動機

prod 反映「客服在多個 LINE 聊天室之間頻繁切換時，會發生 message API 回傳遺失」— WebSocket 即時收到訊息，但下次切換回該室時 `GET /chat-rooms/<id>/messages?limit=30&offset=0` 卻拿不到。本 skill 自動複現此情境並驗證。

## 適用環境

- **僅限 dev**（會建立測試訪客 + 大量發訊息，污染資料）
- 所有 URL / 帳密透過 CLI 參數傳入，不硬寫在腳本內

## 執行流程

### Step 0：前置檢查與參數蒐集

1. **dev health 確認**：`curl -s <your-api-url>/health`
2. **LINE channel_config**：需要 `webhook_token` 跟 `channel_secret`（從 admin API 或 DB 取得）
3. **問使用者**（必問）：LINE channel_secret 是什麼？dev 環境是否有可用的 LINE channel_config？

### Step 1：執行測試腳本

```bash
node ~/.claude/skills/test-line-message-integrity/scripts/integrity-test.mjs \
  --api=<your-api-url> \
  --site-code=<your-site-code> \
  --line-token=<webhook_token> \
  --line-secret=<channel_secret> \
  --username=<test-username> \
  --password=<test-password> \
  --duration=60 \
  --guests=3 \
  --guest-interval=500 \
  --switch-interval=300
```

### Step 2：同時用 Playwright MCP 開瀏覽器做視覺驗證

腳本跑壓測期間，主 Claude **並行**做：
1. 開 dev 後台登入
2. 進聊天首頁，過濾 LINE 渠道
3. 找剛建的測試訪客
4. 點擊每個聊天室切換 3-5 次（每次間隔 2 秒）
5. 視覺確認：訊息列表持續累積，沒有重複
6. 截圖：每次切換完截一張

### Step 3：解讀報告

報告寫到 `/tmp/line-integrity-report.json`。重點看：
- **遺失 = 0**：訪客發送的訊息全在 DB 內找得到
- **重複 = 0**：DB 內沒有同 content 重複
- **Ghost ID = 0**：API 回傳過的 message ID 最終都在 DB 找得到

## 安全提醒

- **絕對不要在 prod 跑** — 會發大量假 LINE 訊息進去
- 訪客 external_id 都帶 `U_TEST_` 前綴，方便事後清理
