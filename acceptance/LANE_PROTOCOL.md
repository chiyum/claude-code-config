# 分級開發流程（2026-09-29 試行，2026-10-28 轉正）

轉正紀錄：試行採「新流程 run 對照歷史基線」（基線凍結成 `~/.claude/run-metrics/baseline-202609.json`，欄位見 `scripts/report-runs.py` 的 `pilot_report()`；沒有基線檔時 `--pilot` 只提示讀不到基線，需先自行凍結一份），累積 105 筆後時長中位數 326→177 分、out tokens 255k→95k，2026-10-28 複盤拍板轉正。本檔仍凌駕 `CLAUDE.md` 五步驟中與之衝突的條款；五步驟正文與 `agents/*.md` 的收斂另開任務。`report-runs.py --pilot` 保留供日後對照。

## 1. 開始前定級（每個改 code 的任務）

- 使用者已指定級別 → 照用，state 寫 `lane_source: user`
- 未指定 → 主 Claude 先判一個級別，用 AskUserQuestion 一題三選項確認（推薦項排第一，每項附一句「選它之後流程會怎樣」），確認後才開工；`lane_source: user`
- 例外：使用者說「直接改」「你直接處理」且改動一句話能描述 → 直接 S 不再問；`lane_source: claude`
- 級別寫進 state 後不得自行升降級。做到一半發現判錯（例如 S 做著發現要動 migration）→ 停下問一次改級，並把 `lane_changed_from` 記進 state

| lane | 判準 | 例 |
|---|---|---|
| S | 一句話能描述 diff；不碰資料結構、權限／認證、付費、對外暴露面、prod 資料 | 改文案、移按鈕、加 log、修一個位置明確的小 bug |
| M | 多檔改動或有行為變化，但不碰 L 的五項 | 新增一個頁面功能、改排序邏輯、i18n、加 API 欄位 |
| L | 含 migration、權限／認證、付費、對外暴露面、prod 資料任一 | 新表＋GRANT、金流、開對外 port、回填線上資料 |

## 2. 各級流程

- **S**：architect 直接做（單檔且 ≤ 20 行時主 Claude 可自己改）→ build／lint 過 → commit → push → 部署後親自點一次。不開 reviewer、不開 PM、不寫凍結清單、不寫憲章；state 仍要建（含 `lane`、`estimated_minutes`）
- **M**：Explore 盤點現況（≤ 5 分鐘；理解回述加一項「現況是什麼」）→ PM 凍結清單一次 → architect → `pre-review.sh` → reviewer 一輪 → 只跑與改動相關的本機測試一次 → push → 部署 → 10 分鐘線上檢查（版本字串、healthz／readyz、真的點一次新功能）。QA／PM 本地驗證合併為一次，證據照落地
- **L**：M 全套 ＋ 任務憲章 ＋ 線上唯讀預檢（env 鍵、資料形狀、runtime 角色權限）＋ 反方 PM 一次 ＋ PM 裁決與證據封印只在收尾做一次。含 migration 加回滾測試；改 DB 存取或鎖定 SQL 加以 runtime 角色跑的 SQL 權限稽核

## 3. 全 lane 共同規則（2026-09-28 拍板，自 2026-09-29 起適用所有產品）

1. 本機測試只跑「與改動相關」的一次；不在新 sha 上重跑已通過且無關的 gate；不為「證據綁最終 sha」重跑全部
2. build 過就 push、部署；不要求 reviewer 通過才 push（M／L 的 reviewer 一輪照開，但只擋 [嚴重]）
3. 部署後 10 分鐘線上檢查取代第二輪本機驗證；只有本機測不到的東西（正式站設定、真實資料形狀、runtime 角色權限）才到線上查
4. 交棒 reviewer 時明說：只報影響正確性或凍結需求的 [嚴重]；[一般] 併入同一輪一起修；不報 [建議]。要開第二輪須使用者同意
5. PM 裁決、證據封印、逐字裁決落檔只在 L 收尾做一次，不在每個 commit 做；PM 條文以一次定稿為目標
6. 不用 load<6 當 gate 硬門檻；只擋磁碟不足與「另一個 build 進行中」
7. 跨 agent 對他人 commit 的描述，決策前先 `git show --stat` 核實
8. 知識卡：補卡前先 `rg` 同 problem-class＋tech 的既有卡，命中就併入既有卡；agent 只能標 `status: proposed`，`validated` 由使用者或線上證據才能標
9. 派出 agent 或背景長步驟（部署、e2e、切換）後，主 Claude 用 Monitor／until 迴圈自己盯產物（證據目錄、commit、log 的 PASS／FAIL 列），不只等完成通知；約 15–20 分鐘沒有新產物就用 SendMessage 問狀況；轉達裁決後要確認對方有回應；包裝腳本必須把工具的結束碼傳出來，不得恆為 0（2026-10-14 複盤拍板）
10. 對線上環境（含 dev）下任何會觸發重建、重啟、部署的指令（部署腳本、PaaS 的 `up`／改變數、`gh workflow run`、`compose up`／`restart`）之前，先做三件事：①跑 `TZ=<當地時區> date` 確認實際時段，對照產品配置的部署窗口或中斷規約，不憑對話印象判斷「現在是離峰」 ②查這個指令還會順帶觸發什麼：讀產品配置的地雷段、看腳本的 diff 或 dry-run、PaaS 改變數時加「不自動部署」旗標（如 Railway 的 `--skip-deploys`）、部署本地 HEAD 前比對 DB migration 版本、push 與部署串接要 `set -o pipefail` 並驗 `origin/main` 等於本地 HEAD ③執行後讀部署 log 結尾，確認實際落地的 SHA 與服務，不只看 version endpoint（它是瞬時值，健檢失敗自動回退後會騙人）（2026-10-28 複盤拍板：同類事故在四個不同產品各發生一次，含白天誤判為離峰重啟、改變數觸發舊碼重建、push 被拒仍觸發部署、回退後 version endpoint 誤報成功）

## 4. state 追加欄位

| 欄位 | 值 | 何時寫 |
|---|---|---|
| `lane` | S / M / L | 定級時 |
| `lane_source` | user / claude | 定級時 |
| `estimated_minutes` | 整數 | 定級時主 Claude 估「改完到上線」 |
| `gate_reruns` | 整數 | 每重跑一支已通過的 gate +1 |
| `live_regressions` | 整數 | 部署後線上檢查才發現、本機沒抓到的問題數 |
| `user_aborted` | true | 使用者中途喊停或要求換做法 |
| `lane_changed_from` | S / M / L | 中途改級時 |
| `batches` | 整數，預設 1 | 切批或多產品時每批／每產品 +1；self_verdict 的 reviewer 與 qa＋pm 額度按此倍數算 |
| `approved_extra_rounds` | 整數 | 使用者同意加開的 reviewer 回合，每同意一輪 +1 |

## 5. 收尾 self_verdict（`collect-run-metrics.py` 自動算，與使用者的 `verdict` 分欄；2026-10-28 複盤修正）

- **bad**：`user_aborted`，或 `live_regressions` ≥ 2
- **ok**：reviewer 派遣 > `batches` + `approved_extra_rounds`，或 qa＋pm 派遣超過 lane 額度 × `batches`（S 0、M 3、L 6），或 `live_regressions` = 1，或 `gate_reruns` > 0，或實際時長 > 2 × `estimated_minutes`（時長含等使用者的時間，只當提醒不判 bad）
- **good**：其餘
- 有使用者 `verdict` 的 run，報表一律以使用者為準；self_verdict 只補未評分的 run
- 收尾填 `live_regressions` 前，先對一次 handoff 裡記的「上線後才發現的缺陷」數；不一致以 handoff 為準（修正前自評與使用者評分只有 62% 一致，且幾乎都是自評偏嚴）

## 6. 試行比較與保險絲

- `report-runs.py --pilot` 對照基線：時長中位數、reviewer 派遣中位數、agent 派遣中位數、out tokens 中位數、self_verdict bad 率、live_regressions 總數，並按 lane 分列
- 保險絲：任一產品的 S run 出現 `live_regressions` ≥ 1 → 該產品的 S 一律升 M 到試行結束，記入該任務 handoff 與 `~/.claude/state/LANE_FUSES.md`
- retro 觸發改為 `retro-digest.py --due`（≥ 8 個評分、或 ≥ 10 筆 run、或距上次 14 天，任一即到期）
