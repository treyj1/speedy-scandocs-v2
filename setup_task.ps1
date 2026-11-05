# Speedy Scandocs v2: one-time setup on the office computer.
# Run in PowerShell from this folder:
#   powershell -ExecutionPolicy Bypass -File .\setup_task.ps1
#
# 1. Stores the Bedrock API key as a user environment variable (typed, not pasted into a file).
# 2. Creates a Task Scheduler job that runs the script:
#      - every hour during the workday (7 AM to 7 PM by default),
#      - once when this user signs in, and once on waking if a run was missed.
#    The computer does not need to stay awake overnight.
#
# Change the hours like this:  .\setup_task.ps1 -StartHour 8 -EndHour 18 -EveryMinutes 60

param(
    [int]$StartHour = 7,
    [int]$EndHour = 19,
    [int]$EveryMinutes = 60,
    [string]$TaskName = "Speedy Scandocs"
)

$ErrorActionPreference = "Stop"
$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path

# --- API key ------------------------------------------------------------
$existing = [Environment]::GetEnvironmentVariable("AWS_BEARER_TOKEN_BEDROCK", "User")
if ($existing) {
    $answer = Read-Host "A Bedrock API key is already saved. Replace it? (y/N)"
}
if (-not $existing -or $answer -match '^[Yy]') {
    $secure = Read-Host "Paste the Bedrock API key" -AsSecureString
    $key = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
    if (-not $key) { throw "No key entered." }
    [Environment]::SetEnvironmentVariable("AWS_BEARER_TOKEN_BEDROCK", $key, "User")
    $env:AWS_BEARER_TOKEN_BEDROCK = $key
    Write-Host "API key saved for user $env:USERNAME."
}

# --- What to run: the packaged .exe if present, otherwise Python ---------
$exe = Join-Path $Dir "scandocs.exe"
if (Test-Path $exe) {
    $action = New-ScheduledTaskAction -Execute $exe -WorkingDirectory $Dir
} else {
    $py = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
    if (-not $py) { throw "Python not found. Install Python 3.11+ (python.org) and run: pip install -r requirements.txt" }
    $action = New-ScheduledTaskAction -Execute $py -Argument "`"$Dir\scandocs.py`"" -WorkingDirectory $Dir
}

# --- Schedule -------------------------------------------------------------
# Workday: every hour from StartHour to EndHour, every day.
$start   = (Get-Date).Date.AddHours($StartHour)
$workday = New-ScheduledTaskTrigger -Daily -At $start
$workday.Repetition = (New-ScheduledTaskTrigger -Once -At $start `
    -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes) `
    -RepetitionDuration (New-TimeSpan -Hours ($EndHour - $StartHour))).Repetition

# Morning catch-up: run 2 minutes after this user signs in (network drives are ready by then).
$logon = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$logon.Delay = "PT2M"

# StartWhenAvailable: if the computer was asleep at a scheduled time, run once on waking.
# No WakeToRun: the computer is never woken up just for this.
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable `
            -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($workday, $logon) -Settings $settings `
    -Description "Names scanned PDFs by client using Claude on Amazon Bedrock." -Force | Out-Null

Write-Host ("Scheduled task '{0}' runs every {1} minutes from {2}:00 to {3}:00, and when {4} signs in." -f `
    $TaskName, $EveryMinutes, $StartHour, $EndHour, $env:USERNAME)
Write-Host "Check results in scandocs_log.csv. Remove with: Unregister-ScheduledTask -TaskName '$TaskName'"

# --- Desktop shortcuts for the person who checks the scans ----------------
# Reads the folder paths from config.toml so the shortcuts always match.
function Get-ConfigPath([string]$key) {
    $line = Select-String -Path (Join-Path $Dir "config.toml") -Pattern "^\s*$key\s*=\s*'([^']*)'" |
            Select-Object -First 1
    if (-not $line) { return $null }
    $p = $line.Matches[0].Groups[1].Value
    if ($p -like "*{dropbox}*") { $p = $p.Replace("{dropbox}", (Get-DropboxRoot)) }
    $p = [Environment]::ExpandEnvironmentVariables($p)
    if (-not [IO.Path]::IsPathRooted($p)) { $p = Join-Path $Dir $p }
    return $p
}

function Get-DropboxRoot {
    foreach ($base in @($env:LOCALAPPDATA, $env:APPDATA)) {
        $info = Join-Path $base "Dropbox\info.json"
        if (Test-Path $info) {
            $j = Get-Content $info -Raw | ConvertFrom-Json
            if ($j.business -and $j.business.path) { return $j.business.path }
            if ($j.personal -and $j.personal.path) { return $j.personal.path }
        }
    }
    throw "config.toml uses {dropbox} but Dropbox was not found for this Windows user."
}

$shell   = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath("Desktop")
function New-Shortcut([string]$name, [string]$target, [string]$arguments = "", [string]$icon = "") {
    $lnk = $shell.CreateShortcut((Join-Path $desktop "$name.lnk"))
    $lnk.TargetPath = $target
    if ($arguments) { $lnk.Arguments = $arguments }
    if ($icon) { $lnk.IconLocation = $icon }
    $lnk.WorkingDirectory = $Dir
    $lnk.Save()
}

$named  = Get-ConfigPath "named_folder"
$review = Get-ConfigPath "review_folder"
$rules  = Get-ConfigPath "rules_file"
$list   = Get-ConfigPath "client_list"
$scan   = Get-ConfigPath "scan_folder"
foreach ($folder in @($scan, $named, $review)) { if ($folder) { New-Item -ItemType Directory -Force -Path $folder | Out-Null } }

# First install: copy the starter rules and client list to where config.toml says they live
# (e.g. the shared Dropbox), without overwriting ones that already exist.
foreach ($pair in @(@($rules, "naming_rules.txt"), @($list, "client_list.txt"))) {
    $target, $starter = $pair
    if ($target -and -not (Test-Path $target) -and (Test-Path (Join-Path $Dir $starter))) {
        New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
        Copy-Item (Join-Path $Dir $starter) $target
    }
}

$notepad = Join-Path $env:WINDIR "System32\notepad.exe"
if ($named)  { New-Shortcut "Scans - Named" $named }
if ($review) { New-Shortcut "Scans - Needs Review" $review }
if ($rules)  { New-Shortcut "Scan Naming Rules" $notepad "`"$rules`"" }
if ($list)   { New-Shortcut "Client List" $notepad "`"$list`"" }
New-Shortcut "Name Scans Now" (Join-Path $env:WINDIR "System32\schtasks.exe") "/run /tn `"$TaskName`"" `
    "$env:WINDIR\System32\shell32.dll,238"

Write-Host "Desktop shortcuts created: Scans - Named, Scans - Needs Review, Scan Naming Rules, Client List, Name Scans Now."
