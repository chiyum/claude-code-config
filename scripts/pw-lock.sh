#!/bin/bash
# Playwright MCP 瀏覽器互斥鎖（QA / PM / design-reviewer / ui-designer 共用同一把）
# 用法: pw-lock.sh acquire [owner]  → 取到印 LOCK ACQUIRED (exit 0)；排隊逾時印 LOCK WAIT TIMEOUT (exit 1)
#       pw-lock.sh release          → 釋放（browser_close 之後立刻跑，成功或失敗路徑都要）
# 原理: mkdir 是原子操作，天然互斥；殘留鎖（前一個 agent 崩潰）超過 STALE 秒自動接管
LOCKDIR="$HOME/.claude/locks/playwright-mcp.lock.d"
STALE=${PW_LOCK_STALE:-3600}     # 60 分鐘視為殘留鎖（PM 全流程常超過 20 分鐘，2026-09-19 由 1200 調高）
MAX_WAIT=${PW_LOCK_MAX_WAIT:-3600} # 最長排隊 60 分鐘
case "$1" in
  acquire)
    OWNER="${2:-agent}@$(basename "$(pwd)")"
    mkdir -p "$HOME/.claude/locks"
    waited=0
    while true; do
      if mkdir "$LOCKDIR" 2>/dev/null; then
        date +%s > "$LOCKDIR/acquired_at"; echo "$OWNER" > "$LOCKDIR/owner"
        echo "LOCK ACQUIRED by $OWNER"; exit 0
      fi
      now=$(date +%s); at=$(cat "$LOCKDIR/acquired_at" 2>/dev/null || echo "$now")
      if [ $(( now - at )) -gt "$STALE" ]; then
        # 接管必須原子：先把殘留鎖 mv 到唯一名稱（rename 原子），只有 mv 成功的那一個才算接管；
        # 原本的 rm -rf 後 mkdir 不是原子操作，兩個同時偵測到 stale 的 agent 會都以為自己拿到鎖（2026-09-19 qa-bc-prod 實測）
        stale_dir="$LOCKDIR.stale.$$.$now"
        if mv "$LOCKDIR" "$stale_dir" 2>/dev/null; then
          echo "STALE LOCK $(( now - at ))s (owner=$(cat "$stale_dir/owner" 2>/dev/null))，接管"; rm -rf "$stale_dir"
        fi
        continue
      fi
      if [ "$waited" -ge "$MAX_WAIT" ]; then echo "LOCK WAIT TIMEOUT"; exit 1; fi
      s=$(( (RANDOM % 4) + 6 )); sleep "$s"; waited=$(( waited + s ))
      echo "排隊等待瀏覽器鎖 ${waited}s（目前持有者：$(cat "$LOCKDIR/owner" 2>/dev/null)）"
    done ;;
  release)
    rm -rf "$LOCKDIR" && echo "LOCK RELEASED" ;;
  *)
    echo "用法: pw-lock.sh acquire [owner] | release"; exit 2 ;;
esac
