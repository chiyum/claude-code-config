#!/usr/bin/env bash
# secrets-sync.sh — 機敏檔跨機器同步（age 加密進 ~/.claude repo，明文永遠 gitignored）
#
# 用法：
#   secrets-sync.sh init            新機器：檢查 age 與私鑰、設 git hooksPath、解密全部
#   secrets-sync.sh encrypt [名稱]  本機明文 → secrets/<名稱>.age（改完 SECRETS 後跑，再 commit）
#   secrets-sync.sh decrypt [名稱]  secrets/<名稱>.age → 明文（git pull 後跑；本機明文較新會拒絕，--force 覆寫並留 .bak）
#   secrets-sync.sh status          每個檔的同步狀態；有 DIRTY/STALE 回 1（pre-commit 用）
#
# 私鑰：~/.config/age/keys.txt（可用 AGE_KEY_FILE 覆寫）。私鑰只放密碼管理器與各機器本機，不進 git、不放雲端明文。
# 清單：secrets/manifest.txt（密文名 明文路徑）；公鑰：secrets/recipients.txt
set -euo pipefail

CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
KEY="${AGE_KEY_FILE:-$HOME/.config/age/keys.txt}"
VAULT="$CLAUDE_DIR/secrets"
MANIFEST="${SECRETS_MANIFEST:-$VAULT/manifest.txt}"
RECIPIENTS="$VAULT/recipients.txt"

die() { echo "secrets-sync: $*" >&2; exit 2; }
need_age() { command -v age >/dev/null || die "未安裝 age（brew install age）"; }
need_key() { [ -s "$KEY" ] || die "找不到私鑰 ${KEY}：從密碼管理器貼入後 chmod 600"; }

# 讀清單：印出「名稱<TAB>展開後的明文路徑」；可選只取一個名稱
entries() {
  local want="${1:-}"
  grep -vE '^\s*(#|$)' "$MANIFEST" | while read -r name path; do
    [ -n "$want" ] && [ "$want" != "$name" ] && continue
    printf '%s\t%s\n' "$name" "${path/#\~/$HOME}"
  done
}

cmd_encrypt() {
  need_age; [ -s "$RECIPIENTS" ] || die "缺 $RECIPIENTS"
  local n=0
  while IFS=$'\t' read -r name plain; do
    if [ ! -f "$plain" ]; then echo "[skip] ${name}：本機沒有 $plain"; continue; fi
    age -R "$RECIPIENTS" -o "$VAULT/$name.age" "$plain"
    echo "[ok]   $name ← $plain → secrets/$name.age"; n=$((n+1))
  done < <(entries "${1:-}")
  [ "$n" -gt 0 ] && echo "接著：git -C $CLAUDE_DIR add secrets/ && git commit"
}

cmd_decrypt() {
  need_age; need_key
  local force=0 want="${1:-}"
  if [ "${2:-}" = "--force" ] || [ "$want" = "--force" ]; then force=1; fi
  if [ "$want" = "--force" ]; then want=""; fi
  while IFS=$'\t' read -r name plain; do
    local cipher="$VAULT/$name.age"
    if [ ! -f "$cipher" ]; then echo "[skip] ${name}：repo 沒有 secrets/$name.age"; continue; fi
    local tmp; tmp="$(mktemp)"
    if ! age -d -i "$KEY" -o "$tmp" "$cipher"; then echo "[fail] ${name}：解密失敗（私鑰不在 recipients？）"; rm -f "$tmp"; continue; fi
    if [ -f "$plain" ] && ! cmp -s "$tmp" "$plain"; then
      if [ "$force" -ne 1 ] && [ "$plain" -nt "$cipher" ]; then
        echo "[refuse] ${name}：本機 $plain 比密文新且內容不同，先 encrypt 或用 --force 覆寫（會留 .bak）"; rm -f "$tmp"; continue
      fi
      local bak="$plain.bak-$(date +%Y%m%d%H%M%S)"; cp -p "$plain" "$bak"; chmod 600 "$bak"
    fi
    mkdir -p "$(dirname "$plain")"; install -m 600 "$tmp" "$plain"; rm -f "$tmp"
    echo "[ok]   $name → $plain"
  done < <(entries "$want")
}

cmd_status() {
  need_age
  local rc=0 quiet="${1:-}"
  while IFS=$'\t' read -r name plain; do
    local cipher="$VAULT/$name.age" st
    if [ ! -f "$cipher" ] && [ ! -f "$plain" ]; then st="absent"
    elif [ ! -f "$cipher" ]; then st="DIRTY（尚未加密，跑 encrypt）"; rc=1
    elif [ ! -f "$plain" ]; then st="STALE（本機無明文，跑 decrypt）"; rc=1
    elif [ ! -s "$KEY" ]; then st="unknown（無私鑰，無法比對）"
    else
      local tmp; tmp="$(mktemp)"
      if age -d -i "$KEY" -o "$tmp" "$cipher" 2>/dev/null && cmp -s "$tmp" "$plain"; then st="in-sync"
      elif [ "$plain" -nt "$cipher" ]; then st="DIRTY（明文有未加密改動，跑 encrypt）"; rc=1
      else st="STALE（密文較新，跑 decrypt）"; rc=1; fi
      rm -f "$tmp"
    fi
    [ "$quiet" = "--quiet" ] && [ "$st" = "in-sync" ] || echo "$name: $st"
  done < <(entries)
  return $rc
}

cmd_init() {
  need_age; need_key
  git -C "$CLAUDE_DIR" config core.hooksPath githooks && echo "[ok] git hooksPath=githooks（pre-commit 會擋未加密的機敏改動）"
  cmd_decrypt
  echo "[done] 新機器就緒；之後流程：改 SECRETS → secrets-sync.sh encrypt → commit/push；另一台 pull → secrets-sync.sh decrypt"
}

case "${1:-}" in
  init) cmd_init ;;
  encrypt) cmd_encrypt "${2:-}" ;;
  decrypt) cmd_decrypt "${2:-}" "${3:-}" ;;
  status) cmd_status "${2:-}" ;;
  *) sed -n '2,12p' "$0"; exit 1 ;;
esac
