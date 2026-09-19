# Register Windows scheduled task: daily 07:00, 07:40, 12:00 + at logon (catch up if the laptop was off)
# ASCII only: Windows PowerShell 5.1 misreads UTF-8 files without BOM.
$root = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python).Source
$pythonw = Join-Path (Split-Path $python) "pythonw.exe"
if (-not (Test-Path $pythonw)) { $pythonw = $python }
$script = Join-Path $root "scripts\laptop_daily.py"
$action = New-ScheduledTaskAction -Execute $pythonw -Argument ('"' + $script + '"') -WorkingDirectory $root
$daily = New-ScheduledTaskTrigger -Daily -At 7:00am
# later runs: add AI fact summaries to the star set that GitHub makes around 07:00
$late1 = New-ScheduledTaskTrigger -Daily -At 7:40am
$late2 = New-ScheduledTaskTrigger -Daily -At 12:00pm
$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$logon.Delay = "PT3M"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "CardnewsGovDaily" -Description "Real estate card news: make government press release cards and push to GitHub" -Action $action -Trigger @($daily, $late1, $late2, $logon) -Settings $settings -Force | Out-Null
Get-ScheduledTask -TaskName "CardnewsGovDaily" | Select-Object TaskName, State
