# 工程知識庫索引（架構師成長系統）

> 這是一套**跨專案、可複用的工程教訓 / 模式知識庫**。記的不是「發生過什麼」（那是 memory），也不是「為什麼這樣決定」（那是 ADR），而是：**「下次碰到 X 技術，照這個做 / 別踩這個坑」**。
>
> 知識卡的成長引擎：architect / reviewer 在工作中撞到非顯而易見的技術坑、或學到有效模式時，**當下補一張卡**（規則見 `~/.claude/CLAUDE.md`）。隨著專案累積，這個資料夾會越長越厚，agent 也就越來越「有經驗」。

## agent 怎麼用這份索引

1. 接到任務時，先辨識涉及哪些**技術**（websocket / redis / go / 你的技術棧…）與**問題類別**（高併發 / 快取一致性 / race / 多實例…）。
2. 在下方兩張索引比對命中標籤，**只讀命中的知識卡**（不必全讀）。
3. 設計 / 審查 / 測試時把卡內「對策」與「適用 / 不適用」納入考量；卡內 `程式碼參考` 可直接翻到真實實作。
4. 若這次又學到新教訓，照成長規則補一張卡並回此索引補一列。

每張卡的 frontmatter 都有 `tech` 與 `problem-class` 標籤；新增卡請沿用既有標籤命名（小寫、kebab-case），需要新標籤時直接加。

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
| _(隨專案累積補上)_ | … |

---

## 全部知識卡

| 卡 | 一句話 | source | 狀態 |
|---|---|---|---|
| [example-card] | （範例）長駐 Pub/Sub 訂閱必須有 reconnect loop | example | validated |

<!-- 連結定義 -->
[example-card]: example-card.md
