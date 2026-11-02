#!/usr/bin/env bash
# Claude Code PreToolUse hook（matcher: Bash）：擋「沒有到期機制的背景等待迴圈」
#
# 為什麼要有這支：四次「主 Claude 整晚空等」事故的共同點都是
# 主 Claude 掛了一支背景 until／while 迴圈盯產物，但迴圈沒有 timeout（或盯的檔名是猜的），
# 迴圈永遠不結束，主 Claude 就永遠不會被喚醒。LANE_PROTOCOL 第 9 條字句補了兩次仍再犯，
# 所以改由這支 hook 確定性地擋：背景 Bash 含 until / while true / while : 卻沒有 timeout，就拒絕。
#
# 行為：
#   - 只看 tool_name == Bash 且 run_in_background == true 的呼叫；其餘一律放行（exit 0）
#   - 指令含 `until ` / `while true` / `while :` / `while [ 1 ]` 且不含 `timeout ` → exit 2（阻擋，stderr 給 Claude 看）
#   - 任何解析失敗都放行，不得因為 hook 自己壞掉卡住 session
#
# 自測（負向對照）：bash guard-background-wait.sh --selftest

set -u

selftest() {
  local fail=0
  run() { printf '%s' "$2" | bash "$0"; local rc=$?; if [ "$rc" -ne "$1" ]; then echo "FAIL expect=$1 got=$rc: $2"; fail=1; else echo "ok   rc=$rc: ${3}"; fi; }
  run 2 '{"tool_name":"Bash","tool_input":{"command":"until ls /tmp/x.log; do sleep 5; done","run_in_background":true}}' "背景 until 無 timeout → 擋"
  run 2 '{"tool_name":"Bash","tool_input":{"command":"while true; do sleep 9; done","run_in_background":true}}' "背景 while true 無 timeout → 擋"
  run 0 '{"tool_name":"Bash","tool_input":{"command":"timeout 900 bash -c '"'"'until ls /tmp/x.log; do sleep 5; done'"'"'","run_in_background":true}}' "背景 until 有 timeout → 放行"
  run 0 '{"tool_name":"Bash","tool_input":{"command":"until ls /tmp/x.log; do sleep 5; done","run_in_background":false}}' "前景 until → 放行（Bash 工具本身有上限）"
  run 0 '{"tool_name":"Bash","tool_input":{"command":"ls -la","run_in_background":true}}' "背景非迴圈 → 放行"
  run 0 '{"tool_name":"Read","tool_input":{"file_path":"/tmp/a"}}' "非 Bash → 放行"
  run 0 'not json' "壞 payload → 放行"
  return $fail
}

[ "${1:-}" = "--selftest" ] && { selftest; exit $?; }

command -v jq >/dev/null 2>&1 || exit 0
payload=$(cat) || exit 0

tool_name=$(printf '%s' "$payload" | jq -r '.tool_name // empty' 2>/dev/null) || exit 0
[ "$tool_name" = "Bash" ] || exit 0

in_bg=$(printf '%s' "$payload" | jq -r '.tool_input.run_in_background // false' 2>/dev/null) || exit 0
[ "$in_bg" = "true" ] || exit 0

cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null) || exit 0
[ -n "$cmd" ] || exit 0

# 有等待迴圈嗎
if ! printf '%s' "$cmd" | grep -Eq '(^|[;&|[:space:]])until[[:space:]]|while[[:space:]]+true|while[[:space:]]+:|while[[:space:]]+\[[[:space:]]*1[[:space:]]*\]'; then
  exit 0
fi

# 有到期機制嗎（timeout 指令包住）
if printf '%s' "$cmd" | grep -Eq '(^|[;&|[:space:]])timeout[[:space:]]+[0-9]'; then
  exit 0
fi

cat >&2 <<'MSG'
已擋下：背景等待迴圈沒有到期機制，掛了之後若目標永遠不出現，你永遠不會被喚醒（實測曾因此空等 9 小時）。
改法擇一：
  1. 用 Monitor 工具（自帶 30 分鐘到期通知）
  2. 迴圈外面包 timeout，例如：timeout 900 bash -c 'until ls <檔>; do sleep 10; done'
另外：掛之前先 ls 確認監看目標的目錄／檔名真的存在，猜出來的檔名不准當監看目標（LANE_PROTOCOL 第 9 條）。
MSG
exit 2
