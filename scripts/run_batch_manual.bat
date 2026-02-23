@echo off
REM ============================================
REM 日次バッチ処理 手動実行スクリプト
REM ダブルクリックで実行できます
REM ============================================
chcp 65001 > nul 2>&1

set PROJECT_DIR=C:\Users\kimi4\stock-strategy-analyzer
set PYTHON_EXE=C:\anaconda\python.exe
set PYTHONPATH=%PROJECT_DIR%

cd /d %PROJECT_DIR%

echo ============================================
echo   日次バッチ処理（手動実行）
echo ============================================
echo.
echo 処理を開始します...
echo 全銘柄の処理には約1.5〜3時間かかります。
echo 途中で中断する場合は Ctrl+C を押してください。
echo （中断後は run_batch_resume.bat で再開できます）
echo.

REM ログディレクトリ作成
if not exist logs mkdir logs

REM バッチ処理実行
%PYTHON_EXE% src\batch\daily_batch.py

echo.
if %ERRORLEVEL% NEQ 0 (
    echo バッチ処理がエラーで終了しました。
    echo ログファイル: logs\batch_%date:~0,4%%date:~5,2%%date:~8,2%.log
) else (
    echo バッチ処理が正常に完了しました！
)

echo.
pause
