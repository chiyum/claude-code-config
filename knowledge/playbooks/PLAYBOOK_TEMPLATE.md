---
title: <技術域> 設計框架 Playbook
type: playbook
tech: [<技術標籤>, <技術標籤>]
status: living
---

# <技術域> Playbook（設計框架）

> 這是一份**範本**，示範 playbook 的固定五段結構。Playbook 是「蒸餾層」：把同一技術域的多張事故知識卡蒸餾成一套「設計決策流程 + 必過檢查清單」，讓 agent 一次 Read 就拿到整套框架，需要事故細節再深入個別知識卡。
>
> 與知識卡的分工：**知識卡**記單一事故（症狀 / 根因 / 對策），**playbook** 記整個技術域的決策順序與檢查底線。`status: living` 表示它會隨新卡持續更新——architect 補新卡時，若該卡屬於本 playbook 的技術域，必須在同一 commit 內於「必過檢查清單」或「已知坑速查」補一列並連回新卡（規則見 `../INDEX.md`）。

## 何時讀

寫明「任務涉及什麼就要先讀本檔」，讓 agent 能用一句話判斷命中與否。
（虛構示例：任何涉及 Redis 讀寫 / cache / 分散式鎖 / Pub/Sub / 多實例 worker 的工作，動手前先走一遍本流程。）

## 設計決策流程（依序自問）

把該技術域的關鍵決策整理成「依序自問」的問題串，每題三行：問題 → 該怎麼做（對策濃縮）→ 為什麼（根因濃縮），並用 `[[卡名]]` 連回出處卡。

1. **這個長駐訂閱 / 長連線斷線後會自我恢復嗎？**
   → 內層負責單次 Subscribe 生命週期、外層永遠 reconnect（指數退避），只有 `ctx.Done()` 才退出；加 reconnect 計數與 lifecycle log。
   → 因為底層連線一定會斷，收到 channel close 就 return 的 goroutine 會永久失聯。[[example-card]]

2. **<下一個決策問題>**
   → <對策>
   → <根因>。[[<卡名>]]

## 必過檢查清單

交付前逐項打勾；每項都連回出處卡，違反時 reviewer 可直接點名。

- [ ] 所有長駐 Pub/Sub 訂閱 / 長連線 goroutine 都有 reconnect loop（指數退避 + 上限），不是收到 close 就 return [[example-card]]
- [ ] <檢查項> [[<卡名>]]

## 已知坑速查

| 坑 | 症狀 | 對策 | 深入卡 |
|---|---|---|---|
| Pub/Sub receive loop 收到 close 就 return | 某台 instance 從某刻起收不到跨機事件，重啟才恢復 | 兩層結構：內層單次生命週期、外層 reconnect for-loop | [example-card] |
| <坑> | <症狀> | <對策> | [<卡名>] |

## 深入閱讀

[example-card]: ../example-card.md
