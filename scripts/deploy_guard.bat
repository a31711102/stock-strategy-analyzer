@echo off
REM ============================================
REM デプロイガード - ログイン時に保留中デプロイを検出・実行
REM
REM .deploy_pending マーカーが存在する場合のみ動作する。
REM マーカーはバッチ正常完了後に作成され、デプロイ成功後に削除される。
REM デプロイが中断された場合にのみマーカーが残存し、
REM 次回ログイン時にこのスクリプトがリトライを実行する。
REM ============================================
chcp 65001 > nul 2>&1

set PROJECT_DIR=C:\Users\kimi4\stock-strategy-analyzer
set PYTHON_EXE=C:\anaconda\python.exe
set PYTHONPATH=%PROJECT_DIR%
set FOR_DISABLE_CONSOLE_CTRL_HANDLER=1

cd /d %PROJECT_DIR%

REM マーカーが存在しない場合は即座に終了（通常のログイン時）
if not exist "%PROJECT_DIR%\.deploy_pending" exit /b 0

REM ログディレクトリ作成
if not exist logs mkdir logs

echo ============================================ >> "%PROJECT_DIR%\logs\deploy.log"
echo [%date% %time%] [GUARD] デプロイ保留を検出。自動デプロイを実行します >> "%PROJECT_DIR%\logs\deploy.log"

call "%PROJECT_DIR%\scripts\auto_deploy.bat"

if %ERRORLEVEL% EQU 0 (
    del "%PROJECT_DIR%\.deploy_pending"
    echo [%date% %time%] [GUARD] デプロイガード: 正常完了 >> "%PROJECT_DIR%\logs\deploy.log"
) else (
    echo [%date% %time%] [GUARD] デプロイガード: 失敗（次回ログイン時に再試行） >> "%PROJECT_DIR%\logs\deploy.log"
)
