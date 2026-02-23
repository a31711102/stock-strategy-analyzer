@echo off
REM ============================================
REM 日次バッチ処理 中断再開スクリプト
REM 前回の途中から再開します
REM ============================================
chcp 65001 > nul 2>&1

set PROJECT_DIR=C:\Users\kimi4\stock-strategy-analyzer
set PYTHON_EXE=C:\anaconda\python.exe
set PYTHONPATH=%PROJECT_DIR%

cd /d %PROJECT_DIR%

echo ============================================
echo   日次バッチ処理（中断再開）
echo ============================================
echo.
echo 前回の進捗から再開します...
echo.

REM ログディレクトリ作成
if not exist logs mkdir logs

REM 再開モードで実行
%PYTHON_EXE% src\batch\daily_batch.py --resume

echo.
if %ERRORLEVEL% NEQ 0 (
    echo バッチ処理がエラーで終了しました。
) else (
    echo バッチ処理が正常に完了しました！
)

echo.
pause
