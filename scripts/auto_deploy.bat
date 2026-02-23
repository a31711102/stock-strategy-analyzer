@echo off
REM ============================================
REM 静的HTML生成 → GitHub Pages 自動デプロイ
REM バッチ処理完了後に呼び出される
REM ============================================
chcp 65001 > nul 2>&1

set PROJECT_DIR=C:\Users\kimi4\stock-strategy-analyzer
set PYTHON_EXE=C:\anaconda\python.exe
set PYTHONPATH=%PROJECT_DIR%

cd /d %PROJECT_DIR%

REM 静的HTML生成
echo [%date% %time%] 静的HTML生成を開始します
%PYTHON_EXE% scripts\generate_static_pages.py

if %ERRORLEVEL% NEQ 0 (
    echo [%date% %time%] 静的HTML生成がエラーで終了しました >> logs\deploy_error.log
    exit /b %ERRORLEVEL%
)

REM Git で docs/ をコミット＆プッシュ
echo [%date% %time%] GitHub Pages にデプロイします

git add docs/
git diff --cached --quiet
if %ERRORLEVEL% EQU 0 (
    echo [%date% %time%] docs/ に変更がありません。デプロイをスキップします。
    exit /b 0
)

for /f "tokens=*" %%d in ('powershell -Command "Get-Date -Format yyyy-MM-dd"') do set TODAY=%%d
git commit -m "chore: update static pages (%TODAY%)"
git push origin main

if %ERRORLEVEL% NEQ 0 (
    echo [%date% %time%] git push がエラーで終了しました >> logs\deploy_error.log
    exit /b %ERRORLEVEL%
)

echo [%date% %time%] デプロイが正常に完了しました
