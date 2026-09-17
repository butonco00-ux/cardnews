# 윈도우 예약 작업 등록: 매일 07:00 + 로그인할 때(꺼져 있었으면 켜질 때 따라잡음)
$root = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python).Source
$pythonw = Join-Path (Split-Path $python) "pythonw.exe"
if (-not (Test-Path $pythonw)) { $pythonw = $python }
$action = New-ScheduledTaskAction -Execute $pythonw -Argument ('"' + (Join-Path $root "scripts\laptop_daily.py") + '"') -WorkingDirectory $root
$daily = New-ScheduledTaskTrigger -Daily -At 7:00am
$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$logon.Delay = "PT3M"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "CardnewsGovDaily" -Description "부동산 카드뉴스: 정부 보도자료 카드 만들어 GitHub에 올리기" -Action $action -Trigger @($daily, $logon) -Settings $settings -Force | Out-Null
Get-ScheduledTask -TaskName "CardnewsGovDaily" | Select-Object TaskName, State
