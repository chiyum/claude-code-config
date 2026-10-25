#!/bin/bash
# 任務收工清理（state 標 done 時由主 Claude 呼叫；看門狗職責 4 以 --sweep 接漏網）
#
# 目的：任務標 done 的同一個動作裡，把該任務的執行期大檔清掉，只留制度與歷史檔。
#   刪：acceptance/<slug>/**/evidence/（截圖、影片、apk、log）
#       state/<slug>/ 底下的子目錄（runtime、decompiled、venv、publication 等執行期暫存）
#       worktrees/*<slug>*（git worktree 走 git worktree remove；純目錄直接刪）
#   留：驗收清單 .md、handoff / questions / state json、ADR、知識卡、規格、completion-report、
#       state/<slug>/ 頂層的小檔（env.sh、show.py 之類）
#   刪前先寫 evidence-manifest.txt（大小 / mtime / sha256 / 路徑），幾 KB，供日後追溯「當時驗了什麼」
#
# 用法：
#   cleanup-task.sh <slug> [--apply]        單一任務；預設 dry-run 只列清單與大小，--apply 才真刪
#   cleanup-task.sh --sweep [--apply]       看門狗用：掃所有任務，done 立刻清、reported / 無 state 閒置滿 N 天才清
#   cleanup-task.sh --backlog               一次性報表：列出所有任務的 status / 閒置天數 / 可回收大小，不刪
#   cleanup-task.sh --orphans [--apply]     對不到任何任務的孤兒 worktree：只移除「乾淨＋已合進 main＋閒置滿 N 天」的
#   環境變數：EVIDENCE_RETENTION_DAYS（預設 7）、CLEANUP_ROOTS（預設 "$HOME/.claude"；可放多個根目錄，空白分隔）
#
# 護欄（腳本自己擋，不靠人記）：
#   1. state 是 running / awaiting_user / awaiting_next_batch / in_progress / retry_exhausted → 一律不動
#   2. 目標目錄有程序開著檔案（lsof）→ 跳過並回報
#   3. git worktree 有未 commit 變更、或分支未合進 main → 跳過並回報，不強刪
#   4. 每筆刪除寫一行到 ~/.claude/state/cleanup.log
#   5. 絕不碰 specs、products、knowledge；只動 acceptance / state / worktrees 三個目錄
set -u
RETENTION=${EVIDENCE_RETENTION_DAYS:-7}
ROOTS=${CLEANUP_ROOTS:-"$HOME/.claude"}
MODE=single; APPLY=0; SLUG=""
for a in "$@"; do case "$a" in
  --apply) APPLY=1 ;; --sweep) MODE=sweep ;; --backlog) MODE=backlog ;; --orphans) MODE=orphans ;;
  -h|--help) sed -n 2,27p "$0"; exit 0 ;;
  --*) echo "未知參數 $a" >&2; exit 2 ;; *) SLUG="$a" ;;
esac; done
[ "$MODE" = single ] && [ -z "${SLUG}" ] && { echo "用法：cleanup-task.sh <slug> [--apply] | --sweep [--apply] | --backlog" >&2; exit 2; }

now=$(date +%s)
log(){ # $1 = 目標路徑（保留參數位置，方便多根目錄時擴充），其餘為訊息
  shift; mkdir -p "$HOME/.claude/state"; echo "[$(date '+%F %T')] $*" >> "$HOME/.claude/state/cleanup.log"; }
say(){ echo "$*"; }
hsize(){ du -sh "$1" 2>/dev/null | cut -f1; }
kbsize(){ du -sk "$1" 2>/dev/null | cut -f1; }
# 目錄內最新 mtime 距今幾天（空目錄回 9999）
idle_days(){ local newest; newest=$(find "$1" -type f -print0 2>/dev/null | xargs -0 stat -f %m 2>/dev/null | sort -n | tail -1)
  [ -z "$newest" ] && { echo 9999; return; }; echo $(( (now - newest) / 86400 )); }
# 快速判定：目錄在 N 天內有沒有任何檔案被動過（找到第一個就停，大目錄不必全掃）
touched_within(){ [ -n "$(find "$1" -type f -mtime -"$2" -print -quit 2>/dev/null)" ]; }
busy(){ lsof +D "$1" >/dev/null 2>&1; }   # 有程序開著檔案 → 0

# state 狀態：找各根目錄的 live state（archive 不算 live）；多份時取「最嚴格」的那份
# 正規化：done|complete|completed → done；reported；其餘活躍狀態原樣回傳；找不到 → none
task_status(){ local slug="$1" st s r; st=none
  for r in $ROOTS; do local f="$r/state/$slug.json"; [ -f "$f" ] || continue
    s=$(jq -r '.status // empty' "$f" 2>/dev/null)
    case "$s" in done|complete|completed) s=done ;; ''|null) s=unknown ;; esac
    case "$s" in running|awaiting_user|awaiting_next_batch|in_progress|retry_exhausted) echo "$s"; return ;; esac
    case "$st:$s" in none:*) st=$s ;; done:reported|done:unknown|reported:unknown) st=$s ;; esac
  done; echo "$st"; }
task_dirs(){ local slug="$1" r; for r in $ROOTS; do for d in "$r/acceptance/$slug" "$r/state/$slug"; do [ -d "$d" ] && echo "$d"; done; targets_worktree "$slug"; done; }
task_idle(){ local slug="$1" d m=9999 v; while IFS= read -r d; do [ -n "$d" ] || continue
  v=$(idle_days "$d"); [ "$v" -lt "$m" ] && m=$v; done < <(task_dirs "$slug"); echo "$m"; }
# 便宜版：任務目錄在保留天數內有沒有動靜（sweep 用，避免對每個大目錄全掃 stat）
task_active_recently(){ local slug="$1" d; while IFS= read -r d; do [ -n "$d" ] || continue
  touched_within "$d" "$RETENTION" && return 0; done < <(task_dirs "$slug"); return 1; }
# 判定能不能清：done → 可；reported / none / unknown → 閒置滿 N 天才可；活躍狀態 → 不可
eligible(){ local st="$1" idle="$2"
  case "$st" in done) return 0 ;; reported|none|unknown) [ "$idle" -ge "$RETENTION" ] ;; *) return 1 ;; esac; }

# 蒐集目標：evidence 目錄、state/<slug>/ 子目錄、worktrees
targets_evidence(){ local slug="$1" r; for r in $ROOTS; do [ -d "$r/acceptance/$slug" ] && find "$r/acceptance/$slug" -maxdepth 6 -type d -name evidence 2>/dev/null; done; }
targets_state_sub(){ local slug="$1" r; for r in $ROOTS; do [ -d "$r/state/$slug" ] && find "$r/state/$slug" -mindepth 1 -maxdepth 1 -type d 2>/dev/null; done; }
# worktree 名稱與 slug 常互為子字串（worktree "20261005-att-reports" vs slug "20261005-shop-att-reports"）：
# 雙向比對——worktree 名含 slug、或 slug 含 worktree 名（名稱至少 12 字避免誤配日期前綴）
wt_matches(){ local n="$1" slug="$2"; case "$n" in *"$slug"*) return 0 ;; esac
  [ ${#n} -ge 12 ] && case "$slug" in *"$n"*) return 0 ;; esac; return 1; }
targets_worktree(){ local slug="$1" r w n; for r in $ROOTS; do [ -d "$r/worktrees" ] || continue
  for w in "$r"/worktrees/*/; do [ -d "$w" ] || continue; n=$(basename "$w"); wt_matches "$n" "$slug" && echo "${w%/}"; done; done; }

write_manifest(){ # $1 = evidence 目錄 → 同層 evidence-manifest.txt（已存在則附加新段落）
  local d="$1" out; out="$(dirname "$d")/evidence-manifest.txt"
  { echo "# cleanup $(date -Iseconds)  source=$d  total=$(hsize "$d")"; echo "# bytes	mtime	sha256	path"
    find "$d" -type f -print0 2>/dev/null | while IFS= read -r -d '' f; do
      printf '%s\t%s\t%s\t%s\n' "$(stat -f %z "$f")" "$(stat -f %Sm -t %FT%T "$f")" "$(shasum -a 256 "$f" | cut -d' ' -f1)" "${f#$d/}"; done; } >> "$out"
  echo "$out"; }

remove_dir(){ # $1 = 目錄；dry-run 只印
  local d="$1" sz; sz=$(hsize "$d")
  if busy "$d"; then say "  ⏸  跳過（有程序開著檔案）$d ($sz)"; return 1; fi
  if [ "$APPLY" = 1 ]; then rm -rf "$d" && { say "  🧹 已刪 $d ($sz)"; log "$d" "🧹 ${SLUG} 刪 $d ($sz)"; } || say "  ❌ 刪除失敗 $d"
  else say "  🔍 將刪 $d ($sz)"; fi; }

remove_worktree(){ local w="$1" sz main br
  sz=$(hsize "$w")
  if busy "$w"; then say "  ⏸  跳過 worktree（有程序開著檔案）$w"; return; fi
  if [ -f "$w/.git" ]; then                       # 真正的 git worktree
    main=$(git -C "$w" rev-parse --path-format=absolute --git-common-dir 2>/dev/null); main=${main%/.git}
    br=$(git -C "$w" branch --show-current 2>/dev/null)
    if [ -n "$(git -C "$w" status --porcelain 2>/dev/null)" ]; then say "  ⏸  跳過 worktree（有未 commit 變更）$w ($sz)"; log "$w" "⏸ ${SLUG} worktree 未 commit，保留 $w"; return; fi
    if [ -n "$br" ] && [ "$br" != main ] && ! git -C "$main" branch --merged main 2>/dev/null | grep -qx "[* ]*$br"; then
      say "  ⏸  跳過 worktree（分支 $br 未合進 main）$w ($sz)"; log "$w" "⏸ ${SLUG} worktree 分支 $br 未合併，保留 $w"; return; fi
    if [ "$APPLY" = 1 ]; then
      git -C "$main" worktree remove --force "$w" >/dev/null 2>&1 || rm -rf "$w"
      git -C "$main" worktree prune >/dev/null 2>&1
      [ -n "$br" ] && [ "$br" != main ] && git -C "$main" branch -d "$br" >/dev/null 2>&1
      say "  🧹 已移除 worktree $w ($sz, 分支 $br)"; log "$w" "🧹 ${SLUG} 移除 worktree $w ($sz, 分支 ${br:-?})"
    else say "  🔍 將移除 worktree $w ($sz, 分支 ${br:-?}, repo $main)"; fi
  else remove_dir "$w"; fi; }

clean_one(){ # $1 = slug；回 0 = 有處理（或 dry-run 列出），1 = 不符資格
  SLUG="$1"; local st idle any=0 d
  st=$(task_status "${SLUG}"); idle=$(task_idle "${SLUG}")
  if ! eligible "$st" "$idle"; then
    say "⛔ ${SLUG}：status=$st 閒置 ${idle} 天 → 不清（done 才立清；reported / 無 state 要閒置滿 ${RETENTION} 天）"; return 1; fi
  say "▶ ${SLUG}：status=$st 閒置 ${idle} 天 $([ "$APPLY" = 1 ] && echo '[APPLY]' || echo '[dry-run]')"
  while IFS= read -r d; do [ -n "$d" ] || continue; any=1
    [ "$APPLY" = 1 ] && ! busy "$d" && say "  📝 manifest → $(write_manifest "$d")"
    remove_dir "$d"; done < <(targets_evidence "${SLUG}")
  while IFS= read -r d; do [ -n "$d" ] || continue; any=1; remove_dir "$d"; done < <(targets_state_sub "${SLUG}")
  while IFS= read -r d; do [ -n "$d" ] || continue; any=1; remove_worktree "$d"; done < <(targets_worktree "${SLUG}")
  [ "$any" = 0 ] && say "  （沒有可清的目標）"; return 0; }

all_slugs(){ local r; for r in $ROOTS; do
  [ -d "$r/acceptance" ] && find "$r/acceptance" -mindepth 1 -maxdepth 1 -type d -exec basename {} \;
  [ -d "$r/state" ] && find "$r/state" -mindepth 1 -maxdepth 1 -type d ! -name archive ! -name runtime ! -name '.*' -exec basename {} \;
  done | sort -u; }
ALL_SLUGS=""   # all_slugs 要 find 上千個目錄，只算一次
cached_slugs(){ [ -n "$ALL_SLUGS" ] || ALL_SLUGS=$(all_slugs); printf '%s\n' "$ALL_SLUGS"; }
# 孤兒判定：worktree 名稱對不到任何 slug
is_orphan(){ local n="$1" s; while IFS= read -r s; do [ -n "$s" ] && wt_matches "$n" "$s" && return 1; done < <(cached_slugs); return 0; }

case "$MODE" in
  single) clean_one "${SLUG}" ;;
  sweep)  # 只處理有可清目標的任務；不符資格的靜默略過（看門狗每 10 分鐘跑，不能灌 log）
    while IFS= read -r s; do
      st=$(task_status "$s")
      case "$st" in done) ;; reported|none|unknown) task_active_recently "$s" && continue ;; *) continue ;; esac
      [ -n "$(targets_evidence "$s"; targets_state_sub "$s"; targets_worktree "$s")" ] || continue
      clean_one "$s"; done < <(cached_slugs) ;;
  orphans) # 對不到任何任務的孤兒 worktree：只動「乾淨 + 已合進 main + 閒置滿 N 天」的；其餘列出留人工
    for r in $ROOTS; do [ -d "$r/worktrees" ] || continue; for w in "$r"/worktrees/*/; do w=${w%/}; n=$(basename "$w")
      is_orphan "$n" || continue
      if touched_within "$w" "$RETENTION"; then say "  ⏸  孤兒 worktree 近 ${RETENTION} 天有動靜，保留 $w ($(hsize "$w"))"; continue; fi
      SLUG="orphan"; remove_worktree "$w"; done; done ;;
  backlog) # 報表：slug / status / 閒置天 / 可回收 / 資格
    printf '%-10s %-6s %8s  %-8s %s\n' status idle recl_MB elig slug
    while IFS= read -r s; do
      kb=0; for d in $(targets_evidence "$s"; targets_state_sub "$s"; targets_worktree "$s"); do kb=$((kb + $(kbsize "$d"))); done
      [ "$kb" -gt 0 ] || continue
      st=$(task_status "$s"); idle=$(task_idle "$s"); e=no; eligible "$st" "$idle" && e=YES
      printf '%-10s %-6s %8d  %-8s %s\n' "$st" "$idle" $((kb/1024)) "$e" "$s"; done < <(cached_slugs) | sort -k3 -n -r
    echo "# 孤兒 worktree（名稱對不到任何 acceptance / state slug；用 --orphans [--apply] 只清乾淨＋已合併＋閒置的，其餘人工）："
    for r in $ROOTS; do [ -d "$r/worktrees" ] || continue; for w in "$r"/worktrees/*/; do n=$(basename "$w")
      is_orphan "$n" && echo "  $(hsize "$w")	$w"; done; done ;;
esac
