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
- INDEX.md 找不到對應產品 → 詢問使用者是否要新增該產品配置（不要直接動手）；**若要新增，必須先問使用者「此產品是否區分 dev / prod 環境？」**（不要預設每個產品都有 dev/prod，有些只有單一線上環境＝push 即上線，有些甚至只在本機），把答案寫進該產品配置的「環境區分」區塊，並據此決定該產品是否適用五步驟中的「合 prod」階段

## 本檔 context 預算（新增制度前先判斷）

本檔每個 session 全額載入，是最貴的 context。收納規則：

- **屬性判斷為主**：「路由/護欄」（每個 session 都必須看到：觸發訊號、gate 骨架、帳號規則、必問白名單）才有資格寫進本檔；「程序細節」（執行到該步才需要：SOP 展開、格式範本、腳本參數）一律放外掛檔（skills/、acceptance/README、state/README、knowledge/、products/），本檔只留一行指標
- **設一條大小保險絲**（如 35KB，查法 `wc -c CLAUDE.md`）：逼近或超過時，新增前必先把既有程序細節搬出去騰位
- **禁止用壓縮換空間**：不得為省字把規則寫成縮寫黑話——預算管「什麼有資格常駐」，不管「字多省」；清楚略長勝過密而難懂
- **新增本檔內容前先與使用者討論**（使用者明確指示直接加者除外）。memory 同理：索引只留活躍項，收尾即歸檔

## 編排協定核心原則（凌駕於五步驟之上，先讀）

本規範採「骨架確定性、葉子按需委派」路線。五步驟骨架、所有 gate、回退條件，一律由本檔確定性控制，不交給模型自動編排。

1. **Session 基準 effort = `high`（固定）**
   - 不整段開 ultracode / xhigh 自動編排。日常主迴圈與所有 subagent 都跑 `high`。
   - `ultracode` 是 session 限定、不可寫進任何持久設定檔（寫了不生效）。

2. **火力靠「加人手」而非「加單人腦力」**
   - 重活（大改、三方案、對抗式 review）由 orchestrator 單點展開 **Dynamic Workflow**，以多個平行 agent（每隻仍 `high`）分工，而非把單一 agent 拉到 xhigh。

3. **例外：極難單線推理可「單葉」升 xhigh**
   - 當某任務屬「極難的單線推理」（複雜演算法、深層 race condition、跨多步且極易一步想錯的推導），orchestrator 可把**那一隻** architect / reviewer 葉子透過 workflow 的 `opts.effort:'xhigh'` 單獨拉高。
   - 這是**單葉**升級，不是整段 session 開 xhigh；且**必須先向使用者宣告理由**再展開。
   - 判準：問「這題是靠更深的單線思考才解得開，還是靠更多平行視角？」——前者才升 xhigh，後者用平行 workflow。

4. **Workflow 觸發權只在 orchestrator 層**
   - 是否把某階段升級為 workflow，**只由主 Claude（orchestrator）判斷**。
   - subagent（architect / reviewer / qa / pm）**一律不得自行展開 workflow**。

5. **護欄 A — 巢狀迴圈邊界**
   - workflow 內部可自行迭代收斂；但 architect ↔ reviewer 的**外層 3 回合上限**、以及各 gate 的 pass/fail 判定，一律由骨架決定。
   - 模型**不得**自行判斷「已足夠」而跳過 gate，也不得自行加碼重試回合。

6. **護欄 B — one-agent-one-partition**
   - 任何平行 agent 一律**唯讀且維度互斥**；禁止多個平行 worker 寫入同一份共享結論。
   - 只允許最後**單一 convergence step** 由一個 agent 匯總。此規則等同把 `one-field-one-semantic` 延伸到多 agent 情境。

## 標準開發流程（唯一一份，凌駕一切）

每一次「修改 code」的任務都必須走這個流程，主 Claude 是 orchestrator，依序交棒給對應 agent，不要自己動手寫 code。

> **入口規則**：使用者輸入 `/dev` 當然觸發 dev skill；使用者用**自然語言授權自主開發**（「自主開發」「不用問做完再回報」「整個流程跑完」等語意）時，主 Claude 必須**主動 invoke dev skill（等同 /dev auto）**再開始，不得只憑記憶照本節執行——skill 內含檢查點、憲章、切批等本節未展開的細節。日常明確指示的單點修改（「幫我修這個 bug」無自主授權語意）照本節流程走即可，不強制過 skill。

### 流程五步驟

0. **驗收條件凍結（開發前）**
   - 主 Claude 把使用者的【原始需求文字】（非轉譯、非摘要）交給 PM，產出三段式驗收清單（`### A<n> 行為`＋`驗證步驟`＋`預期結果`；格式、例句與規模比例原則見 `~/.claude/acceptance/README.md`）；PM 沒有寫檔工具，由主 Claude 寫入 `~/.claude/acceptance/<YYYYMMDD>-<任務簡述>.md`
   - 呈現給使用者確認後凍結，開發期間任何 agent 不得修改。使用者明示跳過、或屬例外情形（純讀取、非 code 修改）可略過；自主完成模式下凍結後直接往下走、最後一次性回報（清單仍要寫檔留存）
   - **大型 / 自主任務加凍結「任務憲章」**（與清單同檔，格式見 `acceptance/README.md`）：範圍、非目標、預授權決策表、必問白名單。憲章凍結後 agent 想提問先對照憲章：能自答就自答並記入決策紀錄；**只有命中白名單（不可逆刪資料 / 花錢 / 資安 / 碰 prod / 需求自相矛盾）才准中斷**；其餘疑問寫 `~/.claude/state/<task>-questions.md` 批次結束一併呈報。日常小任務不強制憲章，各處「模糊先問」條款照舊

1. **architect 開發**
   - 主 Claude 用 `Agent tool subagent_type: "architect"`，把使用者原始需求 + 已蒐集的上下文（檔案路徑、約束、相關發現）傳給 architect
   - architect 自動判斷「直接實作模式」或「三方案分析模式」；三方案模式會停下來等使用者選方案
     - **自主模式例外**（/dev、使用者授權「不用問做完再回報」）: 主 Claude 直接採納 architect 的推薦方案，理由記入最終回報「我幫你做的決定」清單；屬 ADR 門檻照常寫 ADR，不停等使用者
   - **規格書必須同步更新**：architect 實作 code 變更時，必須同時更新該產品在 `~/.claude/products/<product>.md`「規格書與文件」區塊列出的相關規格檔（新需求 → 新增章節；行為變更 → 改該章節；廢棄功能 → 刪該章節）。code + 規格更新放在**同一個 commit**，避免下一個 session 的開發者（不論人或 Claude）看不到差異
   - 若需求屬於規格未涵蓋的新功能，或產品配置內未列任何規格檔 → architect 必須主動在回報時提出「缺規格書，請使用者決定要新增哪一份」，而不是默默跳過
   - **重大技術決策立即記 ADR**：當這次工作包含值得記錄的決策（語言/框架/函式庫選型、重大架構模式、資料庫/儲存結構性決定、重大取捨、回滾成本高/不可逆、推翻先前決策）時，architect 在該 repo `docs/adr/` 寫一筆 ADR（範本與觸發門檻見 `~/.claude/DECISION_LOG.md`）並更新 `docs/adr/README.md`，與 code + 規格放**同一個 commit**。一般 bug 修復 / 小重構 / 照既有規格實作不需寫
   - **先查工程知識庫、撞到坑就立即補卡**：architect / reviewer / qa 接到工作先 Read `~/.claude/knowledge/INDEX.md`，**優先讀命中技術域的 playbook**（`knowledge/playbooks/`：把該技術域所有事故卡蒸餾成的設計框架與檢查清單，一次拿到整套），需要事故細節再深入個別知識卡，避免重踩前人踩過的坑；工作中撞到非顯而易見的技術坑或確立有效模式，architect 當下在 `~/.claude/knowledge/` 補一張卡 + 回 INDEX 補列，與 code 同 commit（制度見 `knowledge/INDEX.md` 開頭）
   - architect 完成後 commit（commit message 用繁體中文）
   - **commit 後、reviewer 前先跑確定性預檢**：於目標產品 repo 根目錄執行 `bash ~/.claude/scripts/pre-review.sh`
     - 未通過 → 將腳本輸出原樣附給 architect 修正後重跑，此往返【不計入】reviewer 3 回合上限
     - 通過 → 進入 reviewer 審查
   - reviewer 分工原則: 腳本已涵蓋的規則性問題（lint、go vet、Redis 寫入 TTL 配對等）reviewer 不需重複逐項檢查，應專注於機器無法判定的問題：欄位語義是否被多功能共用、跨 instance 行為是否成立、快取失效策略是否完整、async 邊界後的狀態假設是否仍有效等
   - **接著呼叫 `reviewer`**
   - reviewer 有意見 → 由主 Claude 把 reviewer 的問題清單回傳給 architect，兩者直到一致（最多回合 3 次，超過要回報使用者；**自主模式**下超限改為該項凍結記入 blockers、繼續其餘工作、最終回報一併列出）
   - **設計鏈成對觸發（正方 ui-designer × 反方 design-reviewer）**：任務含設計 / 切版 / 視覺意圖、或要「從零長出全新頁面」時，先由主 Claude 呼叫 `ui-designer` 產出設計規格（新視覺 / 風格重定義先出三 direction 靜態預覽給使用者挑；全新頁面自動走精簡規格模式）→ architect 照規格實作 → reviewer 通過後呼叫 `design-reviewer` 以該規格做三視口截圖驗收（構圖 / 間距 / 字體 / 色彩 / 動效 / 三態），退修回 architect，上限 3 回合（與 reviewer 回合分開計）。**沒開正方就不開反方**——既有版型微調、純邏輯 / 後端不觸發，避免流程變重
   - 主 Claude 不直接改 code

2. **本地驗證：QA + PM**
   - reviewer 通過後，先在本地驗證
   - QA agent：跑本地 API + Playwright MCP 模擬使用者操作（不只 API，必要時開瀏覽器走完整使用者流程）
   - PM agent：對照規格書驗收（從 `~/.claude/products/INDEX.md` 載入對應產品配置）
     - PM 驗收一律以 `~/.claude/acceptance/` 中本任務的凍結清單為唯一依據；architect 更新的規格書僅供參考，不得作為驗收判定標準
   - **證據落地 gate（反假驗收三層，2026-07 起）**：
     1. QA/PM 每驗一條 `A<n>` 必須落地證據檔到 `~/.claude/acceptance/<任務>/evidence/`（檔名含 `A<n>-`）。主 Claude 放行前執行 `bash ~/.claude/scripts/verify-evidence.sh <清單檔>`，任一條零證據 → 不放行，退回補驗
     2. 腳本通過後，主 Claude **親自 Read 抽驗 1-2 張關鍵截圖**，核對畫面內容真的等於條目宣稱；抽驗不符 → 該 agent 的整份驗收報告降級為不可信，全部重驗
     3. 大改動（architect triage 為「大」）加開**反方 PM**：一隻獨立 agent 以「證明功能沒完成」為目標，專挑清單條目的反例（換帳號、換租戶、重整頁面、斷線重連）；反方找不到反例才算真通過
   - 任一項有問題 → 回到第 1 步交給 architect 修

3. **Push 到 remote main 觸發 dev 部署**
   - 本地 QA + PM 都通過後，才能 push
   - 受影響的所有 repo 都要 push 到各自 remote main
   - push 前先讀 `~/.claude/products/<product>.md` 的「git 帳號歸屬」欄位照著做；**缺此欄才問使用者一次，問完立刻把答案寫回產品配置**，之後同產品不再問
   - 跨 repo 依賴（如 shared kit → app 的 go.mod 升版）也在此步驟完成

4. **確認部署完成後，QA 對 dev 站台驗證**
   - 讀取 `~/.claude/products/<product>.md` 的「部署驗證」章節：
     - 若 `enabled: true` → 執行 `bash ~/.claude/scripts/verify-deploy.sh <version_url> $(git rev-parse HEAD) <timeout> <interval> <jq_path>`（多 repo 產品的 commit 取「擁有該 version endpoint 的 repo」的 HEAD）
       - exit 0（新版本已上線）→ 放行 QA 測試
       - exit 1（超時）→ 這是【部署問題】而非測試失敗：不退回 architect、不計入重試，直接回報使用者檢查部署狀態
     - 若章節不存在或 `enabled: false` → 沿用原行為：用 `ScheduleWakeup` 或 `Bash` 等待約 5 分鐘後再呼叫 QA
   - 放行後呼叫 QA agent 對 dev 站台跑驗證，同樣要 API + Playwright MCP 雙軌
   - dev 驗證同樣適用步驟 2 的證據落地 gate（verify-evidence + 抽驗）
   - **前後端部署面注意**：verify-deploy 只驗 version endpoint 所屬 repo（通常是 API）；前端靜態 bundle 可能較晚上線。有前端改動時，QA 須另確認前端版本字串（如 systemVersion）已更新，避免「API 新了但使用者看到舊 UI」被誤判為功能沒完成

5. **回報或回頭**
   - dev 測試有問題 → 回到第 1 步
   - 全部通過 → 主 Claude 回報使用者「dev 驗收完成」，**停下來等指令**（是否合 prod、是否再加功能等，由使用者決定）
   - **回報必附「1 分鐘複驗指引」**：確切 URL + 帳號 + 3 步以內操作 + 應看到什麼（直接從凍結清單的驗證步驟摘出最關鍵 1-2 條）。使用者照著走走不通 = 流程缺陷，立即回到第 1 步，不得歸因於使用者操作

### 檢查點與切批（斷線自我恢復；細節見 `~/.claude/state/README.md` 與 dev skill）

- 任何走五步驟的任務必維護檢查點檔 `~/.claude/state/<任務slug>.json`：步驟 0 凍結後建立，**每個 gate 轉換（步驟切換、reviewer 回合結束、push、部署放行、批次結束）必更新**；等使用者輸入標 `awaiting_user`、完成標 `done`——這是看門狗斷線復活與跨 session 接續的生命線，不可省略
- 大改可分解為多批、或預估單一 session context 撐不完 → 步驟 0 就切批寫進驗收清單；每批結束寫交接檔 `~/.claude/state/<task>-handoff.md` 並標 `awaiting_next_batch`；大型任務中主 Claude 只當 orchestrator，不親自 Read 大檔原始碼、重活一律委派 agent
- 看門狗（`scripts/watchdog.sh`，launchd / cron 每 10 分鐘）自動復活中斷任務與接續下一批，主 Claude 無需操作

### 例外（主 Claude 可直接處理，不用走 architect）

- 純讀取 / 探索程式碼（Read / Grep / Glob / Bash 查狀態）
- 寫 / 改非程式碼檔案（memory、文件、agent 設定、`~/.claude/*`）
- 使用者明確說「你直接改就好，不用呼叫 agent」

### 交棒提示

- 呼叫 architect：**不要只丟一句「改 code」**，把目標、為什麼、已知限制、相關檔案路徑一併傳入
- 呼叫 reviewer：附上 commit hash + 需求描述 + 重點審查清單
- 呼叫 QA：附上要測的功能、場景、預期結果；明確說是「本地測試」還是「dev 測試」
- 呼叫 PM：附上產品代號（PM 會自行從 INDEX.md 載入）+ 要驗收的功能
- 呼叫 ui-designer：附上任務目標、產品代號、使用者選定的 DESIGN.md（或說明無）、範圍（哪幾頁）；是否需要三 direction 由其自行判斷
- 呼叫 design-reviewer：附上頁面 URL / 本地啟動方式、本次改動範圍、產品代號、設計基準來源（有 ui-designer 規格檔時優先附它）；第 2 輪起附上前一輪退修清單供複驗

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

## 選用模組：Codex CLI 異模型第二意見（預設停用）

> **啟用狀態：`disabled`（預設）。** 本節是選用整合——不是每個人都用 Codex。未安裝 Codex 或不想用者，整節可忽略或刪除，五步驟流程完全不受影響。要啟用：安裝 Codex CLI（`brew install codex`）並登入後，把本行改為 `enabled`。
>
> **原版搭配說明（memory 模式）**：本範本的原始（私人）配置把這類工具的「操作細節」放在 Claude Code 的 auto-memory（`MEMORY.md` 索引＋個別記憶檔），CLAUDE.md 只留護欄與一行指標，以節省每個 session 的常駐 context。公開範本不含 memory 目錄，因此本節保留全文自包含；導入本範本後若你也建立了 memory 制度，建議比照「護欄常駐、細節下放 memory」收納。

Codex（OpenAI 的 coding agent CLI）可作為**選用**的異模型第二意見來源。同模型的 reviewer 有系統性盲點，異模型視角在關鍵時刻價值高；但額度有限，呼喚頻率要低，且**絕不能讓流程依賴他**。

- **只在四種場景考慮呼喚**：①重大改動（架構級/資安/prod hotfix）過自家 reviewer 後的異模型加掃 ②同一 bug 卡關 3 次後的破局第二腦 ③極難單線推理的獨立解交叉比對 ④OpenAI 生態系問題。日常 bug fix / 照規格實作 / 讀 code 一律不用。
- **呼喚權只在主 Claude（orchestrator）**，subagent 不得自行呼喚（同 workflow 觸發權規則）。
- **呼喚前必跑額度探測**：`bash ~/.claude/scripts/codex-probe.sh`——極小探測呼叫（輸出約 5 tokens），exit 0 才可用；非 0（2=未安裝 / 3=未登入 / 4=額度不足 / 5=逾時或未知錯誤）→ 這次不用 Codex，直接走原流程，不重試不等待。這一步把「跑到一半沒額度卡住」擋在正式任務之前。
- **non-blocking 鐵則**：Codex 產出永遠只是參考意見，不得作為任何 gate 的放行依據、不得讓流程等他。正式呼喚用 `codex exec`（非互動）包 timeout；中途額度斷掉或失敗 → 棄用該輪輸出，自家 agent 照五步驟原流程無縫接續，當作從沒問過。
- **省額度紀律**：丟給他的必須是收斂好的問題（症狀 + 已排除假設 + 相關檔案片段），不丟整個 repo 讓他自己逛。

## GitHub 多帳號處理（範例）

本機同時設定兩個 GitHub 帳號，透過 `~/.ssh/config` 用 host alias 區分：

| 帳號 | 用途 | SSH key | clone / remote URL |
|---|---|---|---|
| `primary-account` | 預設、個人主要帳號 | `~/.ssh/id_ed25519_primary` | `git@github.com:primary-account/<repo>.git` |
| `secondary-account` | 次要帳號 | `~/.ssh/id_ed25519_secondary` | `git@github.com-secondary:secondary-account/<repo>.git` |

**操作規則：**

- 使用者要求 push / clone / 設定 remote 到 GitHub 前，**必須先確認目標帳號**：
  - 產品配置 `~/.claude/products/<product>.md` 已有「git 帳號歸屬」欄 → 直接照欄位做，不再問
  - URL 已明確指定哪個帳號 → 直接照 URL 對應到正確 host
  - URL 模糊或只給 repo 名稱 → 主動詢問是哪個帳號；屬某產品的 repo 則把答案寫回該產品配置的「git 帳號歸屬」欄，之後不再問
- 次要帳號的 remote URL 必須使用自訂的 host alias，不能用 `github.com`
- 驗證連線：`ssh -T git@github.com`（主帳號）或 `ssh -T git@github.com-secondary`（次要帳號）
- 若 push 出現 `Repository not found`，先用 `ssh -T` 確認當前 host 認證的是哪個帳號，再判斷是否 URL 寫錯
