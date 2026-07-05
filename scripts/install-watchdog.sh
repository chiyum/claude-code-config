#!/bin/bash
# 看門狗排程安裝器（依賴注入點）
# 設計: watchdog.sh 是平台無關核心，不知道也不關心誰喚醒它；
#       「排程器」是被注入的依賴——本腳本以 uname 偵測平台，注入對應排程器:
#         Darwin        → launchd（LaunchAgent, 每 600 秒）
#         Linux / WSL   → cron（每 10 分鐘）；WSL 另印 Windows 原生工作排程器方案
# 平台差異參數（claude 路徑等）收在 state/watchdog.conf，核心腳本兩平台共用同一份。
# 冪等: 重跑只會覆蓋/更新排程，不會重複安裝。

set -e
SCRIPT="$HOME/.claude/scripts/watchdog.sh"
CONF="$HOME/.claude/state/watchdog.conf"
mkdir -p "$HOME/.claude/state"
chmod +x "$SCRIPT"

# 排程器環境（launchd / cron）沒有互動 shell 的 PATH，claude 執行檔絕對路徑寫進 conf
BIN=$(command -v claude || true)
if [ -n "$BIN" ]; then
  if grep -q '^CLAUDE_BIN=' "$CONF" 2>/dev/null; then
    sed -i.bak "s|^CLAUDE_BIN=.*|CLAUDE_BIN=\"$BIN\"|" "$CONF" && rm -f "$CONF.bak"
  else
    printf 'CLAUDE_BIN="%s"\n' "$BIN" >> "$CONF"
  fi
  echo "CLAUDE_BIN = $BIN"
else
  echo "⚠️ 找不到 claude 執行檔，請手動在 $CONF 設 CLAUDE_BIN"
fi

case "$(uname -s)" in
  Darwin)
    PLIST="$HOME/Library/LaunchAgents/com.user.claude-watchdog.plist"
    cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.user.claude-watchdog</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$SCRIPT</string>
  </array>
  <key>StartInterval</key><integer>600</integer>
  <key>RunAtLoad</key><false/>
  <key>StandardOutPath</key><string>$HOME/.claude/state/watchdog.launchd.log</string>
  <key>StandardErrorPath</key><string>$HOME/.claude/state/watchdog.launchd.log</string>
</dict>
</plist>
EOF
    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl load "$PLIST"
    echo "✅ macOS launchd 已載入（每 600 秒喚醒）: $PLIST"
    echo "   移除: launchctl unload $PLIST && rm $PLIST"
    ;;

  Linux)
    IS_WSL=""
    grep -qi microsoft /proc/version 2>/dev/null && IS_WSL=1
    LINE="*/10 * * * * /bin/bash $SCRIPT"
    ( crontab -l 2>/dev/null | grep -vF "$SCRIPT"; echo "$LINE" ) | crontab -
    echo "✅ cron 已安裝（每 10 分鐘）: $LINE"
    if [ -n "$IS_WSL" ]; then
      echo ""
      echo "偵測到 WSL。cron 依賴 WSL instance 存活；若要 WSL 沒開也能拉起（更穩），"
      echo "改用 Windows 原生工作排程器——以系統管理員在 PowerShell 執行:"
      echo "  schtasks /Create /TN ClaudeWatchdog /SC MINUTE /MO 10 /TR \"wsl.exe -e /bin/bash $SCRIPT\" /F"
      echo "（兩者擇一即可；都裝也無妨，watchdog.sh 有單實例鎖不會打架）"
    fi
    ;;

  *)
    echo "❌ 未支援平台: $(uname -s)（Windows 原生請透過 WSL 或工作排程器 + wsl.exe 執行）"
    exit 1
    ;;
esac
