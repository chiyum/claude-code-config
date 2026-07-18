# 工作流程圖

這張圖是 [`CLAUDE.md`](CLAUDE.md) 裡「編排協定 + 標準開發流程（步驟 0~5）」的視覺化版本，方便一眼看懂主 Claude（orchestrator）如何從 session 啟動、任務分流、驗收凍結、pre-review 預檢、五步驟開發、事件驅動部署驗證到火力配置與收尾。內容以 `CLAUDE.md` 為準；兩者若有出入，一律以 `CLAUDE.md` 文字規範為單一真相。

> 選用模組不入圖：**Codex 異模型第二意見**（預設停用）屬骨架外的參考意見來源，呼喚前跑 `codex-probe.sh` 探測、失敗即棄不影響任何 gate，見 `CLAUDE.md`「選用模組：Codex CLI」節。

```mermaid
flowchart TD
    Start(["Session 啟動｜基準 effort = high（固定，不整段開 ultracode/xhigh）"]) --> Ctx["產品上下文偵測<br/>觸發訊號 → INDEX.md → &lt;product&gt;.md → MEMORY.md → 一行通知已對齊"]
    Ctx --> Type{"任務類型?"}
    Type -->|"純讀取 / 改非 code 檔 / 使用者說直接改"| Direct["主 Claude 直接處理，不走 architect"]
    Type -->|"/dev 或自然語言授權自主開發"| Dev["/dev skill 入口<br/>標準 / auto（零停頓）/ 繼續（接續中斷或下一批）<br/>建檢查點檔 state/&lt;slug&gt;.json"]
    Type -->|"修改 code（單點指示）"| S0
    Dev --> S0

    subgraph Flow["標準開發流程（骨架確定性；gate 與 3 回合上限不交給模型；每個 gate 轉換更新檢查點）"]
      direction TB
      S0["⓪ 驗收條件凍結（開發前）<br/>PM 依【原始需求】產出三段式清單（A&lt;n&gt; 行為＋驗證步驟＋預期結果，驗法凍結定案）<br/>大型/自主任務加任務憲章（預授權決策＋必問白名單）→ 主 Claude 寫入 acceptance/ → 使用者確認後凍結"]
      S0 --> UDQ{"設計意圖 / 全新頁面?"}
      UDQ -->|"是"| UD["ui-designer（正方）產設計規格<br/>新視覺先出三 direction 預覽供挑選"]
      UDQ -->|"否"| S1
      UD --> S1["① architect（重活階段★）<br/>先讀 playbook 再深入知識卡 → 實作＋同步改規格 → 重大決策寫 ADR → 撞坑補卡＋連動 playbook → commit 繁中<br/>碰牆先約束內解：提「放寬/改門檻/重寫」必先附舉證，否則命中必問白名單"]
      S1 --> PR["pre-review.sh 確定性預檢<br/>lint / go vet / Redis TTL 配對掃描（於產品 repo 根目錄）"]
      PR --> PROK{"通過?"}
      PROK -->|"否（附輸出給 architect 修，【不計入】reviewer 3 回合）"| S1
      PROK -->|是| Rev["reviewer 審查（重活階段★）<br/>專注機器判不了的：欄位語義共用 / cache 失效 / race / 跨 instance"]
      Rev --> RevOK{"通過?"}
      RevOK -->|"否（來回 ≤ 3 回合，護欄 A）"| S1
      RevOK -->|"超過 3 回合（自主模式：凍結記 blockers 續跑）"| Report["回報使用者裁決"]
      RevOK -->|是| DG{"開過 ui-designer?"}
      DG -->|"是"| DR["design-reviewer 視覺 gate（反方）<br/>三視口截圖 × 六維度，以設計規格為基準（≤3 回合）"]
      DR -->|"退修"| S1
      DG -->|"否（沒開正方不開反方）"| S2
      DR -->|"PASS"| S2["② 本地驗證＋反假驗收三層 gate<br/>QA/PM 逐條落地證據 evidence/ → verify-evidence.sh 確定性檢查<br/>→ 主 Claude 抽驗截圖 → 大改動加開反方 PM 找反例"]
      S2 --> L{"通過?"}
      L -->|"任一失敗"| S1
      L -->|是| S3["③ push 各 repo remote main<br/>讀產品配置「git 帳號歸屬」欄（缺欄問一次即回寫）＋ 處理跨 repo 依賴（go.mod 升版）"]
      S3 --> S4["④ 確認部署完成：讀產品「部署驗證」章節"]
      S4 --> Dep{"enabled?"}
      Dep -->|"true"| VD["verify-deploy.sh 輪詢 version endpoint<br/>比對 push 的 commit"]
      Dep -->|"false / 無章節"| WAIT["沿用固定等待 ~5min<br/>（ScheduleWakeup/Bash）"]
      VD --> VDR{"新版本上線?"}
      VDR -->|"exit 1 超時＝【部署問題】不退回 architect、不計入重試"| Report
      VDR -->|"exit 0"| DevQA["dev QA：API＋Playwright 雙軌<br/>同樣適用證據落地 gate；前端改動另驗前端版本字串（bundle 可能較晚上線）"]
      WAIT --> DevQA
      DevQA --> Dg{"通過?"}
      Dg -->|否| S1
      Dg -->|是| S5["⑤ 回報「dev 驗收完成」＋ 1 分鐘複驗指引（URL＋帳號＋≤3 步＋應看到什麼）<br/>主動問任務評分（①順暢②還行③卡點）→ rate-run 寫 verdict，問了不追<br/>verdict 累積 ≥8 順口問「要不要 /retro 複盤」（絕不自動觸發）<br/>停下等指令（合 prod / 加功能由使用者決定）"]
    end

    subgraph Resilience["檢查點與看門狗（斷線自我恢復）＋ 批次=Session"]
      direction TB
      SC["state/&lt;slug&gt;.json 檢查點<br/>每個 gate 轉換更新 current_step / next_action / 心跳"]
      WD["watchdog.sh（launchd / cron 每 10 分鐘）<br/>running 心跳逾期且 transcript 沒動 → claude --resume 復活（上限 3 次）<br/>awaiting_next_batch → 開新 session「/dev 繼續」｜awaiting_user 不動"]
      BATCH["大型任務切批：每批結束寫 handoff.md → 標 awaiting_next_batch → 新 session 乾淨 context 接續"]
      SC -.監控.-> WD
      WD -.拉起.-> BATCH
    end

    Flow -.寫檢查點.-> SC

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
