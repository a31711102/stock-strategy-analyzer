@echo off
REM ============================================
REM 静的HTML生成 → GitHub Pages 自動デプロイ
REM バッチ処理完了後に呼び出される
REM ============================================
chcp 65001 > nul 2>&1

set PROJECT_DIR=C:\Users\kimi4\stock-strategy-analyzer
set PYTHON_EXE=C:\anaconda\python.exe
set PYTHONPATH=%PROJECT_DIR%
set LOG_FILE=%PROJECT_DIR%\logs\deploy.log

cd /d %PROJECT_DIR%

REM ログディレクトリ作成
if not exist logs mkdir logs

echo ============================================ >> "%LOG_FILE%"
echo [%date% %time%] === デプロイ開始 === >> "%LOG_FILE%"

REM 1. ボラティリティスクリーナー実行（バッチとは独立にデータ取得）
echo [%date% %time%] スクリーナーを実行します >> "%LOG_FILE%"
echo [%date% %time%] スクリーナーを実行します
%PYTHON_EXE% scripts\run_screener.py >> "%LOG_FILE%" 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo [%date% %time%] [WARN] スクリーナー実行でエラー（続行） >> "%LOG_FILE%"
    echo [%date% %time%] [WARN] スクリーナー実行でエラー（続行）
)
echo [%date% %time%] スクリーナー完了 >> "%LOG_FILE%"

REM 1.5 黄金の指値ボード（Low Hunter）実行
echo [%date% %time%] Low Hunterを実行します >> "%LOG_FILE%"
echo [%date% %time%] Low Hunterを実行します
%PYTHON_EXE% scripts\run_low_hunter.py >> "%LOG_FILE%" 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo [%date% %time%] [WARN] Low Hunter実行でエラー（続行） >> "%LOG_FILE%"
    echo [%date% %time%] [WARN] Low Hunter実行でエラー（続行）
)
echo [%date% %time%] Low Hunter完了 >> "%LOG_FILE%"

REM 2. 静的HTML生成
echo [%date% %time%] 静的HTML生成を開始します >> "%LOG_FILE%"
echo [%date% %time%] 静的HTML生成を開始します
%PYTHON_EXE% scripts\generate_static_pages.py >> "%LOG_FILE%" 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo [%date% %time%] [ERROR] 静的HTML生成が失敗しました >> "%LOG_FILE%"
    echo [%date% %time%] [ERROR] 静的HTML生成が失敗しました
    exit /b %ERRORLEVEL%
)
echo [%date% %time%] 静的HTML生成が完了しました >> "%LOG_FILE%"

REM 3. Git で docs/ をコミット＆プッシュ
echo [%date% %time%] GitHub Pages にデプロイします >> "%LOG_FILE%"
echo [%date% %time%] GitHub Pages にデプロイします

git add docs/
git diff --cached --quiet
if %ERRORLEVEL% EQU 0 (
    echo [%date% %time%] [SKIP] docs/ に変更なし。デプロイをスキップ >> "%LOG_FILE%"
    echo [%date% %time%] docs/ に変更がありません。デプロイをスキップします。
    exit /b 0
)

for /f "tokens=*" %%d in ('powershell -Command "Get-Date -Format yyyy-MM-dd"') do set TODAY=%%d
git commit -m "chore: update static pages (%TODAY%)" >> "%LOG_FILE%" 2>&1
git push origin main >> "%LOG_FILE%" 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo [%date% %time%] [ERROR] git push が失敗しました >> "%LOG_FILE%"
    echo [%date% %time%] [ERROR] git push が失敗しました
    exit /b %ERRORLEVEL%
)

echo [%date% %time%] [OK] デプロイが正常に完了しました >> "%LOG_FILE%"
echo [%date% %time%] デプロイが正常に完了しました
