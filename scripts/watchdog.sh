#!/bin/bash
# 看門狗核心（平台無關）：由外部排程器（launchd / cron / Windows 工作排程器）每 ~10 分鐘喚醒
# 職責:
#   1. running 且心跳逾期且 session 真的死了 → claude --resume 復活（上限 MAX_RESTART 次）
#   2. awaiting_next_batch → 開新 session 接續下一批（批次=Session 制度）
#   3. done 超過保留天數 → 清理 state / handoff / questions 檔
# 設計原則: 冪等（重複執行無副作用）、單實例鎖、絕不動 awaiting_user 的任務
# 排程器安裝見 install-watchdog.sh；state 檔格式見 ../state/README.md

STATE_DIR="$HOME/.claude/state"
LOG="$STATE_DIR/watchdog.log"
CONF="$STATE_DIR/watchdog.conf"; [ -f "$CONF" ] && . "$CONF"
STALE_SECONDS=${STALE_SECONDS:-1200}
MAX_RESTART=${MAX_RESTART:-3}
CLAUDE_BIN=${CLAUDE_BIN:-claude}
# 權限旗標預設留空（保守）；全自動模式在 watchdog.conf 設 --dangerously-skip-permissions
PERMISSION_FLAGS=${PERMISSION_FLAGS:-}
DONE_RETENTION_DAYS=${DONE_RETENTION_DAYS:-7}

log(){ echo "[$(date '+%F %T')] $*" >> "$LOG"; }

command -v jq >/dev/null 2>&1 || { log "缺 jq，無法解析 state 檔，本輪跳過"; exit 0; }
command -v "$CLAUDE_BIN" >/dev/null 2>&1 || { log "找不到 claude 執行檔（$CLAUDE_BIN），請重跑 install-watchdog.sh"; exit 0; }

# 看門狗自身單實例鎖（mkdir 原子性；殘留鎖 30 分鐘接管）
LOCKDIR="$STATE_DIR/.watchdog.lock.d"
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  at=$(cat "$LOCKDIR/at" 2>/dev/null || echo 0)
  if [ $(( $(date +%s) - at )) -gt 1800 ]; then rm -rf "$LOCKDIR"; mkdir "$LOCKDIR" 2>/dev/null || exit 0; else exit 0; fi
fi
date +%s > "$LOCKDIR/at"
trap 'rm -rf "$LOCKDIR"' EXIT

now=$(date +%s)
for f in "$STATE_DIR"/*.json; do
  [ -e "$f" ] || continue
  task=$(jq -r '.task // empty' "$f" 2>/dev/null)
  status=$(jq -r '.status // empty' "$f" 2>/dev/null)
  [ -z "$task" ] && continue

  case "$status" in
    done)
      upd=$(jq -r '.updated_at // 0' "$f")
      if [ $(( now - upd )) -gt $(( DONE_RETENTION_DAYS * 86400 )) ]; then
        rm -f "$f" "$STATE_DIR/$task-handoff.md" "$STATE_DIR/$task-questions.md" "$STATE_DIR/$task.resume.log"
        log "🧹 清理已完成任務 $task"
      fi
      ;;

    running)
      upd=$(jq -r '.updated_at // 0' "$f")
      rc=$(jq -r '.restart_count // 0' "$f")
      sid=$(jq -r '.session_id // empty' "$f")
      age=$(( now - upd ))
      [ "$age" -lt "$STALE_SECONDS" ] && continue

      # 活性雙重判定: 心跳過期但 session transcript 還在更新 = 只是長工具呼叫，不誤殺
      if [ -n "$sid" ]; then
        tf=$(ls "$HOME"/.claude/projects/*/"$sid".jsonl 2>/dev/null | head -1)
        if [ -n "$tf" ] && [ -n "$(find "$tf" -mmin -$(( STALE_SECONDS / 60 )) 2>/dev/null)" ]; then
          log "$task 心跳逾期但 transcript 仍在更新，視為存活，跳過"
          continue
        fi
      fi
      if [ "$rc" -ge "$MAX_RESTART" ]; then
        log "⚠️ $task 已達重啟上限 ${MAX_RESTART} 次，停止自動復活。手動接續: $CLAUDE_BIN --resume $sid"
        continue
      fi
      if [ -z "$sid" ]; then log "⚠️ $task 缺 session_id，無法 resume"; continue; fi

      tmp=$(mktemp); jq --argjson n "$now" '.restart_count += 1 | .updated_at = $n' "$f" > "$tmp" && mv "$tmp" "$f"
      log "🔄 復活 $task（第 $(( rc + 1 )) 次）: --resume $sid"
      nohup "$CLAUDE_BIN" $PERMISSION_FLAGS --resume "$sid" -p "看門狗通知: 任務 $task 的 session 疑似中斷。第一步 Read ~/.claude/state/$task.json 與同目錄的 handoff / questions 檔及對應 acceptance 清單，把 state 檔 updated_at 更新，然後從 next_action 依 CLAUDE.md 五步驟流程繼續；完成後 status 設為 done。" >> "$STATE_DIR/$task.resume.log" 2>&1 &
      ;;

    awaiting_next_batch)
      # 已有同任務的接續 process 在跑就不雙開
      if pgrep -f "繼續 $task" >/dev/null 2>&1; then continue; fi
      tmp=$(mktemp); jq --argjson n "$now" '.status = "running" | .updated_at = $n' "$f" > "$tmp" && mv "$tmp" "$f"
      log "▶️ 開新 session 接續 $task 下一批"
      nohup "$CLAUDE_BIN" $PERMISSION_FLAGS -p "執行 /dev 繼續 $task（先 Read ~/.claude/state/$task.json 與 $task-handoff.md，把 state 檔 session_id 更新為本 session 的 transcript UUID，再接續下一批）" >> "$STATE_DIR/$task.resume.log" 2>&1 &
      ;;

    # awaiting_user 或未知狀態: 一律不動
  esac
done
exit 0
