@echo off
REM ============================================
REM Daily batch automatic execution script
REM Called by Task Scheduler
REM ============================================
chcp 65001 > nul 2>&1

set PROJECT_DIR=C:\Users\kimi4\stock-strategy-analyzer
set PYTHON_EXE=C:\anaconda\python.exe
set PYTHONPATH=%PROJECT_DIR%

REM Disable console control handler for Intel MKL Fortran runtime
REM to prevent forrtl: error (200) crash on numpy/scipy MKL dependency
set FOR_DISABLE_CONSOLE_CTRL_HANDLER=1

cd /d %PROJECT_DIR%

REM Skip weekends
for /f "tokens=1" %%d in ('powershell -Command "(Get-Date).DayOfWeek"') do set DOW=%%d
if "%DOW%"=="Saturday" (
    echo [%date% %time%] Skipped because it is Saturday >> logs\batch_skip.log
    exit /b 0
)
if "%DOW%"=="Sunday" (
    echo [%date% %time%] Skipped because it is Sunday >> logs\batch_skip.log
    exit /b 0
)

REM Create logs directory
if not exist logs mkdir logs

REM Run batch processor
echo [%date% %time%] Starting daily batch
%PYTHON_EXE% src\batch\daily_batch.py

REM Check exit code
if %ERRORLEVEL% NEQ 0 (
    echo [%date% %time%] Batch failed with code %ERRORLEVEL% >> logs\batch_error.log
    exit /b %ERRORLEVEL%
)

echo [%date% %time%] Batch completed successfully

REM Create deploy pending marker (proof of batch success)
REM Used by deploy_guard.bat to retry on next login if deployment is interrupted
echo %date% %time% > "%PROJECT_DIR%\.deploy_pending"

REM Run automatic deployment (generate static pages and git push)
call %PROJECT_DIR%\scripts\auto_deploy.bat

REM Remove marker only on successful deployment
if %ERRORLEVEL% EQU 0 (
    if exist "%PROJECT_DIR%\.deploy_pending" del "%PROJECT_DIR%\.deploy_pending"
)
