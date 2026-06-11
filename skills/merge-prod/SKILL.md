---
name: merge-prod
description: 把多個應用 repo 的 main 分支合併到部署分支（如 prod）並 push。觸發詞：「合併正式站」「上正式站」「merge prod」。
user-invocable: true
allowed-tools:
  - Bash
---

# 合併正式站 — main → prod 部署分支

把應用層 repo 從 main 合併到部署用分支（如 `prod` 或 `prod_mcs`），並 push。

## 適用範圍（按你的專案修改）

```
<your-path>/backend-service
<your-path>/admin-frontend
<your-path>/client-frontend
```

## 觸發

使用者在對話中說：
- 「合併正式站」
- 「上正式站」（同義）
- 「merge prod」「prod merge」

或 `/merge-prod` 直接呼叫。

## 執行流程（每個 repo 各跑一次）

對每一個 repo 嚴格按下列步驟，**任一步失敗就 abort 該 repo 並繼續下一個**（記錄錯誤、最後總結回報）：

```bash
cd <repo>

# 1. 工作區乾淨檢查（避免覆蓋未提交改動）
git status --porcelain
# 若輸出非空 → SKIP 並記錄「工作區不乾淨」

# 2. 抓最新遠端
git fetch origin

# 3. 切到 main 並拉最新
git checkout main
git pull origin main

# 4. 切到部署分支並拉最新
git checkout <deploy-branch>
git pull origin <deploy-branch>

# 5. 合併 main 到部署分支（不 fast-forward，保留 merge commit 容易追蹤）
git merge --no-ff main -m "Merge branch 'main' into <deploy-branch>"
# 若 merge 衝突 → git merge --abort + 切回 main + SKIP 並記錄「衝突」

# 6. push 部署分支
git push origin <deploy-branch>
# 若 push 失敗 → 記錄錯誤但仍切回 main

# 7. 切回 main（無論前面成功與否）
git checkout main
```

## 失敗處理規則

每個 repo 獨立判斷，不互相影響：

| 失敗情境 | 處理 |
|---------|------|
| `git status` 不乾淨 | SKIP 該 repo，記錄「工作區不乾淨：<檔案清單>」 |
| `git pull` 失敗 | SKIP 該 repo，記錄「pull 失敗：<原因>」 |
| `git merge` 衝突 | `git merge --abort` 還原 → 切回 main → SKIP 該 repo，記錄「合併衝突」 |
| `git push` 失敗 | 仍切回 main，記錄「push 失敗：<原因>」（本機已 merge 完成）|

**衝突時不要嘗試自動解** — 直接 abort 並回報，由使用者手動處理。

## 收尾總結（必做）

跑完所有 repo 後輸出表格：

```
合併正式站結果：

| Repo                 | 狀態    | 合併 commit 數 | push  | 備註           |
|----------------------|---------|---------------|-------|---------------|
| backend-service      | ✅ 成功 | 3             | ✅    | -             |
| admin-frontend       | ❌ 衝突 | -             | -     | src/foo.vue   |
| client-frontend      | ✅ 成功 | 1             | ✅    | -             |
```

「合併 commit 數」用 `git rev-list --count <OLD_HEAD>..HEAD` 算（merge 前的部署分支 HEAD 到 merge 後的差）。**不要加 `--no-merges`**，否則 merge commit 自己會被排除，導致回報 0。

衝突的 repo 必須在備註列出有衝突的檔案清單，方便使用者直接打開處理。

## 安全規則（不可違反）

1. **不會 force push**：只用普通 push，遠端有衝突就停
2. **不會自動解衝突**：永遠 abort + 回報，讓使用者決定
3. **不會跳過 main pull**：避免合到落後的本機 main → 把舊 code 推到部署分支
4. **不論成功失敗最後都切回 main**：避免使用者後續工作在錯的分支
