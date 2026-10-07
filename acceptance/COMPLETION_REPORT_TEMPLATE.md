---
report_type: completion
status: {{status}}
spec_id: {{spec_id}}
spec_version: {{spec_version}}
spec_sha256: {{spec_sha256}}
run_id: {{run_id}}
generated_at: {{generated_at}}
---

# {{title}}

> 本報告供外部規格治理者稽核，不是規格來源；行為真相仍以 `{{spec_path}}` 為準。
> status 為 BLOCKED 時本報告為 partial report，任何欄位不得寫「完成」。

## 規格識別
- Spec ID：{{spec_id}}
- Version：{{spec_version}}
- SHA-256：{{spec_sha256}}
- Product：{{product}}
- Run ID：{{run_id}}
- Target environment：{{target_environment}}

## 實作資訊
- Repo：{{repo}}
- Branch：{{branch}}
- Commit：{{commit}}
- 影響檔案：{{changed_files}}
- migration：{{migration}}
- 設定變更：{{config_changes}}
- ADR：{{adr}}

## 驗收結果

| AC | 本地 | dev | 證據 |
|---|---|---|---|
{{acceptance_rows}}

## Reviewer 結果
- 嚴重：{{reviewer_critical}}
- 一般：{{reviewer_normal}}
- 建議：{{reviewer_suggestion}}
- 回合數：{{reviewer_rounds}}

## 規格符合度
- 是否完整完成：{{spec_complete}}
- 是否有範圍外變更：{{scope_creep}}
- 是否觸及非目標：{{non_goal_touched}}
- 是否發生 Change Request：{{change_request}}
- 是否發生 Spec Drift：{{spec_drift}}

## 技術決策
- architect 自行決定的內容：{{architect_decisions}}
- ADR 路徑：{{adr}}

## 部署確認
- backend commit/version：{{deploy_backend}}
- frontend version：{{deploy_frontend}}
- version endpoint：{{version_endpoint}}
- log 結尾結果：{{deploy_log_tail}}
- 是否發生自動回退：{{deploy_rollback}}

## 已知但不阻擋的事項
- reviewer 建議：{{reviewer_suggestion}}
- 後續改善：{{followups}}

## 1 分鐘複驗
- URL：{{recheck_url}}
- 帳號 reference：{{recheck_account_ref}}
- 操作步驟：{{recheck_steps}}
- 預期結果：{{recheck_expected}}

## Run 遙測
- token 分帳：{{metrics_tokens}}
- agent 派遣：{{metrics_agents}}
- reviewer 回合：{{reviewer_rounds}}
- QA 回合：{{qa_rounds}}

## 阻擋紀錄（僅 BLOCKED 時有內容）
{{blocked_section}}
