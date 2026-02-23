# タスクスケジューラ登録スクリプト
# 管理者権限不要（現在のユーザーで登録）

$taskName = "StockStrategyAnalyzer_DailyBatch"
$batPath = "C:\Users\kimi4\stock-strategy-analyzer\scripts\run_batch.bat"
$workDir = "C:\Users\kimi4\stock-strategy-analyzer"

# アクション定義
$action = New-ScheduledTaskAction -Execute $batPath -WorkingDirectory $workDir

# トリガー定義（平日22:00）
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "22:00"

# 設定
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 5) `
    -RunOnlyIfNetworkAvailable `
    -MultipleInstances IgnoreNew

# 登録
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Stock Strategy Analyzer - Daily batch at 22:00 on weekdays" `
    -Force

Write-Host ""
Write-Host "Task registered successfully: $taskName" -ForegroundColor Green
Write-Host "Schedule: Weekdays at 22:00" -ForegroundColor Cyan
Write-Host "StartWhenAvailable: True (runs on next boot if missed)" -ForegroundColor Cyan
