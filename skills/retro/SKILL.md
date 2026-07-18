---
name: retro
description: 宏觀自我複盤（L4 hill-climbing 的人審版）。讀取上次複盤後累積的 run verdict、新增知識卡與摩擦訊號，找出「跨 ≥2 個任務重複出現的流程反模式」，產出改 harness 的提案清單給使用者圈選；使用者拍板才動 CLAUDE.md / playbook。觸發：任務完成評分後累積 ≥8 個 verdict 時主 Claude 順口詢問，或使用者隨時手動 /retro。
---

# /retro — 宏觀自我複盤

目的：把「定期退後一步、從跨任務的重複流程病調整自家規則」制度化。**分析全自動、改動人審**——本 skill 永不擅自修改 CLAUDE.md / playbook，一律先提案、使用者圈選後才動手。

## 流程

### 1. 彙整（確定性）

```bash
python3 ~/.claude/scripts/retro-digest.py
```

拿到上次複盤以來的：run verdict 清單（含 comment / outcome / notes）、新增知識卡清單。digest 為空或 run 數 < 3 時，告知使用者「樣本太少，建議再累積」，除非使用者堅持要跑。

### 2. 分析（主 Claude 或委派一隻唯讀 agent）

- 逐條讀 digest 中 `bad` / `ok` 的 verdict comment 與 notes，需要細節時回讀對應 `~/.claude/run-metrics/runs/<slug>.json` 與該任務的 state / acceptance 檔。
- 抽讀期間新增的知識卡標題（不必全文），找卡與卡之間的共通「流程」主題。
- digest 提到的專案若有新 ADR，抽查其「被取代 / 推翻」關係欄。
- **判準：同一種【流程】病在 ≥2 個不同任務出現才算 pattern。** 單一任務的技術坑不算（那是知識卡的職責，不是 retro 的）。
- 找的等級參考：「團隊反覆把『放寬需求』當第一反應，而不是先在約束內解題」這種跨任務的取向病。

### 3. 提案（寫檔，不動 harness）

寫入 `~/.claude/state/retro/<YYYYMMDD>-retro.md`，每條 pattern 必附：

- **證據**：哪幾個 run / 知識卡 / ADR（可點查）
- **建議調哪條規則**：CLAUDE.md 哪段 / 哪份 playbook / 哪個 agent 定義
- **白話 before/after**：使用者與團隊的操作流程改動前後 + 對系統的影響（讓非工程背景也能拍板）
- **信心**：高（證據 ≥3 處）/ 中（2 處）/ 低（其實不到 2 處就不該列）

**紀律（防止本機制自己變成反例）**：
- 每輪最多 3 條高訊號改動；沒有達標 pattern 就明寫「本輪無建議」——允許空手而回，嚴禁為改而改。
- 建議改動需通過自家「約束內解題」檢查：優先調既有規則的字句，而不是加新機制、新 gate、新腳本。
- CLAUDE.md 相關建議必附預估字數影響（保險絲 35KB）。

### 4. 使用者圈選 → 才動手

- 用 AskUserQuestion 或列點讓使用者圈選採納哪幾條。
- 採納的才改（~/.claude 檔案主 Claude 直接改；涉及 repo 內 playbook/agent 行為大改則照常走流程）。
- 改完在提案檔尾補一段「拍板結果」：採納了哪幾條、駁回了哪幾條與理由。

### 5. 收尾

```bash
python3 ~/.claude/scripts/retro-digest.py --mark   # 更新 .last-retro，重新起算
```

## 觸發方式（寫在 CLAUDE.md 第五步的護欄）

- 大任務最終回報時，主 Claude 問完任務評分後跑 `retro-digest.py --count`，**≥8 就順口問一句**「要不要順便複盤」；使用者說好才跑，說晚點就擱著下次再問，不糾纏。
- 使用者任何時候手動 `/retro` 也可以，不受門檻限制。
- **絕不自動觸發、絕不在自主開發中途觸發。**
