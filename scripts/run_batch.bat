@echo off
REM ============================================
REM 日次バッチ処理 自動実行スクリプト
REM タスクスケジューラから呼び出される
REM ============================================
chcp 65001 > nul 2>&1

set PROJECT_DIR=C:\Users\kimi4\stock-strategy-analyzer
set PYTHON_EXE=C:\anaconda\python.exe
set PYTHONPATH=%PROJECT_DIR%

cd /d %PROJECT_DIR%

REM 平日チェック（土日はスキップ）
for /f "tokens=1" %%d in ('powershell -Command "(Get-Date).DayOfWeek"') do set DOW=%%d
if "%DOW%"=="Saturday" (
    echo [%date% %time%] 土曜日のためスキップします >> logs\batch_skip.log
    exit /b 0
)
if "%DOW%"=="Sunday" (
    echo [%date% %time%] 日曜日のためスキップします >> logs\batch_skip.log
    exit /b 0
)

REM ログディレクトリ作成
if not exist logs mkdir logs

REM バッチ処理実行
echo [%date% %time%] バッチ処理を開始します
%PYTHON_EXE% src\batch\daily_batch.py

REM 終了コード確認
if %ERRORLEVEL% NEQ 0 (
    echo [%date% %time%] バッチ処理がエラーで終了しました (code: %ERRORLEVEL%) >> logs\batch_error.log
    exit /b %ERRORLEVEL%
)

echo [%date% %time%] バッチ処理が正常に完了しました

REM GitHub Pages 自動デプロイ（静的HTML生成 → git push）
call %PROJECT_DIR%\scripts\auto_deploy.bat
