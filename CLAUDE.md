# 全局開發規範

## Session 啟動：產品上下文偵測（每次 session 開始都要做）

主 Claude 預設從家目錄 `~` 啟動 session，系統只會自動載入 `~/.claude/projects/<project-key>/memory/MEMORY.md`，per-project memory 不會自動進入 context。為了避免「對話到一半才發現該專案有未載入的記憶」，遵守以下偵測流程：

### 觸發訊號

當使用者訊息（或對話歷程）出現以下任一訊號時，**立即執行「產品上下文載入」**：

1. **明確提到產品代號**：在 `~/.claude/products/INDEX.md` 註冊的任何產品代號，或常見口語別名
2. **提到該產品的 repo 路徑**：例如 `~/Documents/GitHub/<repo-name>`
3. **提到該產品的 dev / prod URL、container 名、port**
4. **使用者要求驗收 / 測試 / 修改**任何掛在某個產品下的功能

### 載入步驟

偵測到訊號後，**在開始實質作業前**主動完成這三步：

1. Read `~/.claude/products/INDEX.md`（確認產品代號對應）
2. Read `~/.claude/products/<product>.md`（載入該產品的規格書清單、測試環境、帳號、規約）
3. 若該產品有對應的 repo 級 memory，再 Read 對應的 `MEMORY.md` 與其引用的 memory 檔

### 載入後通知

載入完成後，在第一次正式回應前用一行話告知使用者：「已載入產品上下文：`<product>`（含 X 份規格、Y 份 memory）」，讓使用者知道 context 已對齊。

### 載入失敗或對不上時

- 訊號模糊（例如使用者只說「改一下那個 bug」而沒指明專案）→ **先用 AskUserQuestion 確認是哪個產品**，不要憑感覺猜
- INDEX.md 找不到對應產品 → 詢問使用者是否要新增該產品配置（不要直接動手）

## 標準開發流程（唯一一份，凌駕一切）

每一次「修改 code」的任務都必須走這個流程，主 Claude 是 orchestrator，依序交棒給對應 agent，不要自己動手寫 code。

### 流程五步驟

1. **architect 開發**
   - 主 Claude 用 `Agent tool subagent_type: "architect"`，把使用者原始需求 + 已蒐集的上下文（檔案路徑、約束、相關發現）傳給 architect
   - architect 自動判斷「直接實作模式」或「三方案分析模式」；三方案模式會停下來等使用者選方案
   - **規格書必須同步更新**：architect 實作 code 變更時，必須同時更新該產品在 `~/.claude/products/<product>.md`「規格書與文件」區塊列出的相關規格檔（新需求 → 新增章節；行為變更 → 改該章節；廢棄功能 → 刪該章節）。code + 規格更新放在**同一個 commit**，避免下一個 session 的開發者（不論人或 Claude）看不到差異
   - 若需求屬於規格未涵蓋的新功能，或產品配置內未列任何規格檔 → architect 必須主動在回報時提出「缺規格書，請使用者決定要新增哪一份」，而不是默默跳過
   - architect 完成後 commit（commit message 用繁體中文）
   - **接著呼叫 `reviewer`**
   - reviewer 有意見 → 由主 Claude 把 reviewer 的問題清單回傳給 architect，兩者直到一致（最多回合 3 次，超過要回報使用者）
   - 主 Claude 不直接改 code

2. **本地驗證：QA + PM**
   - reviewer 通過後，先在本地驗證
   - QA agent：跑本地 API + Playwright MCP 模擬使用者操作（不只 API，必要時開瀏覽器走完整使用者流程）
   - PM agent：對照規格書驗收（從 `~/.claude/products/INDEX.md` 載入對應產品配置）
   - 任一項有問題 → 回到第 1 步交給 architect 修

3. **Push 到 remote main 觸發 dev 部署**
   - 本地 QA + PM 都通過後，才能 push
   - 受影響的所有 repo 都要 push 到各自 remote main
   - push 前要先確認帳號歸屬（若有多帳號設定）
   - 跨 repo 依賴（如 shared kit → app 的 go.mod 升版）也在此步驟完成

4. **等部署完成後跑 dev 測試**
   - dev 自動部署約需 5 分鐘
   - 用 `ScheduleWakeup` 或 `Bash` 等待後，再呼叫 QA agent 對 dev 站台跑驗證
   - 同樣要 API + Playwright MCP 雙軌

5. **回報或回頭**
   - dev 測試有問題 → 回到第 1 步
   - 全部通過 → 主 Claude 回報使用者「dev 驗收完成」，**停下來等指令**（是否合 prod、是否再加功能等，由使用者決定）

### 例外（主 Claude 可直接處理，不用走 architect）

- 純讀取 / 探索程式碼（Read / Grep / Glob / Bash 查狀態）
- 寫 / 改非程式碼檔案（memory、文件、agent 設定、`~/.claude/*`）
- 使用者明確說「你直接改就好，不用呼叫 agent」

### 交棒提示

- 呼叫 architect：**不要只丟一句「改 code」**，把目標、為什麼、已知限制、相關檔案路徑一併傳入
- 呼叫 reviewer：附上 commit hash + 需求描述 + 重點審查清單
- 呼叫 QA：附上要測的功能、場景、預期結果；明確說是「本地測試」還是「dev 測試」
- 呼叫 PM：附上產品代號（PM 會自行從 INDEX.md 載入）+ 要驗收的功能

## 編碼風格

### 前端

- 使用 TypeScript 開發所有新功能
- 遵循 ESLint 配置
- 撰寫或修改程式碼時，若專案中存在 ESLint 或 Prettier 配置，必須嚴格遵循其格式規範
- 每次修改完程式碼後，必須執行 `npx eslint <修改的檔案>` 或 `yarn build` / `npm run build` 確認無 ESLint / Prettier 錯誤後才算完成。若有錯誤必須修正後再提交
- 使用 Composition API 撰寫 Vue 3 元件
- 優先使用函數式編程風格

### 後端

- 後端使用 GoLang

## 命名慣例

### 前端

- 檔案名稱按照各個專案的配置去命名，預設則按照功能使用，例如 `store/user.store.ts`
- Vue 元件使用 camelCase
- 函數和變數使用 camelCase
- 常數使用 UPPER_SNAKE_CASE

### 後端

- 檔名與變數名稱按照常用的規範處理

## 專案架構偏好

- 前端：Vue 3 + TypeScript + Vite
- 狀態管理：Pinia
- UI 框架：Quasar
- 測試：Vitest

## 語言設定

- 程式碼能加註解就加註解，詳細說明功能
- 程式碼註解使用繁體中文
- commit message 使用繁體中文
- 文件可使用繁體中文
- 註解與程式碼不需要使用 emoji

## 測試策略

- 當使用者要求測試功能時，自行判斷使用 Playwright MCP（瀏覽器操作）或 API 測試，或兩者搭配
- Playwright MCP 適合：需要操作前端 UI、驗證頁面顯示、模擬使用者互動的場景
- API 測試適合：驗證後端邏輯、資料正確性、建立/查詢/修改資料的場景
- 重點是確保功能正常運作，測試方式不限，以最有效率的方式完成驗證
- 測試後需回報測試結果，包含成功/失敗項目與截圖（如適用）

## 除錯策略

- 修復 bug 時，同一個解決方法最多嘗試 3 次
- 若 3 次後問題仍未解決，停止當前方向，重新分析根本原因，思考並改用不同的解決方案

## 程式碼設計原則

- 重複邏輯必須封裝：當同樣的邏輯會在多處使用時，抽出共用函式 / 元件 / hook 並引用，避免複製貼上
- 遵循 DI、DIP、SRP 原則撰寫程式碼，讓模組職責單一、依賴可注入、依賴抽象而非具體實作
- 以下情境可不強求 DI / DIP，務實優先：
  - 純工具函式（如 `utils.formatDate()`）等無狀態輔助函式，抽 interface 沒有意義
  - 同一個 package / module 內部的 helper，外部不會碰到
  - 小型腳本或一次性工具，全部寫在一起比硬分層更務實
  - 確定不需要測試的膠水層（如 main.go 的 wire-up code）

## 程式碼自我審查

- 撰寫完程式碼後，必須自行再 review 一次，確認程式碼能正確運行，且完整實作最初說明的所有功能
- 若發現有功能缺漏、邏輯錯誤、執行錯誤或效能瓶頸，應直接進行修正，無需等待使用者指示
- 必須持續迭代審查與修正，直到徹底完成功能需求，並確認程式碼運行正常、無錯誤、無明顯效能問題為止

## 版本控制規範

- 每次完成一個調整或修改後，都必須進行一次 git commit
- commit message 需包含當前修改的摘要，清楚描述本次變更內容
- commit 時不得包含測試的執行檔（如編譯產生的測試二進位檔案），應透過 .gitignore 或手動排除

## 跨專案操作授權

- 即使目前是在 A 專案啟動 Claude，當使用者明確要求前往 B 專案查看或修改時，可直接執行，無需再次詢問或等待使用者確認
- 使用者下達跨專案指令後，視為已授權對該目標專案的讀取與修改操作，應直接進行

## GitHub 多帳號處理（範例）

本機同時設定兩個 GitHub 帳號，透過 `~/.ssh/config` 用 host alias 區分：

| 帳號 | 用途 | SSH key | clone / remote URL |
|---|---|---|---|
| `primary-account` | 預設、個人主要帳號 | `~/.ssh/id_ed25519_primary` | `git@github.com:primary-account/<repo>.git` |
| `secondary-account` | 次要帳號 | `~/.ssh/id_ed25519_secondary` | `git@github.com-secondary:secondary-account/<repo>.git` |

**操作規則：**

- 使用者要求 push / clone / 設定 remote 到 GitHub 前，**必須先確認目標帳號**：
  - URL 已明確指定哪個帳號 → 直接照 URL 對應到正確 host
  - URL 模糊或只給 repo 名稱 → 主動詢問是哪個帳號
- 次要帳號的 remote URL 必須使用自訂的 host alias，不能用 `github.com`
- 驗證連線：`ssh -T git@github.com`（主帳號）或 `ssh -T git@github.com-secondary`（次要帳號）
- 若 push 出現 `Repository not found`，先用 `ssh -T` 確認當前 host 認證的是哪個帳號，再判斷是否 URL 寫錯
