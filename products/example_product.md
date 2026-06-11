# 產品配置：範例產品（example_product）

> 這是一份範例產品配置檔，展示所需的格式與區塊。請複製此檔並依照你的產品填寫。

由 N 個 repo 組成的系統：

| Repo | 角色 | 路徑 |
|------|------|------|
| `backend-service` | 後端 API（Go + Gin + WebSocket） | `<your-path>/backend-service` |
| `admin-frontend` | 後台管理前端（Vue 3 + Vite） | `<your-path>/admin-frontend` |
| `client-frontend` | 客戶端前端（Vue 3 + Vite） | `<your-path>/client-frontend` |

## 規格書與文件（驗收前一定先讀；架構師改 code 必同步更新）

> ⚠️ **規格同步原則（給 architect / 主 Claude）**：任何需求變更、行為調整、API / DB / WebSocket / cache 規約異動，**必須在改 code 的同一個 commit 內，同步更新下表對應的規格檔**。新功能找不到對應章節 → 新增章節；行為改動 → 改對應章節；廢棄功能 → 刪該章節。

| 路徑 | 內容 |
|------|------|
| `<your-path>/backend-service/README.md` | 後端架構、API、WebSocket、ENV 對照表 |
| `<your-path>/admin-frontend/docs/spec.md` | 後台功能規格書 |
| `<your-path>/admin-frontend/docs/user-guide.md` | 後台使用手冊 |

讀完規格才開始操作。如果規格與要驗證的功能對不上，先回報「規格不明確」而不是自己腦補。

## 測試環境

### 本地環境

| 元件 | 啟動方式 | Port | Container / Host |
|------|---------|------|------------------|
| 後端 | `cd backend-service && make docker-up && make run` | 8080 | host：本機 Go |
| PostgreSQL | `make docker-up`（起 infra） | 5432 | container `app_postgres` |
| Redis | `make docker-up` | 6379 | container `app_redis` |
| 後台前端 | `cd admin-frontend && yarn dev` | 9527 | host：Vite |
| 客戶端前端 | `cd client-frontend && yarn dev` | 8082 | host：Vite |

健康檢查：
- 後端：`curl http://localhost:8080/health`
- WebSocket：`ws://localhost:8080/api/v1/ws/<path>`

### 線上 dev 環境

| 項目 | 值 |
|------|---|
| 後台入口 | `https://admin.your-dev-domain.com` |
| API base | `https://api.your-dev-domain.com` |
| WebSocket | `wss://api.your-dev-domain.com` |
| 部署方式 | push `main` → 等約 5 分鐘自動部署 |

## 測試帳號

| 帳號 | 密碼 | 權限等級 | 適用情境 |
|------|------|---------|---------|
| `admin` | `<your-password>` | 管理者 | 完整功能測試 |
| `agent01` | `<your-password>` | 一般操作員 | 權限限制測試 |

## 重要規約（驗收時一定要對照）

1. **API 回應格式**：所有業務 API 一律 HTTP 200，body `{ success, code, message, data }`；`code=1` 成功，`code<0` 業務錯誤
2. **權限模型**：Admin / Agent 角色之分，跨租戶隔離
3. **WebSocket 規約**：訊息格式、心跳、重連策略
4. **Cache 策略**：Redis-First 混合儲存（熱資料 N 條 + DB 全量）

## 截圖存放路徑

`/tmp/pm-example_product-<feature>-<step>.png`
