# 2025-2026 可轉債量化策略平台與執行軌道圖 - 實作報告

我們已經成功建立並驗證了**可轉債策略交易平台**，包含每日監控 SOP 路線圖（高鐵/捷運路線圖風格）以及歷史最佳優化策略成功案例庫。

---

## 🛠️ 實作項目與變動

### 1. 執行中 SOP 軌道監控與數據生成
* **每日監控腳本** ([daily_monitor.py](file:///d:/bond/backend/daily_monitor.py))：生成 `active_tracks.json` 數據。模擬追蹤公會發布之最新競拍公告，並依 SOP 自動進行 $T-15$ 籌碼判定、買入與賣出動作。
* **狀態劃分**：
  * **博智二 (8155)**：已通過籌碼篩選（外資累積買超 > 2,000張），進入買入持有階段，帳面報酬 **+5.26%**。
  * **威剛八 (3260)**：剛公告發行，處於 `T-16` 競拍公告中，靜待 `T-15`（6/22）籌碼判定。
  * **志皓二 (2467)**：在 `T-15` 籌碼判定失敗（外資僅 120 張），自動剔除交易（Failed/Skipped）。

### 2. 前端高鐵/捷運風格軌道圖 (Subway Route Map)
* **CSS/JS 動態渲染**：在 `index.css` 與 `app.js` 中實作了橫向捷運軌道樣式，包含站點圓圈、路線進度條、呼吸燈提示（當前站點閃爍動畫）及懸浮詳細說明 Tooltips。
* **多標的同步顯示**：首頁可同時呈現威剛、博智、志皓等不同股票的獨立捷運路線圖，讓目前交易進度一目了然。

### 3. 歷史優化策略成功案例庫（新增股本佔比策略）
經參數網格搜尋與股本大小相對過濾，我們在案例庫中露出以下五大核心策略：
* **🥇 策略 1（外資大買型）**：$T-15$ 買 ➔ $T+19$ 賣，外資累積買超 > 2,000張（勝率 100.0% / 報酬 +45.0%）。
* **🥈 策略 2（投信大買型）**：$T-15$ 買 ➔ $T+19$ 賣，投信累積買超 > 2,000張（勝率 100.0% / 報酬 +42.9%）。
* **🥉 策略 3（雙法人加持型）**：$T-15$ 買 ➔ $T+19$ 賣，外資與投信皆大買 > 2,000張（勝率 100.0% / 報酬 +42.9%）。
* **📈 策略 4（投信卡位 + 股本佔比型）**：$T-15$ 買 ➔ $T+19$ 賣，投信累積 > 2000張 且 佔個股總股本 &ge; 0.5%（**勝率 100.0% / 報酬 +43.6%**）。
* **📊 策略 5（外資卡位 + 股本佔比型）**：$T-15$ 買 ➔ $T+19$ 賣，外資累積 > 2000張 且 佔個股總股本 &ge; 0.5%（**勝率 92.9% / 報酬 +37.2%**）。

---

### 4. 統一主題與視覺樣式 (Unify Theme & Visual Layout)
* **HTML 結構宣告**：補回 `<!DOCTYPE html>` 與 `<html lang="zh-Hant-TW">` 結構。
* **頂部 Header 欄位統一**：
  * 使用相同的 Tailwind sticky header、高斯模糊效果 (`backdrop-blur`)、漸層主標題字體。
  * 獨立拆分並美化水印徽章為兩個標籤：`作者: pioter`（Indigo 柔光）與 `AI分析師: +1000`（Cyan 柔光），與 `ai-theme-map-site` 完全保持一致。
* **分頁按鈕切換機制**：修改 `app.js` 的 `switchTab` 邏輯，藉由 Tailwind 類別動態切換 active 狀態樣式（從原本的 CSS `.active-tab` 轉為 `text-white bg-slate-800` 與 `text-slate-400 hover:text-white` 的優雅過渡）。

---

## 🖼️ 實測畫面與驗證

已通過瀏覽器 Subagent 在 `http://localhost:8000/` 完成完整的 UI 功能性與互動驗證：

````carousel
![統一後的主題與標題徽章](file:///C:/Users/pioterlee/.gemini/antigravity-ide/brain/fd350c3d-baae-453b-b142-71a8d5227969/home_page_1781664840070.png)
<!-- slide -->
![執行中 SOP 捷運軌道圖](file:///C:/Users/pioterlee/.gemini/antigravity-ide/brain/fd350c3d-baae-453b-b142-71a8d5227969/active_tracks_view_1781662038976.png)
<!-- slide -->
![策略 4 (股本佔比型) 優化案例](file:///C:/Users/pioterlee/.gemini/antigravity-ide/brain/fd350c3d-baae-453b-b142-71a8d5227969/strategy_4_trades_1781663277422.png)
````

*瀏覽器操作錄像：[操作錄影](file:///C:/Users/pioterlee/.gemini/antigravity-ide/brain/fd350c3d-baae-453b-b142-71a8d5227969/verify_unified_theme_1781664827977.webp)*
