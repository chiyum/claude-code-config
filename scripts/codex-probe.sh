#!/bin/bash
# codex-probe.sh — 呼喚 Codex 前的可用性 / 額度探測
#
# 用途：主 Claude（orchestrator）想把問題丟給 Codex 取得「異模型第二意見」前，
#       必須先跑本腳本。任何非 0 的 exit code 都代表「這次不要用 Codex」，
#       直接照原流程（自家 agent）繼續，不重試、不等待。
#
# 原理：對 codex exec 發一個極小探測（輸出約 5 tokens、輸入幾乎全 cache），
#       能完整跑完一輪 turn.completed 才算可用。額度耗盡 / 未登入 / 網路異常
#       都會在這一步被攔下，避免正式任務跑到一半斷掉。
#
# exit code：
#   0 = 可用（額度足夠、登入正常）
#   2 = codex 未安裝
#   3 = 未登入
#   4 = 額度不足（usage / rate limit）
#   5 = 其他失敗（逾時、網路、未知錯誤）
#
# 用法：bash ~/.claude/scripts/codex-probe.sh [timeout秒數，預設90]

set -u

PROBE_TIMEOUT="${1:-90}"

# --- 1. 安裝檢查 ---
if ! command -v codex >/dev/null 2>&1; then
  echo "CODEX_PROBE: NOT_INSTALLED（codex 不在 PATH，跳過 Codex 走原流程）"
  exit 2
fi

# --- 2. 登入檢查 ---
LOGIN_OUTPUT="$(codex login status 2>&1)"
if ! echo "$LOGIN_OUTPUT" | grep -qi "logged in"; then
  echo "CODEX_PROBE: NOT_LOGGED_IN（$LOGIN_OUTPUT）"
  exit 3
fi

# --- 3. 額度探測：極小 exec 呼叫 ---
# 可攜式 timeout：優先用 coreutils timeout，沒有就用 perl alarm 包裝
run_with_timeout() {
  local secs="$1"; shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "$secs" "$@"
  elif command -v gtimeout >/dev/null 2>&1; then
    gtimeout "$secs" "$@"
  else
    perl -e 'alarm shift; exec @ARGV' "$secs" "$@"
  fi
}

PROBE_OUTPUT="$(echo "只回覆兩個字：OK" | run_with_timeout "$PROBE_TIMEOUT" \
  codex exec --json --skip-git-repo-check --ephemeral -s read-only - 2>&1)"
PROBE_EXIT=$?

# 額度耗盡的典型錯誤字樣（ChatGPT 方案 / API 兩種都涵蓋）
if echo "$PROBE_OUTPUT" | grep -qiE "usage limit|rate limit|quota|exceeded.*limit|too many requests|429"; then
  echo "CODEX_PROBE: QUOTA_EXHAUSTED（額度不足，跳過 Codex 走原流程）"
  exit 4
fi

# 成功判準：JSONL 事件流有完整跑完一輪
if echo "$PROBE_OUTPUT" | grep -q '"type":"turn.completed"'; then
  USAGE_LINE="$(echo "$PROBE_OUTPUT" | grep '"type":"turn.completed"' | tail -1)"
  echo "CODEX_PROBE: OK（可用）$USAGE_LINE"
  exit 0
fi

# 走到這裡 = 逾時或未知錯誤
echo "CODEX_PROBE: FAILED（exit=$PROBE_EXIT，逾時或未知錯誤，跳過 Codex 走原流程）"
echo "$PROBE_OUTPUT" | tail -5
exit 5
