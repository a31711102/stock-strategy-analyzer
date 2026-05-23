@echo off
REM ============================================
REM Generate static HTML -> GitHub Pages auto deploy
REM Called after daily batch execution completes
REM ============================================
chcp 65001 > nul 2>&1

set PROJECT_DIR=C:\Users\kimi4\stock-strategy-analyzer
set PYTHON_EXE=C:\anaconda\python.exe
set PYTHONPATH=%PROJECT_DIR%
set LOG_FILE=%PROJECT_DIR%\logs\deploy.log

cd /d %PROJECT_DIR%

REM Create logs directory
if not exist logs mkdir logs

echo ============================================ >> "%LOG_FILE%"
echo [%date% %time%] === Deployment Started === >> "%LOG_FILE%"

REM 2. Generate static HTML
echo [%date% %time%] Starting static HTML generation >> "%LOG_FILE%"
echo [%date% %time%] Starting static HTML generation
%PYTHON_EXE% scripts\generate_static_pages.py >> "%LOG_FILE%" 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo [%date% %time%] [ERROR] Static HTML generation failed >> "%LOG_FILE%"
    echo [%date% %time%] [ERROR] Static HTML generation failed
    exit /b %ERRORLEVEL%
)
echo [%date% %time%] Static HTML generation completed >> "%LOG_FILE%"

REM 3. Commit & Push docs/ with Git
echo [%date% %time%] Deploying to GitHub Pages >> "%LOG_FILE%"
echo [%date% %time%] Deploying to GitHub Pages

git add docs/
git diff --cached --quiet
if %ERRORLEVEL% EQU 0 (
    echo [%date% %time%] [SKIP] No changes in docs/. Deployment skipped >> "%LOG_FILE%"
    echo [%date% %time%] No changes in docs/. Deployment skipped.
    exit /b 0
)

for /f "tokens=*" %%d in ('powershell -Command "Get-Date -Format yyyy-MM-dd"') do set TODAY=%%d
git commit -m "chore: update static pages (%TODAY%)" >> "%LOG_FILE%" 2>&1
git push origin main >> "%LOG_FILE%" 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo [%date% %time%] [ERROR] git push failed >> "%LOG_FILE%"
    echo [%date% %time%] [ERROR] git push failed
    exit /b %ERRORLEVEL%
)

echo [%date% %time%] [OK] Deployment completed successfully >> "%LOG_FILE%"
echo [%date% %time%] Deployment completed successfully
