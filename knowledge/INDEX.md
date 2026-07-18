# 工程知識庫索引（架構師成長系統）

> 這是一套**跨專案、可複用的工程教訓 / 模式知識庫**。記的不是「發生過什麼」（那是 memory），也不是「為什麼這樣決定」（那是 ADR），而是：**「下次碰到 X 技術，照這個做 / 別踩這個坑」**。
>
> 知識卡的成長引擎：architect / reviewer 在工作中撞到非顯而易見的技術坑、或學到有效模式時，**當下補一張卡**（規則見 `~/.claude/CLAUDE.md`）。隨著專案累積，這個資料夾會越長越厚，agent 也就越來越「有經驗」。

## agent 怎麼用這份索引

1. 接到任務時，先辨識涉及哪些**技術**（websocket / redis / go / 你的技術棧…）與**問題類別**（高併發 / 快取一致性 / race / 多實例…）。
2. **先讀命中技術域的 Playbook**（下表）：playbook 是把該域所有事故卡蒸餾成的「設計決策流程 + 必過檢查清單」，一次 Read 就拿到整套框架。
3. 需要事故細節（症狀重現、程式碼參考）時，才順著 playbook 的連結深入個別知識卡；playbook 未覆蓋的域再用下方兩張標籤索引比對命中卡。
4. 設計 / 審查 / 測試時把「對策」與「適用 / 不適用」納入考量；卡內 `程式碼參考` 可直接翻到真實實作。
5. 若這次又學到新教訓，照成長規則補一張卡並回此索引補一列；**新卡屬於既有 playbook 的域時，同一 commit 在該 playbook 補一列檢查項**（保持 playbook 是活的蒸餾層，不會過時）。

每張卡的 frontmatter 都有 `tech` 與 `problem-class` 標籤；新增卡請沿用既有標籤命名（小寫、kebab-case），需要新標籤時直接加。

## Playbook 層（設計框架，先讀這裡）

同一技術域累積 3~5 張卡之後，值得把它們蒸餾成一份 playbook（結構範本見 `playbooks/PLAYBOOK_TEMPLATE.md`：frontmatter `type: playbook` + 何時讀 / 設計決策流程 / 必過檢查清單 / 已知坑速查 / 深入閱讀 五段）。

| Playbook | 何時讀 | 蒸餾自 |
|---|---|---|
| [playbooks/PLAYBOOK_TEMPLATE.md](playbooks/PLAYBOOK_TEMPLATE.md) | （範本，展示結構用） | [example-card] |
| _(隨技術域累積補上，例如 redis / websocket / go-backend / 前端表單 / 時區)_ | … | … |

## 知識卡格式

複製 `example-card.md` 當範本，六段固定結構：

```
---
title: <一句話描述這個教訓 / 模式>
tech: [redis, pubsub]            # 涉及技術標籤，小寫 kebab-case
problem-class: [resilience]      # 問題類別標籤
source: <產品代號 / 來源>
status: validated                # validated=線上實證 / proposed=推論
---
## 症狀 / 觸發情境
## 根因
## 對策 / 模式
## 程式碼參考      （`相對路徑:行號`，讓後人翻得到）
## 適用 / 不適用
## 關聯           （[[其他卡名]]、commit hash）
```

---

## 依「技術」分類

| 技術標籤 | 知識卡 |
|---|---|
| **redis / pubsub** | [example-card] |
| _(隨專案累積補上)_ | … |

## 依「問題類別」分類

| 問題類別 | 知識卡 |
|---|---|
| **resilience（韌性）** | [example-card] |
| **problem-orientation / goalpost-moving（碰牆先在約束內解，別反射性改球門）** | [solve-within-constraints-before-moving-the-goalpost] |
| _(隨專案累積補上)_ | … |

---

## 全部知識卡

| 卡 | 一句話 | source | 狀態 |
|---|---|---|---|
| [example-card] | （範例）長駐 Pub/Sub 訂閱必須有 reconnect loop | example | validated |
| [solve-within-constraints-before-moving-the-goalpost] | 想提「放寬需求 / 改門檻 / 大重寫」前必先附「約束內解題」舉證（控制變因 / 讀既有能力 / reuse 積木，三式擇一）；舉不出證不准提，舉得出證升級為 owner 決策 | institution | validated |

<!-- 連結定義 -->
[example-card]: example-card.md
[solve-within-constraints-before-moving-the-goalpost]: solve-within-constraints-before-moving-the-goalpost.md
