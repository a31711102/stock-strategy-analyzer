@echo off
REM ============================================
REM Deploy Guard - Retry pending deployment on login
REM
REM Runs only if .deploy_pending marker exists.
REM The marker is created after successful batch execution
REM and deleted after successful deployment.
REM If deployment is interrupted, the marker remains
REM and this script retries deployment on next login.
REM ============================================
chcp 65001 > nul 2>&1

set PROJECT_DIR=C:\Users\kimi4\stock-strategy-analyzer
set PYTHON_EXE=C:\anaconda\python.exe
set PYTHONPATH=%PROJECT_DIR%
set FOR_DISABLE_CONSOLE_CTRL_HANDLER=1

cd /d %PROJECT_DIR%

REM Exit immediately if no pending marker exists
if not exist "%PROJECT_DIR%\.deploy_pending" exit /b 0

REM Create logs directory
if not exist logs mkdir logs

echo ============================================ >> "%PROJECT_DIR%\logs\deploy.log"
echo [%date% %time%] [GUARD] Pending deploy detected. Running auto deploy >> "%PROJECT_DIR%\logs\deploy.log"

call "%PROJECT_DIR%\scripts\auto_deploy.bat"

if %ERRORLEVEL% EQU 0 (
    del "%PROJECT_DIR%\.deploy_pending"
    echo [%date% %time%] [GUARD] Deploy Guard completed successfully >> "%PROJECT_DIR%\logs\deploy.log"
) else (
    echo [%date% %time%] [GUARD] Deploy Guard failed (will retry on next login) >> "%PROJECT_DIR%\logs\deploy.log"
)
