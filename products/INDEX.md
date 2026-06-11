# 產品配置索引（PM agent 專用）

PM 接到驗收任務時，**先讀這份索引**，找到任務對應的產品，再 Read 該產品的配置檔載入詳細資訊。

## 已註冊產品

| 產品代號 | 一句話描述 | 配置檔路徑 |
|---------|-----------|----------|
| `example_product` | 範例產品（展示配置格式用） | `~/.claude/products/example_product.md` |

## 配置檔必填區塊

每份產品配置檔（`<product>.md`）必須包含：

1. **規格書與文件路徑**：列出該產品所有規格書 / CLAUDE.md / 設計文件位置
2. **測試環境**：後端 / 前端 / DB / 快取等服務的位置與 port、健康檢查指令
3. **測試帳號**：username、password、權限等級、適用情境
4. **重要規約**：API 回應格式、權限模型、業務規則等驗收時必須對照的條目
5. **截圖存放路徑**：通常是 `/tmp/pm-<product>-<feature>-<step>.png`

## 如何新增產品

1. 在 `~/.claude/products/` 建立 `<product>.md`（檔名用 snake_case）
2. 依「必填區塊」填寫
3. 在上方「已註冊產品」表新增一行
4. 不要把產品專屬內容寫進 `~/.claude/agents/pm.md`，PM agent 必須保持產品無關
