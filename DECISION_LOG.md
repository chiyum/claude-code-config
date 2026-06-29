# 決策紀錄制度（ADR — Architecture Decision Record）

> 這份文件是「決策紀錄」這套制度的單一真相來源。主 Claude、architect、以及使用者本人都依這份運作。
> 目的：把每一次「為什麼這樣決定」留存下來，供未來的你我（不論人或 Claude）回頭查證，避免「後人不知道前人為何這樣寫」。

## 一、核心模式：混合存放

決策分兩類，存放位置不同：

| 決策類型 | 存放位置 | 範例 |
|---|---|---|
| **產品相關決策**（綁某個 repo / 產品）| 該 repo 內 `docs/adr/`，**同時**在 `~/.claude/products/<product>.md` 加一行索引 | 「系統 X 改用 Go 重構」「派單改 weighted round-robin」「可見性語義翻轉」 |
| **跨產品 / 個人工作流決策**（不屬任何單一產品）| `~/.claude/`（CLAUDE.md 或獨立檔）| 「GitHub 多帳號規則」「標準開發流程」 |

判斷原則：**「這個決策換到別的專案還成立嗎？」** 成立 → 放 `~/.claude`；只對這個產品成立 → 放該 repo `docs/adr/`。

## 二、repo 內目錄結構

```
docs/
  adr/
    README.md            ← 索引表（每新增一筆 ADR 就補一列）
    0001-xxxx.md
    0002-xxxx.md
    ...
```

- 檔名：`NNNN-kebab-case-標題.md`，4 位數補零、**每個 repo 各自單調遞增**。
- 標題可用本地語言，但檔名 slug 用英文 kebab-case。

## 三、什麼時候寫（觸發門檻）

走「決策當下立即記」：**做出以下任一種決策時，當下就寫一筆 ADR，和 code + 規格放同一個 commit。**

會觸發（值得記）：
- 語言 / 框架 / 主要函式庫的選型
- 重大架構模式（單體 vs 前後分離、同步 vs 事件驅動、ORM 層 vs service 層擋…）
- 資料庫 / 儲存 / 快取的選型或結構性決定
- 重大取捨（效能 vs 簡潔、一致性 vs 可用性、自建 vs 第三方）
- **回滾成本高或不可逆**的決定
- **推翻先前決策**（新 ADR 註明 supersedes ADR-NNNN，並把舊 ADR 狀態改 Superseded）

不需要寫：一般 bug 修復、小重構、命名/樣式微調、純照既有規格實作、探索 / 讀 code。

模糊時：**「半年後有人問『當初為什麼這樣選』，我會希望有紀錄嗎？」** 會 → 寫。

## 四、ADR 範本

```markdown
# ADR-NNNN: <一句話標題>

- 日期：YYYY-MM-DD
- 狀態：Proposed | Accepted | Superseded by ADR-NNNN | Deprecated
- 決策者：<使用者> / Claude（architect）

## 背景與需求
（什麼情境、什麼需求或限制逼出這個決策？）

## 決策
（最後決定怎麼做，一句話能講完最好。）

## 考慮過的替代方案
1. 方案 A —— 否決原因 / 取捨
2. 方案 B —— 否決原因 / 取捨

## 後果與風險
- 好處：
- 壞處 / 技術債：
- 回滾難度：低 / 中 / 高（為什麼）

## 關聯
（相關 ADR、規格檔、commit hash、memory 檔名。）
```

> 若走「三方案分析模式」，三個方案本來就要列出來——直接把分析濃縮進「考慮過的替代方案」即可。

## 五、索引（兩處都要）

1. **repo 內 `docs/adr/README.md`**：每新增一筆補一列。
   ```markdown
   | ADR | 標題 | 日期 | 狀態 |
   |---|---|---|---|
   | [0001](0001-example.md) | <標題> | YYYY-MM-DD | Accepted |
   ```

2. **`~/.claude/products/<product>.md` 的「規格書與文件」區塊**：該產品**第一次**寫 ADR 時加一行指向 README：
   ```markdown
   | 決策紀錄 (ADR) | `<repo>/docs/adr/README.md` |
   ```

## 六、誰負責寫

- 走標準開發流程時 → **architect** 在實作的同一個 commit 裡寫 ADR。
- 使用者口頭拍板的決策 → 可直接叫主 Claude「把這個決策記一筆 ADR」，主 Claude 代寫。
- reviewer 審查時發現「該記卻沒記」的重大決策 → 在回報裡點出「缺 ADR」。
