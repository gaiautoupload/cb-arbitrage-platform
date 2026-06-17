@echo off
:: Reconfigure encoding for Chinese characters in cmd
chcp 65001 > nul
echo ==========================================================
echo 🚀 開始執行可轉債策略平台 - 每日盤後數據更新 (update_daily.bat)
echo ==========================================================
echo.

cd /d "%~dp0"

echo 📥 [1/10] 爬取今日重大公告 (mops_crawler.py)...
python backend/mops_crawler.py
if %errorlevel% neq 0 (echo ❌ 執行失敗! && pause && exit /b %errorlevel%)

echo 🏛️ [2/10] 爬取公會競拍公告 (twsa_crawler.py)...
python backend/twsa_crawler.py
if %errorlevel% neq 0 (echo ❌ 執行失敗! && pause && exit /b %errorlevel%)

echo ⚙️ [3/10] 解析新發行可轉債公告 (parser.py)...
python backend/parser.py
if %errorlevel% neq 0 (echo ❌ 執行失敗! && pause && exit /b %errorlevel%)

echo 📈 [4/10] 抓取個股最新歷史股價 (stock_fetcher.py)...
python backend/stock_fetcher.py
if %errorlevel% neq 0 (echo ❌ 執行失敗! && pause && exit /b %errorlevel%)

echo 👥 [5/10] 抓取今日三大法人籌碼資料 (inst_fetcher.py)...
python backend/inst_fetcher.py
if %errorlevel% neq 0 (echo ❌ 執行失敗! && pause && exit /b %errorlevel%)

echo 🔄 [6/10] 合併法人籌碼至股價資料庫 (merge_inst_to_prices.py)...
python backend/merge_inst_to_prices.py
if %errorlevel% neq 0 (echo ❌ 執行失敗! && pause && exit /b %errorlevel%)

echo 🧹 [7/10] 清理與修正 NaN 無效數值 (clean_nan_prices.py)...
python backend/clean_nan_prices.py
if %errorlevel% neq 0 (echo ❌ 執行失敗! && pause && exit /b %errorlevel%)

echo 🔗 [8/10] 串聯可轉債多階段生命週期 (bond_stage_linker.py)...
python backend/bond_stage_linker.py
if %errorlevel% neq 0 (echo ❌ 執行失敗! && pause && exit /b %errorlevel%)

echo 📊 [9/10] 重算量化策略回測指標 (analyzer.py)...
python backend/analyzer.py
if %errorlevel% neq 0 (echo ❌ 執行失敗! && pause && exit /b %errorlevel%)

echo 🚇 [10/10] 更新執行中 SOP 軌道路線狀態 (daily_monitor.py)...
python backend/daily_monitor.py
if %errorlevel% neq 0 (echo ❌ 執行失敗! && pause && exit /b %errorlevel%)

echo.
echo ==========================================================
echo 📦 數據更新完畢，開始自動推送至 GitHub Pages...
echo ==========================================================
git add backend/data/
git commit -m "Auto Update Database: %date% %time%"
git push origin main
if %errorlevel% neq 0 (
    echo ⚠️ 推送失敗，請確認是否已設定 ssh 或 github 認證密鑰！
) else (
    echo 🎉 網站已順利同步更新！
)

echo.
echo ==========================================================
echo ✅ 每日排程更新執行完畢！
echo ==========================================================
timeout /t 5
