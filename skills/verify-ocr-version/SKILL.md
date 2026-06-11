---
name: verify-ocr-version
description: 給出一組指令讓使用者能驗證線上 dev / prod 的 sidecar 服務是不是已部署到最新版（本地 main 的 HEAD commit）。觸發詞：「驗證版本」、「是不是最新版」。
user-invocable: true
allowed-tools:
  - Bash
  - Read
---

# 驗證線上 sidecar 是否為最新版

## 動機

某些 sidecar 服務不在 CI 自動部署範圍內，每次有 code 改動都要手動部署。曾經出現「code 已 push 但 dev 機沒拉新 image」導致線上跑舊版的事故。本 skill 給使用者一組指令快速判定線上跟本地 main 的 HEAD 是否一致。

## 使用流程

### Step 1：取本地 main HEAD（主 Claude 自己跑）

```bash
cd <your-sidecar-repo-path> && \
git fetch origin main 2>&1 | tail -3 && \
echo "本地 main HEAD：" && git log -1 --format='%h %s (%ai)' origin/main
```

記下 commit hash 與 subject 作為「期望版本」。

### Step 2：從最新 diff 找辨識字串

```bash
cd <your-sidecar-repo-path> && \
git diff HEAD~1 HEAD -- '*.py' '*.go' | grep '^+' | grep -oE '[A-Za-z_]{8,}' | sort -u | head -10
```

從輸出挑一個「該 commit 新引入的、不會在舊版出現」的識別字串。

### Step 3：給使用者跑（在 dev 機 SSH session）

```bash
# A) container image 何時 built
docker inspect <container-name> --format '{{.Image}} created={{.Created}}'

# B) container 上次啟動時間
docker ps --filter name=<container-name> --format 'name={{.Names}}\nstatus={{.Status}}\nimage={{.Image}}'

# C) sidecar 內是否含「最新 commit 的關鍵字串」
docker exec <container-name> grep -c "<identification-string>" /app/<source-file>
```

### Step 4：判讀

| 指令 A image created 時間 | 指令 C grep 結果 | 判定 |
|---|---|---|
| 跟本地 HEAD push 時間相近 | ≥ 1 | ✅ 線上是最新版 |
| 比本地 HEAD push 早很多 | 0 | ❌ image 沒重 build，要手動部署 |

### Step 5：如果未部署，給使用者部署指令

```bash
cd <deploy-path> && \
git fetch origin main && git reset --hard origin/main && git clean -fd && \
docker compose up -d --build && \
sleep 30 && \
docker exec <container-name> grep -c "<identification-string>" /app/<source-file>
```

## 設計脈絡

- 為什麼要這個 skill：CI 沒含 sidecar、人類手動部署容易漏
- 為什麼不用 image tag：dev compose 用固定 tag，不帶 commit hash，光看 image name 看不出版本
- 為什麼用 grep 驗證：因為這是最可靠的方式，確認 container 內的程式碼確實是最新版
