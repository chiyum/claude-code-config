# 外部凍結規格協定（Claude 側執行細節）

`~/.claude/CLAUDE.md`「外部凍結規格模式」只放路由與硬護欄；本檔是完整程序。規格目錄與治理規則見 `~/.claude/specs/README.md`（若有）。原生需求模式（PM 產清單 → 使用者確認 → 凍結）**完全不變**，本協定只是新增一種步驟 0 入口。

## 1. 何時進入外部規格模式

- 使用者下 `/dev --spec <SPEC.md 絕對路徑>`、`/dev auto --spec <路徑>`
- 使用者在對話中直接給出 `~/.claude/specs/<product>/<spec_id>/v<ver>/SPEC.md` 路徑並要求開發
- 沒有給 SPEC 路徑 → 一律原生模式，不得主動把需求轉成外部 SPEC

## 2. 三方責任與硬邊界

| 誰 | 決定什麼 | 不得 |
|---|---|---|
| 使用者 | 產品決策、核准規格與 CR、確認 prod | — |
| 規格治理者 | 要完成什麼、什麼算完成（範圍、非目標、A1～An） | 用 completion report 回填 SPEC |
| Claude architect | 如何實作；repo 內技術規格 / API 文件 / ADR / 部署文件 | 改 SPEC、改驗收條件、實作非目標、追加範圍外功能 |
| Claude PM | 可測試性稽核（步驟 0）、依 SPEC 驗收（步驟 2 / 4） | 重寫 A1～An、縮小範圍、把非目標移入範圍、替使用者選衝突解法 |
| Claude reviewer / QA | 審查、測試、證據 | 自行接受規格變更 |

ADR 不能取代產品核准；completion report 不是規格來源；manifest hash 驗證失敗不得自動更新 manifest；不得自動接受較新版本。

## 3. 狀態矩陣與錯誤碼

`python3 ~/.claude/scripts/verify-external-spec.py --spec <SPEC.md> [--expected-sha256 <hash>] [--expected-product <代號>] [--mode check] [--confirm-environment prod]`

| 情況 | 錯誤碼 / exit | 行為 |
|---|---|---|
| status DRAFT | `SPEC_NOT_FROZEN` / 5 | 禁止開發；只允許 `/spec-check`（`--mode check` 可讀） |
| status FROZEN、hash 相符 | ok / 0 | 可進開發；輸出正規化 metadata（jq 合進 state） |
| manifest status SUPERSEDED | `SPEC_SUPERSEDED` / 6 | 禁止建立新 run；提醒向治理者取最新版本路徑，**不自行猜路徑** |
| 缺 SPEC | `SPEC_NOT_FOUND` / 2 | 阻擋 |
| 缺 manifest | `MANIFEST_NOT_FOUND` / 3 | 阻擋 |
| 缺欄位 / 格式錯 / SPEC 與 manifest metadata 不一致 / A 編號重複 / FROZEN 但未決問題非空 / BOM / CRLF | `SPEC_INVALID` / 4 | 阻擋，不得自動修正 |
| manifest hash ≠ 實際 bytes，或 ≠ state 綁定 hash | `SPEC_DRIFT` / 7 | 阻擋並停止（見第 7 節） |
| product 與載入產品不同、或未註冊 | `PRODUCT_MISMATCH` / 8 | 阻擋並回報差異 |
| target_environment 為 prod 且未確認 | `ENVIRONMENT_REQUIRES_CONFIRMATION` / 9 | 命中必問白名單；使用者明確確認後才加 `--confirm-environment prod` 重跑 |

stdout 一律 JSON（`ok` / `error` / `message` / `details`），stderr 一行人讀摘要。

## 4. 入口流程（步驟 0 的外部規格版）

1. Read SPEC 與同目錄 manifest.json
2. 跑驗證器（不帶 `--expected-sha256`）；非 0 → 依矩陣回報並停止
3. 載入產品上下文（CLAUDE.md session 啟動規則）；再以 `--expected-product <載入的產品>` 重跑一次確認一致
4. 確認 `target_environment`（dev 直接走；prod 必問）
5. 產生 run ID：`RUN-<YYYYMMDD>-<NNN>`，NNN 取 `~/.claude/acceptance/<spec_id>/` 下既有 run 數 + 1，三位補零
6. 建立 state（欄位見 `~/.claude/state/README.md`）：以驗證器輸出合併
   ```bash
   SLUG=<YYYYMMDD>-<簡述>; RUN=RUN-$(date +%Y%m%d)-001
   META=$(python3 ~/.claude/scripts/verify-external-spec.py --spec "$SPEC" --expected-product "$PRODUCT")
   echo "$META" | jq --arg slug "$SLUG" --arg run "$RUN" --arg sid "$CLAUDE_CODE_SESSION_ID" --arg now "$(date -Iseconds)" --argjson ts "$(date +%s)" \
     '{task:$slug, run_id:$run, session_id:$sid, sessions:[$sid], product:.product, spec_mode:"external",
       spec_id:.spec_id, spec_version:.spec_version, spec_path:.spec_path, spec_sha256:.spec_sha256, manifest_path:.manifest_path,
       target_environment:.target_environment, acceptance:.spec_path, acceptance_ids:.acceptance_ids,
       evidence_root:("'"$HOME"'/.claude/acceptance/"+.spec_id+"/"+$run),
       current_step:"0", next_action:"PM 可測試性稽核", status:"running", started_at:$now, ended_at:null, restart_count:0, updated_at:$ts}' \
     > ~/.claude/state/$SLUG.json
   mkdir -p ~/.claude/acceptance/<spec_id>/$RUN/{local,dev}
   ```
   `acceptance` 欄位指向 SPEC 路徑本身（看門狗復活提示會叫它讀「對應 acceptance 清單」）；`~/.claude/acceptance/<spec_id>/<run_id>/` 只放證據與索引，**不得複製 SPEC**
7. PM 以 **acceptance auditor** 身分稽核（第 5 節）；通過 → 直接進 architect。**不再要求使用者確認已核准的 FROZEN 規格**
8. 稽核發現矛盾或不可測 → 輸出 `SPEC_CHANGE_REQUIRED`（第 6 節），state 標 `awaiting_user`，停止

`/dev --spec` 標準模式與 auto 模式在此的差別：標準模式在 PM 稽核結果呈現時停一次（只是讓使用者看到稽核結論，不是重新確認規格）；auto 模式直接進 architect。

## 5. PM 步驟 0：acceptance auditor（不是 author）

只檢查：每條 A 是否能被客觀測試、前置條件是否完整、驗證步驟是否可執行、預期結果是否明確、A 編號是否重複、SPEC 是否自相矛盾、是否與已確認的系統現況直接衝突、所需測試帳號 / 資料是否有安全引用方式（SECRETS reference）。

輸出格式：
```
# 可測試性稽核報告
- Spec ID / Version / SHA-256：
- 結論：可進開發 / 需 Change Request
## 逐條
### A1 — 可測試 | 不可測（原因） | 自相矛盾（與 A<n> / 第 7 節）
## 需要 Change Request 的項目（無則寫無）
```
不得改寫 A1～An、不得增加產品功能、不得縮小範圍、不得把非目標移入範圍、不得替使用者選衝突解法。

## 6. SPEC_CHANGE_REQUIRED（凍結後要動規格的唯一出口）

任何 agent（architect / reviewer / QA / PM）發現需要變更時，由主 Claude 統一輸出：

```
SPEC_CHANGE_REQUIRED

Spec ID：
Version：
受影響驗收條件：

發現：
<客觀描述>

現況證據：
<repo 路徑、程式碼、API、資料模型或測試證據>

為何無法在目前約束內完成：
<必須先證明已嘗試約束內解法：控制變因反例 / 既有能力查證 / reuse 既有積木>

可選方案：
1.
2.
3.

建議方案：
<可提供技術建議，但不得自行採用>

需要產品決策：
<使用者或規格治理者必須回答的問題>
```

允許觸發的理由只有：規格自相矛盾、技術硬限制使需求客觀無法完成、需要不可逆資料變更、需要新增費用、出現資安風險、必須碰 prod、必須改變外部 API 或既有相容承諾、找不到任何約束內可行解且已有程式碼或實驗證據。輸出後：state 標 `awaiting_user`、記 `change_requests` 陣列、停止。治理者開新版本後，使用者以新路徑重新啟動 run；舊 run 不續跑。

## 7. 每個 gate 的漂移檢查

每個 gate 轉換前（進 architect、pre-review 後、reviewer 每回合前、QA 前、PM 前、push 前、部署放行前、dev QA 前、完成報告前）：

```bash
bash ~/.claude/scripts/spec-gate.sh ~/.claude/state/<slug>.json "<gate 名稱>"
```

檢查 SPEC 路徑存在、manifest 存在、SHA-256 與 state 一致、metadata 與 state 一致、版本未被替換。exit 7 = `SPEC_DRIFT`：腳本已把 state 標 `blocked_spec_drift` 並印出舊 hash / 新 hash / 路徑 / 目前步驟。此時不得繼續任何步驟、不得自行接受新版本；主 Claude 原樣回報並停止。原生模式的 state 沒有 `spec_mode: external`，腳本直接 exit 0。

## 8. 交棒內容（每個 agent prompt 必含）

共同抬頭（原樣貼給每個 agent）：
```
外部規格模式 run
- Spec ID：<spec_id>　Version：<spec_version>　SHA-256：<spec_sha256>
- SPEC 絕對路徑：<spec_path>（唯一行為依據；不得修改）
- Product：<product>　Target environment：<target_environment>　Run ID：<run_id>
- 證據根目錄：~/.claude/acceptance/<spec_id>/<run_id>/（local/ 與 dev/ 分開）
- 你的角色邊界：<見下>
```

**architect**：依 SPEC 實作；不改 SPEC；不加非範圍功能、不實作非目標；技術文件 / API 文件 / ADR 與 code 同 commit；記錄自行做的實作決策（回報「實作決策」清單）；發現規格衝突時停手輸出 `SPEC_CHANGE_REQUIRED` 素材；commit 主體繁體中文，末尾加 trailer：
```
Spec-ID: <spec_id>
Spec-Version: <spec_version>
Spec-SHA256: <spec_sha256>
Acceptance: A1,A2,A3
```

**reviewer**：逐條對 SPEC 確認實作是否符合；檢查 scope creep、是否違反非目標、是否偷偷變更外部行為、commit trailer 是否齊；不得以 architect 更新的技術規格取代凍結 SPEC；每個問題標示受影響 A 編號。

**QA**：用 SPEC 的驗證步驟與預期結果；證據落地到 `<evidence_root>/<local|dev>/`，檔名含 `A<n>-`；每個環境寫一份 `evidence-index.json`（第 9 節），綁定 spec ID / version / hash / commit / environment；不得從受測功能自己產生的資料推導期望值；本地與 dev 分開；API 成功不等於 UI 流程成功（SPEC 要求雙軌就兩者都要）。

**PM（步驟 2 / 4）**：只以 SPEC 為行為驗收依據，技術文件只作理解輔助；不把 architect 新增的行為當已核准需求；每條 A 明確輸出 PASS / FAIL / BLOCKED——PASS 必有證據、FAIL 必寫實際 vs 預期、BLOCKED 必寫阻擋原因；結果寫進同一份 `evidence-index.json`（PM 沒有 Write 工具時由主 Claude 代寫，內容須逐字取自 PM 回報）。

原生模式的 security-auditor、ui-designer × design-reviewer、反方 PM、主 Claude 抽驗截圖、3 回合上限、pre-review gate 全部照舊。

## 9. 證據目錄與 evidence-index.json

```
~/.claude/acceptance/<spec_id>/<run_id>/
├── local/
│   ├── qa-A1-api-response.json
│   ├── qa-A1-ui.png
│   └── evidence-index.json
└── dev/
    ├── qa-A1-...
    └── evidence-index.json
```

每個環境一份索引：
```json
{
  "run_id": "RUN-20260908-001",
  "spec_id": "SPC-EX-20260908-001",
  "spec_version": "1.0",
  "spec_sha256": "<與 state 相同>",
  "implementation_commit": "<受測 commit>",
  "environment": "local",
  "deployed_version": "<dev 必填：version endpoint 回的版本或 commit>",
  "acceptance": {
    "A1": {
      "status": "PASS",
      "expected_source": "SPEC.md A1",
      "expected": "...",
      "observed": "...",
      "evidence": ["qa-A1-api-response.json", "qa-A1-ui.png"]
    }
  }
}
```
`evidence` 路徑相對於該環境目錄（或 run 根目錄），必須落在本 run 內。

放行前：
```bash
bash ~/.claude/scripts/verify-evidence.sh --spec <SPEC.md> --evidence-dir ~/.claude/acceptance/<spec_id>/<run_id>/local \
  --expected-sha256 "$(jq -r .spec_sha256 ~/.claude/state/<slug>.json)" --run-id <run_id>
```
dev 換 `--evidence-dir .../dev`。腳本檢查：每條 A 至少一份非空證據；索引的 spec ID / version / hash / run ID / environment 與本 run 相符；證據檔存在、非空、在本 run 目錄內；雙軌要求兩類都有；dev 有 `deployed_version` / `deployed_commit`；每條 A 皆 PASS。SPEC 沒有 `### A<n>` 標題時，腳本改讀首欄為 AC 編號的 Markdown 表格列（`| AC01 | ... |`），SPEC 與索引兩邊的鍵都正規化成「AC＋去前導零數字」再對應，大小寫與連字號不影響比對；證據可以用檔名記號對應，也可以用索引該條 `evidence` 引用；表格式條目不做雙軌檢查（規則全文見腳本檔頭）。通過後主 Claude 仍要親自 Read 抽驗 1-2 張關鍵截圖；大改動加開反方 PM。

## 10. 完成報告

七道 gate（本地 QA、PM、本地 evidence gate、push、dev 部署確認、dev QA、dev evidence gate）全過、state 標 `done` 後：
```bash
python3 ~/.claude/scripts/new-completion-report.py --state ~/.claude/state/<slug>.json --final \
  --set reviewer_critical=0 --set reviewer_normal=2 --set reviewer_suggestion="..." --set recheck_url=... 
```
輸出 `~/.claude/specs/<product>/<spec_id>/runs/<run_id>/completion-report.md`（模板 `COMPLETION_REPORT_TEMPLATE.md`，`{{欄位}}` 由 state / 索引自動填，其餘用 `--set`）。條件不足時 `--final` 會拒絕；改不帶 `--final` 產出 `status: BLOCKED` 的 partial report，標題不得含「完成」。產生器會掃描機敏字樣，命中即拒寫。最終回報仍附 1 分鐘複驗指引、run 遙測與評分提問（原生規則）。

## 11. handoff 與切批

外部規格 run 的 `<slug>-handoff.md` 開頭必含 spec_id / spec_version / spec_sha256 / spec_path / run_id / target_environment；接續 session 第一步跑 `spec-gate.sh` 再繼續。
