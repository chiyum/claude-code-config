---
title: 長駐 Redis Pub/Sub 訂閱必須包 reconnect loop，否則連線一斷就永久失聯
tech: [redis, pubsub, goroutine]
problem-class: [resilience, multi-instance, cache-invalidation]
source: example
status: validated
---

> 這是一張**範例知識卡**，示範格式用。真實的知識卡由 architect / reviewer 在工作中撞到坑時補上，並帶有可追溯的 `檔案:行號`。

## 症狀 / 觸發情境
多實例部署下，某台 instance 從某刻起再也收不到別台廣播的事件（如 cache 失效訊號），且不會自我恢復，只能重啟 process 暫時解除。Redis 只要短暫中斷或重啟過一次就會觸發。

## 根因
把 `pubsub.Channel()` 的 receive loop 寫成「收到 channel close（連線中斷 / server 重啟）就 `return`」。goroutine 一旦 return 就永久消失，沒有任何重連機制，此 instance 從此與 Pub/Sub 脫節。

## 對策 / 模式
拆兩層：內層負責「單次 Subscribe 生命週期」，連線中斷時回 error；外層是永遠 reconnect 的 for-loop，指數退避（如 1s → 上限 30s），只有 `ctx.Done()`（process 結束）才退出。加 reconnect 計數器 + lifecycle log，方便日後判斷 subscriber 是否死過。

**通則：任何長駐訂閱 / 長連線 goroutine 都必須假設底層連線會斷，reconnect loop 是標配而非選配。**

## 程式碼參考
- `<repo>/path/to/cache_repo.go:NN`（reconnect loop + 指數退避）
- `<repo>/path/to/cache_repo.go:NN`（單次 subscribe 生命週期）

## 適用 / 不適用
- 適用：所有長駐的 Pub/Sub 訂閱、長連線（WS / gRPC stream）。
- 不適用：一次性、短生命週期的訂閱（請求內訂閱完即關）。

## 關聯
- 相關卡：[[example-card]]（同類事故的其他面向）、commit `<hash>`
