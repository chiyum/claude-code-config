# 切版設計參考流程（DESIGN.md 整合指南）

> 這份文件指示 Claude：**只有在我明確要求「設計 / 切版 / 做版面視覺」時**，才去參考
> `awesome-design-md` 的 `DESIGN.md`，並把選定的設計系統「融入本專案既有的設定」。
> 平時的功能修改、bug 修復、既有版型微調，一律**不觸發**這份流程。

---

## 0. 設定

- **awesome-design-md 位置**：`<你的 design-md 目錄>`（例如 `~/Documents/ai/awesome-design-md`，自行調整）
  （若該目錄不存在，提醒我先 clone：
  `git clone https://github.com/VoltAgent/awesome-design-md.git <你的 design-md 目錄>`）
- **預設參考風格**：無。**每次要做設計時都先問我用哪一份**，不要自己預設或沿用上次。

DESIGN.md 檔案位置：`<你的 design-md 目錄>/design-md/<網站名>/DESIGN.md`
（每個資料夾另有 `preview.html` / `preview-dark.html` 可先預覽風格）

---

## 1. ⚠️ 觸發條件（動手前一定先判斷）

### 1.1 要套用這份流程的情況

只有當我的指令**明確含有設計 / 切版 / 視覺 / 風格 / 版面** 的意圖時才啟用，例如：

- 「幫我**設計**這個登入頁的版面」
- 「這個 dashboard **重新切版**，用 Linear 的風格」
- 「做一個**新頁面 / 新元件**，視覺照 `DESIGN.md`」
- 「把這頁**換成 ◯◯ 的設計風格**」
- 「這個版面**重做視覺**」

### 1.2 絕對不要套用的情況（預設行為）

當我只是要改既有版型、修功能、調邏輯，而**沒有提到設計**時，**完全不要碰設計系統**，照我說的做就好。以下都屬於「不觸發」：

- 「把這個按鈕移到右邊」 / 「這兩個欄位對調」
- 「這個 dialog 關掉後要 reset 表單」
- 「修這個對齊跑掉的 bug」
- 「把這個 list 改成虛擬滾動」
- 「這個 component 邏輯重構一下」
- 「加一個 loading 狀態 / 錯誤提示」
- 任何**沒有設計字眼**、只是針對**既有版型**的調整或修正

### 1.3 判斷準則

- **有疑慮時，預設「不觸發」。** 寧可先問我一句：「這次需要套用 `DESIGN.md` 設計流程嗎？」也不要自作主張把整套設計系統套到我只想小修的地方。
- 「改既有版型」≠「設計」。除非我說了設計 / 切版 / 風格，否則把既有版型當成不可任意更動的現狀，只做我指定的那一處。
- 即使這次有觸發，也**只套用到我請你設計的那個範圍**（那一頁 / 那一個元件），不要順手去改其他既有畫面。

---

## 2. 觸發後的流程

### 2.1 確認來源

**每次觸發都要先問我用哪一份 DESIGN.md，不要自己挑、也不要沿用上次。**
列出 `<你的 design-md 目錄>/design-md/` 底下可用的風格選項給我選，等我指定後再往下做。

### 2.2 先讀懂專案既有設定（融入，不是另立一套）

動工前先偵測本專案目前怎麼管理樣式 token，之後**沿用既有結構去擴充**，不要新建一套平行體系，也不要覆蓋既有慣例：

- Quasar 專案：找 `quasar.variables.scss`、`quasar.config.(js|ts)` 的 `brand`、以及任何既有的 SCSS / CSS 變數檔。
- 若有自訂 design token 檔（SCSS map、CSS custom properties、TS 常數）→ 以它為主要落點。
- Tailwind 專案：以 `tailwind.config` 的 `theme.extend` 為落點。

**原則**：DESIGN.md 是「來源」，專案既有 token 檔是「目的地」。把來源映射進目的地的既有命名與結構，缺什麼才新增，不要改動與本次設計無關的既有變數。

### 2.3 映射並套用

依「第 3 節對應規則」把 DESIGN.md 的 token 對進專案既有設定，然後只在我指定的頁面 / 元件上使用這些 token 切版。完成後簡述：用了哪份 DESIGN.md、新增 / 對應了哪些 token、動到哪些檔案。

---

## 3. DESIGN.md → 專案對應規則（以 Quasar 為主）

DESIGN.md 上半是 YAML token，下半是設計脈絡散文。YAML 直接拿來映射，散文用來理解「為什麼這樣用」（例如某色只用在 CTA、display 一律 weight 400 等），切版時要遵守散文裡的 Do's / Don'ts。

| DESIGN.md 區塊 | Quasar 落點 | 說明 |
|---|---|---|
| `colors`（核心品牌色） | `quasar.config` 的 `brand` 或 `quasar.variables.scss` 的 `$primary/$secondary/$accent/$dark/$positive/$negative/$info/$warning` | 把語意最接近的主色對應到 Quasar 品牌變數 |
| `colors`（其餘 surface / text / hairline 等） | 專案 SCSS 變數或 CSS custom properties（沿用既有命名風格） | Quasar 品牌變數裝不下的，放自訂 token，**保留 DESIGN.md 的語意名稱**（如 `canvas`、`ink`、`muted`） |
| `typography` | SCSS 變數 / CSS 變數的字級階層 | 完整搬 fontFamily / size / weight / lineHeight / letterSpacing；字體買不到時用 DESIGN.md 標註的開源替代 |
| `spacing` | 既有間距 token，或對應到 Quasar 的 spacing 慣例 | 維持其尺度系統，不要隨手填數值 |
| `rounded` | `$generic-border-radius` + 自訂圓角變數 | 依 DESIGN.md 的階層（按鈕 / 卡片 / hero 各自的圓角） |
| `components` | 切版時的對照表 | YAML 裡每個元件的 token 組合，是你做按鈕 / 卡片 / 輸入框時的依據，對應到 Quasar 元件的 props / class / style |

非 Quasar 專案（Tailwind / 純 CSS）：同樣邏輯，落點換成 `tailwind.config` 的 theme 或 `:root` 的 CSS 變數即可。

---

## 4. 重要原則（每次都遵守）

1. **融入既有設定**：擴充專案現有 token 結構，不另建平行體系，不覆蓋無關的既有變數。
2. **只動指定範圍**：只對我這次請你設計的頁面 / 元件套用，不順手重設計其他既有畫面。
3. **token 引用而非寫死**：切版時引用對應好的變數，不要把 hex / px 直接散落在元件裡。
4. **遵守 DESIGN.md 的脈絡**：散文裡的 Do's / Don'ts、字重、字距等規則要照做，不只搬色碼。
5. **品牌識別提醒**：這些 DESIGN.md 抽自知名網站，視覺會很像對方品牌。若這是要正式上線的產品畫面，套用後提醒我「目前風格貼近 ◯◯，建議再調成自有識別」。
6. **不確定就停下來問**，尤其是觸發判斷（第 1 節）與風格來源（2.1）。

---

## 5. 互動與動效補充

若你另外維護動效規格檔（例如 `~/.claude/DESIGN_MOTION.md`），動效的取捨（先依互動目的與操作頻率決定「動畫 / 即時切換」，刻意無動效也是有效規格）、動態 / 實機證據邊界依該檔；品牌選擇與既有 token 映射沿用本檔。動效參考不改變原有觸發判準、凍結規則或 architect 唯一寫入規則。全新頁面的精簡規格例外仍依 `~/.claude/CLAUDE.md` 的設計鏈條款。
