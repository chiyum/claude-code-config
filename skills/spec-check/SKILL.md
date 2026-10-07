---
name: spec-check
description: 外部規格技術可行性檢查（唯讀）。在規格治理者凍結 SPEC 之前（DRAFT）或凍結後稽核（FROZEN），從 repo、產品配置、repo memory、知識庫角度逐條檢查驗收條件可行性、隱藏影響與規格衝突，輸出固定格式報告。不改 code、不改 SPEC、不 commit、不部署、不替使用者做產品選擇。用法：/spec-check <SPEC.md 絕對路徑>
user-invocable: true
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash
---

# /spec-check — 外部規格技術可行性檢查

墊在外部規格模式（`~/.claude/acceptance/EXTERNAL_SPEC_PROTOCOL.md`）之前：治理者寫好 SPEC 草稿，先讓 Claude 從技術現況回答「這份規格能不能做、做下去會碰到什麼」，治理者再決定要不要凍結。本 skill 是**唯讀**的：Bash 只准跑驗證器、hash、`git log` / `git grep` 這類唯讀指令。

## 可以 / 不可以

| 可以 | 不可以 |
|---|---|
| Read SPEC、manifest、產品配置、repo memory、相關 repo 原始碼 | 修改 code、SPEC、manifest |
| 讀既有 API、資料模型、元件、部署方式；查 `~/.claude/knowledge/` | 建立 migration、commit、push、部署 |
| 找既有能力、判斷影響範圍、找規格與現況的衝突 | 替使用者做產品選擇 |
| 建議可驗證的證據形式 | 把技術偏好升格為產品限制、偷偷把建議寫進 SPEC |

## 步驟

1. **驗證檔案**（允許 DRAFT）：
   ```bash
   python3 ~/.claude/scripts/verify-external-spec.py --spec <SPEC.md> --mode check
   ```
   - exit 6（`SPEC_SUPERSEDED`）→ 直接回報「此檔已被取代，不得作為新任務來源；請向治理者取最新版本路徑」，**不猜新版路徑**，結束
   - exit 2/3/4（找不到 / 缺 manifest / 格式錯）→ 回報錯誤 JSON 的 `message`，仍可對 SPEC 正文做可行性檢查，但報告頂端註明「檔案層驗證未通過，凍結前必須先修正」
   - ok 且 `frozen_audit: true` → 報告標題下方標示「**凍結後稽核**：本報告只回報發現，SPEC 不得因此修改；要改請走 Change Request」
2. **載入產品上下文**：Read `~/.claude/products/INDEX.md` → `<product>.md` → 該產品 repo memory（照 CLAUDE.md session 啟動規則）。product 未註冊 → 報告「規格衝突」列出
3. **讀知識庫**：`~/.claude/knowledge/INDEX.md` 頂部的 Playbook 層，優先讀命中技術域的 playbook
4. **逐條 A 對 repo 現況**：對每條驗收條件找既有能力（API / 表 / 元件 / 權限），判斷是「已有」「需擴充」「需新建」「與現況衝突」；衝突要附程式碼路徑證據
5. **隱藏影響**：資料庫、權限、快取、跨 instance、前後端相容、部署順序、回滾
6. **輸出報告**（格式固定如下）；SPEC 有問題時只輸出事實、證據、選項，不改寫 SPEC

大型規格（≥8 條 A 或跨 3 個以上 repo）可用 Agent tool 派唯讀 `Explore` 平行掃不同 repo，每隻只讀、維度互斥，最後由主 Claude 單點匯總（護欄 B）。

## 輸出格式（固定）

```
# 技術可行性檢查報告

## 規格識別
- Spec ID：
- Product：
- Version：
- Status：（DRAFT / FROZEN — 凍結後稽核 / 檔案層驗證未通過）
- SHA-256：

## 整體結論
- 可直接實作 / 有條件可實作 / 存在規格衝突

## 驗收條件逐條檢查

### A1
- 可行性：
- 現有能力：
- 影響 repo：
- 可能修改：
- 風險：
- 建議驗證方式：

## 隱藏影響
- 資料庫：
- 權限：
- 快取：
- 跨 instance：
- 前後端相容：
- 部署順序：
- 回滾：

## 規格衝突
- 無，或列出確切衝突與程式碼證據

## 需要產品決策
僅列出無法在現有凍結約束內解決的事項。

## 非阻擋建議
不得偷偷加入 SPEC，只能列為建議。
```

報告只在對話中呈現；若使用者要求留檔，寫到 `~/.claude/acceptance/<spec_id>/spec-check-<YYYYMMDD>.md`（Claude 側），**不寫進 `~/.claude/specs/` 的版本目錄**。
