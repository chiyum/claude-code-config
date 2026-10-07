#!/bin/bash
# verify-evidence: QA/PM 驗收後、主 Claude 放行前的確定性證據檢查
# 用法: verify-evidence.sh <驗收清單檔路徑>
#   例: bash ~/.claude/scripts/verify-evidence.sh ~/.claude/acceptance/20260706-xxx.md
# 退出碼: 0=每條驗收條目都有證據檔, 1=有條目缺證據（不得放行，退回 QA/PM 補證據或重驗）
#
# 規約（見 ~/.claude/acceptance/README.md）:
#   - 清單條目標題格式: 「### <字母><數字> <行為描述>」（A1 / B3 皆可；同一份清單可混用不同字母前綴）
#   - 證據目錄: 與清單同名的目錄 + /evidence/（清單 20260706-xxx.md → 20260706-xxx/evidence/）
#   - 證據檔名必含「<條目ID>-」前綴段（qa-A1-登入畫面.png / qa-B3-scorer.py），A1- 不會誤配 A10-
#
# 外部規格模式（2026-09 起，規約見 ~/.claude/acceptance/EXTERNAL_SPEC_PROTOCOL.md）：
#   verify-evidence.sh --spec <SPEC.md> --evidence-dir <run>/local|dev [--environment local|dev]
#                      [--index <evidence-index.json>] [--expected-sha256 <state hash>] [--run-id RUN-...]
#   偵測到 --spec 即轉交 verify-evidence-external.py（多驗 evidence-index、hash 綁定、雙軌、dev 版本）。
#   舊的單一位置參數用法完全不變。

case "$1" in
  --spec|--evidence-dir|--environment|--index|--expected-sha256|--run-id)
    exec python3 "$(dirname "$0")/verify-evidence-external.py" "$@"
    ;;
esac

LIST="$1"
if [ -z "$LIST" ] || [ ! -f "$LIST" ]; then
  echo "❌ 找不到驗收清單: $LIST"
  echo "用法: verify-evidence.sh <驗收清單檔路徑>"
  exit 1
fi

EVIDENCE_DIR="${LIST%.md}/evidence"
IDS=$(grep -oE '^### [A-Z][0-9]+' "$LIST" | awk '{print $2}' | sort -u)

if [ -z "$IDS" ]; then
  echo "❌ 清單內找不到任何「### <字母><數字>」格式的驗收條目（如 ### A1 / ### B3），請先把清單升級為新格式（見 acceptance/README.md）"
  exit 1
fi

if [ ! -d "$EVIDENCE_DIR" ]; then
  echo "❌ 證據目錄不存在: $EVIDENCE_DIR"
  echo "   QA/PM 必須把截圖 / curl 輸出以「<qa|pm>-<條目ID>-<說明>」命名存入該目錄"
  exit 1
fi

FAIL=0
for id in $IDS; do
  # 檔名須含「A<n>-」段，尾端的 - 防止 A1 誤配 A10
  MATCHES=$(find -L "$EVIDENCE_DIR" -maxdepth 1 -type f -name "*${id}-*" | wc -l | tr -d ' ')
  if [ "$MATCHES" -eq 0 ]; then
    echo "❌ 條目 $id 沒有任何證據檔（需至少一個 *${id}-* 檔案於 $EVIDENCE_DIR）"
    FAIL=1
  else
    echo "✅ $id: ${MATCHES} 個證據檔"
    find -L "$EVIDENCE_DIR" -maxdepth 1 -type f -name "*${id}-*" -exec basename {} \; | sed 's/^/     - /'
  fi
done

if [ "$FAIL" -eq 1 ]; then
  echo ""
  echo "❌ 證據不完整：缺證據的條目不得視為通過。退回 QA/PM 補做該條驗證並落地證據，不要只補檔名。"
  exit 1
fi

echo ""
echo "✅ 證據完整性通過。提醒主 Claude：放行前仍須親自抽驗 1-2 張關鍵截圖內容是否與條目宣稱相符。"
exit 0
