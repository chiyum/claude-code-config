# 工作流程圖

這張圖是 [`CLAUDE.md`](CLAUDE.md) 裡「編排協定 + 標準開發流程（步驟 0~5）」的視覺化版本，方便一眼看懂主 Claude（orchestrator）如何從 session 啟動、任務分流、驗收凍結、pre-review 預檢、五步驟開發、事件驅動部署驗證到火力配置與收尾。內容以 `CLAUDE.md` 為準；兩者若有出入，一律以 `CLAUDE.md` 文字規範為單一真相。

```mermaid
flowchart TD
    Start(["Session 啟動｜基準 effort = high（固定，不整段開 ultracode/xhigh）"]) --> Ctx["產品上下文偵測<br/>觸發訊號 → INDEX.md → &lt;product&gt;.md → MEMORY.md → 一行通知已對齊"]
    Ctx --> Type{"任務類型?"}
    Type -->|"純讀取 / 改非 code 檔 / 使用者說直接改"| Direct["主 Claude 直接處理，不走 architect"]
    Type -->|"修改 code"| S0

    subgraph Flow["標準開發流程（骨架確定性；gate 與 3 回合上限不交給模型）"]
      direction TB
      S0["⓪ 驗收條件凍結（開發前）<br/>PM 依【原始需求】產出可客觀驗證清單 → 主 Claude 寫入 acceptance/ → 使用者確認後凍結（開發期間不得改）"]
      S0 --> S1["① architect（重活階段★）<br/>查 knowledge/INDEX → 實作＋同步改規格 → 重大決策寫 ADR → 撞坑補知識卡 → commit 繁中"]
      S1 --> PR["pre-review.sh 確定性預檢<br/>lint / go vet / Redis TTL 配對掃描（於產品 repo 根目錄）"]
      PR --> PROK{"通過?"}
      PROK -->|"否（附輸出給 architect 修，【不計入】reviewer 3 回合）"| S1
      PROK -->|是| Rev["reviewer 審查（重活階段★）<br/>專注機器判不了的：欄位語義共用 / cache 失效 / race / 跨 instance"]
      Rev --> RevOK{"通過?"}
      RevOK -->|"否（來回 ≤ 3 回合，護欄 A）"| S1
      RevOK -->|"超過 3 回合"| Report["回報使用者裁決"]
      RevOK -->|是| S2["② 本地驗證<br/>QA：API＋Playwright｜PM：對照 acceptance/ 凍結清單（規格書僅參考）"]
      S2 --> L{"通過?"}
      L -->|"任一失敗"| S1
      L -->|是| S3["③ push 各 repo remote main<br/>先確認帳號歸屬 ＋ 處理跨 repo 依賴（go.mod 升版）"]
      S3 --> S4["④ 確認部署完成：讀產品「部署驗證」章節"]
      S4 --> Dep{"enabled?"}
      Dep -->|"true"| VD["verify-deploy.sh 輪詢 version endpoint<br/>比對 push 的 commit"]
      Dep -->|"false / 無章節"| WAIT["沿用固定等待 ~5min<br/>（ScheduleWakeup/Bash）"]
      VD --> VDR{"新版本上線?"}
      VDR -->|"exit 1 超時＝【部署問題】不退回 architect、不計入重試"| Report
      VDR -->|"exit 0"| DevQA["dev QA：API＋Playwright 雙軌"]
      WAIT --> DevQA
      DevQA --> Dg{"通過?"}
      Dg -->|否| S1
      Dg -->|是| S5["⑤ 回報「dev 驗收完成」，停下等指令（合 prod / 加功能由使用者決定）"]
    end

    subgraph Gov["★ 重活階段的火力配置 — 凌駕五步驟的核心原則，只有 orchestrator 能決定"]
      direction TB
      Q{"這題靠更多平行視角，<br/>還是更深單線思考?"}
      Q -->|"小改 · 單線好解"| M1["單 agent（high）直接做<br/>（不觸發 workflow）"]
      Q -->|"多視角：大改 / 三方案 / 多維審查"| M2["展開 Dynamic Workflow：多個平行 agent（每隻仍 high）<br/>對抗式互驗｜唯讀＋維度互斥＋單一 convergence step（護欄 B）"]
      Q -->|"極難單線推理：複雜演算法 / 深層 race / 極易一步錯"| M3["單葉升 xhigh（opts.effort=xhigh）<br/>只拉高那一隻，須先向使用者宣告理由"]
    end

    S1 -.套用火力配置.-> Q
    Rev -.套用火力配置.-> Q

    Direct --> Hook
    S5 --> Hook
    Report --> Hook
    Hook["Stop Hook：slack-notify.sh → 每次回覆推播到 Slack"]

    Skill["Skill（自然語言觸發）<br/>/merge-prod · 訊息完整性壓測 · verify-ocr-version"] -.可被呼叫.-> Flow
```
