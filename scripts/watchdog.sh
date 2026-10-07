#!/bin/bash
# 看門狗核心（平台無關）：由外部排程器（launchd / cron / Windows 工作排程器）每 ~10 分鐘喚醒
# 職責:
#   1. running 且心跳逾期且 session 真的死了 → claude --resume 復活（上限 MAX_RESTART 次）
#   2. awaiting_next_batch → 開新 session 接續下一批（批次=Session 制度）
#   3. done 超過保留天數 → 清理 state / handoff / questions 檔
#   4. 任務閒置超過保留天數 → 清理 acceptance/<任務>/evidence/ 證據大檔（驗收清單 .md 永久保留）
#   5. 任何狀態的 state 檔 mtime 超過 IDLE_ARCHIVE_DAYS → 連同 handoff / questions / resume.log 搬到 state/archive/
#      （awaiting_user / reported 也歸檔，不刪；已達重啟上限或缺 session_id 的殭屍 running 同樣靠這條退場）
# 設計原則: 冪等（重複執行無副作用）、單實例鎖、絕不復活 awaiting_user / reported 的任務
# profile 機制（2026-08 起）: transcript 在 ~/.ai-profiles/claude/<profile>/projects/ 或 ~/.claude/projects/；
#   復活 / 接續必須帶同一個 CLAUDE_CONFIG_DIR，否則 claude --resume 回「No conversation found」（2026-09-13 修正）
# 排程器安裝見 install-watchdog.sh；state 檔格式見 ../state/README.md

STATE_DIR="$HOME/.claude/state"
LOG="$STATE_DIR/watchdog.log"
CONF="$STATE_DIR/watchdog.conf"; [ -f "$CONF" ] && . "$CONF"
STALE_SECONDS=${STALE_SECONDS:-1200}
MAX_RESTART=${MAX_RESTART:-3}
CLAUDE_BIN=${CLAUDE_BIN:-claude}
PERMISSION_FLAGS=${PERMISSION_FLAGS:---dangerously-skip-permissions}
DONE_RETENTION_DAYS=${DONE_RETENTION_DAYS:-7}
IDLE_ARCHIVE_DAYS=${IDLE_ARCHIVE_DAYS:-14}
DEFAULT_CONFIG_DIR=${DEFAULT_CONFIG_DIR:-}   # state 檔沒 config_dir、transcript 也找不到時用的 profile；空字串 = ~/.claude
ARCHIVE_DIR="$STATE_DIR/archive"

log(){ echo "[$(date '+%F %T')] $*" >> "$LOG"; }
# log 輪替：超過 2MB 只留最後 3000 行（過往一度累積到 3.9MB，全是重複警告）
if [ -f "$LOG" ] && [ "$(stat -f %z "$LOG" 2>/dev/null || stat -c %s "$LOG")" -gt 2000000 ]; then
  tail -n 3000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi
# 同一則警告 24 小時只記一次（殭屍任務每 10 分鐘灌同樣的話沒有意義）
warn_once(){ local key; key=$(printf '%s' "$1" | tr -c 'A-Za-z0-9_.-' '_'); shift
  mkdir -p "$STATE_DIR/.warned"
  if [ -z "$(find "$STATE_DIR/.warned/$key" -mmin -1440 2>/dev/null)" ]; then log "$@"; touch "$STATE_DIR/.warned/$key"; fi; }
# 找 session transcript：先掃 profile 目錄，再掃舊的 ~/.claude/projects
find_transcript(){ ls "$HOME"/.ai-profiles/claude/*/projects/*/"$1".jsonl "$HOME"/.claude/projects/*/"$1".jsonl 2>/dev/null | head -1; }
# 由 transcript 路徑推回該 session 的 CLAUDE_CONFIG_DIR（~/.claude 本身回空字串）
config_dir_of(){ case "$1" in "$HOME"/.ai-profiles/claude/*) echo "${1%%/projects/*}" ;; *) echo "" ;; esac; }
# 決定復活 / 接續要用的 profile：state.config_dir > transcript 路徑推回 > DEFAULT_CONFIG_DIR
resolve_config_dir(){ local f="$1" sid="$2" cfg; cfg=$(jq -r '.config_dir // empty' "$f" 2>/dev/null)
  [ -z "$cfg" ] && [ -n "$sid" ] && cfg=$(config_dir_of "$(find_transcript "$sid")")
  [ -z "$cfg" ] && cfg="$DEFAULT_CONFIG_DIR"; echo "$cfg"; }
# 用指定 profile 啟動 claude（背景、無頭）
run_claude(){ local cfg="$1" out="$2"; shift 2
  if [ -n "$cfg" ]; then CLAUDE_CONFIG_DIR="$cfg" nohup "$CLAUDE_BIN" "$@" >> "$out" 2>&1 &
  else nohup "$CLAUDE_BIN" "$@" >> "$out" 2>&1 & fi; }
# 把任務的 state / handoff / questions / resume.log 搬進 archive/
archive_task(){ mkdir -p "$ARCHIVE_DIR"; mv -f "$1" "$ARCHIVE_DIR"/
  for x in "$STATE_DIR/$2-handoff.md" "$STATE_DIR/$2-questions.md" "$STATE_DIR/$2.resume.log"; do [ -e "$x" ] && mv -f "$x" "$ARCHIVE_DIR"/; done; }

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

  # 職責 5: 任何狀態、檔案本身 IDLE_ARCHIVE_DAYS 天沒動 → 歸檔（用 mtime，不信 updated_at 的格式）
  if [ -n "$(find "$f" -mtime +"$IDLE_ARCHIVE_DAYS" 2>/dev/null)" ]; then
    archive_task "$f" "$task"; log "📦 歸檔閒置任務 ${task}（status=${status}，超過 ${IDLE_ARCHIVE_DAYS} 天未動）"; continue
  fi

  case "$status" in
    done)
      upd=$(jq -r '.updated_at // 0' "$f")
      case "$upd" in ''|*[!0-9]*) upd=0 ;; esac  # 硬化：updated_at 非純數字(如誤寫成日期字串)一律當 0，避免 $((now-upd)) 算術爆掉導致心跳靜默失效（2026-07-19 事故）
      if [ $(( now - upd )) -gt $(( DONE_RETENTION_DAYS * 86400 )) ]; then
        archive_task "$f" "$task"; log "📦 歸檔已完成任務 $task"
      fi
      ;;

    running)
      upd=$(jq -r '.updated_at // 0' "$f")
      case "$upd" in ''|*[!0-9]*) upd=0 ;; esac  # 硬化：updated_at 非純數字(如誤寫成日期字串)一律當 0，避免 $((now-upd)) 算術爆掉導致心跳靜默失效（2026-07-19 事故）
      rc=$(jq -r '.restart_count // 0' "$f")
      sid=$(jq -r '.session_id // empty' "$f")
      age=$(( now - upd ))
      [ "$age" -lt "$STALE_SECONDS" ] && continue

      if [ -z "$sid" ]; then warn_once "$task-nosid" "⚠️ $task 缺 session_id，無法 resume（閒置滿 ${IDLE_ARCHIVE_DAYS} 天會自動歸檔）"; continue; fi
      # 活性雙重判定: 心跳過期但 session transcript 還在更新 = 只是長工具呼叫，不誤殺
      tf=$(find_transcript "$sid")
      if [ -n "$tf" ] && [ -n "$(find "$tf" -mmin -$(( STALE_SECONDS / 60 )) 2>/dev/null)" ]; then
        log "$task 心跳逾期但 transcript 仍在更新，視為存活，跳過"
        continue
      fi
      if [ -z "$tf" ]; then warn_once "$task-notf" "⚠️ $task 的 session $sid 在任何 profile 都找不到 transcript，無法 resume"; continue; fi
      cfg=$(resolve_config_dir "$f" "$sid")
      if [ "$rc" -ge "$MAX_RESTART" ]; then
        warn_once "$task-limit" "⚠️ $task 已達重啟上限 ${MAX_RESTART} 次，停止自動復活。手動接續: CLAUDE_CONFIG_DIR=${cfg:-~/.claude} $CLAUDE_BIN --resume $sid"
        continue
      fi

      tmp=$(mktemp); jq --argjson n "$now" '.restart_count += 1 | .updated_at = $n' "$f" > "$tmp" && mv "$tmp" "$f"
      log "🔄 復活 ${task}（第 $(( rc + 1 )) 次，profile=${cfg:-~/.claude}）: --resume $sid"
      run_claude "$cfg" "$STATE_DIR/$task.resume.log" $PERMISSION_FLAGS --resume "$sid" -p "看門狗通知: 任務 $task 的 session 疑似中斷。第一步 Read ~/.claude/state/$task.json 與同目錄的 handoff / questions 檔及對應 acceptance 清單，把 state 檔 updated_at 更新，然後從 next_action 依 CLAUDE.md 五步驟流程繼續；做完回報後 status 設為 reported。"
      ;;

    awaiting_next_batch)
      # 已有同任務的接續 process 在跑就不雙開
      if pgrep -f "繼續 $task" >/dev/null 2>&1; then continue; fi
      sid=$(jq -r '.session_id // empty' "$f")
      cfg=$(resolve_config_dir "$f" "$sid")
      tmp=$(mktemp); jq --argjson n "$now" '.status = "running" | .updated_at = $n' "$f" > "$tmp" && mv "$tmp" "$f"
      log "▶️ 開新 session 接續 $task 下一批（profile=${cfg:-~/.claude}）"
      run_claude "$cfg" "$STATE_DIR/$task.resume.log" $PERMISSION_FLAGS -p "執行 /dev 繼續 ${task}（先 Read ~/.claude/state/$task.json 與 $task-handoff.md，把 state 檔 session_id 更新為本 session 的 \$CLAUDE_CODE_SESSION_ID、config_dir 更新為 \$CLAUDE_CONFIG_DIR，再接續下一批）"
      ;;

    # awaiting_user / reported / 未知狀態: 一律不動（只受職責 5 的閒置歸檔）
  esac
done

# ── 職責 4: acceptance 證據清理 ──────────────────────────────
# 任務閒置超過 EVIDENCE_RETENTION_DAYS 天後刪 evidence/ 目錄（截圖等大檔）。
# 驗收清單 .md 位於任務目錄根層，永久保留不受影響。
# 判定「閒置」= 整個任務目錄內沒有任何檔案在保留天數內被動過——
# 用檔案 mtime 而非 state 的 done 時間，因為舊任務的 state 檔已被職責 3 清掉。
EVIDENCE_RETENTION_DAYS=${EVIDENCE_RETENTION_DAYS:-7}
ACCEPT_DIR="$HOME/.claude/acceptance"
for d in "$ACCEPT_DIR"/*/; do
  [ -d "${d}evidence" ] || continue
  task=$(basename "$d")
  # 任務還活著（state 檔存在且狀態非 done）→ 絕不動它的證據
  sf="$STATE_DIR/$task.json"
  if [ -f "$sf" ]; then
    st=$(jq -r '.status // empty' "$sf" 2>/dev/null)
    case "$st" in done|reported) ;; *) continue ;; esac
  fi
  # 保留天數內任務目錄有任何動靜 → 視為仍在使用，跳過
  [ -n "$(find "$d" -type f -mtime -"$EVIDENCE_RETENTION_DAYS" 2>/dev/null | head -1)" ] && continue
  sz=$(du -sh "${d}evidence" 2>/dev/null | cut -f1)
  rm -rf "${d}evidence"
  log "🧹 清理驗收證據 ${task}/evidence（${sz}，任務閒置超過 ${EVIDENCE_RETENTION_DAYS} 天）"
done
exit 0
