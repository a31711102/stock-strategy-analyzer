# デプロイガード タスクスケジューラ登録スクリプト
# ログイン時に .deploy_pending マーカーを検知して自動デプロイをリトライする

$taskName = "StockStrategyAnalyzer_DeployGuard"
$batPath = "C:\Users\kimi4\stock-strategy-analyzer\scripts\deploy_guard.bat"

# アクション定義
$action = New-ScheduledTaskAction -Execute $batPath

# トリガー定義（ログイン時）
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "kimi4"

# 設定（互換性の高いパラメータのみ使用）
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew

# 登録
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Deploy guard: retry pending deploy on login (marker-based)" -Force

Write-Host ""
Write-Host "Task registered successfully: $taskName" -ForegroundColor Green
Write-Host "Trigger: At logon (user: kimi4)" -ForegroundColor Cyan
Write-Host "Action: Runs deploy_guard.bat (no-op if no pending deploy)" -ForegroundColor Cyan
