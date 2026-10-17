#Requires -Version 7.0
<# Default: read-only preflight. -Launch holds the test mutex until our game exits.
   It never closes another process, imports a save, or activates native hooks. #>
[CmdletBinding()]
param([switch] $Launch)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Lab.Common.ps1')
$config = Get-LabConfiguration
$lab = Assert-LabRoot
$manifest = Read-LabManifest
Assert-LabProfile $manifest
if ($manifest.Phase -cne 'Validated') { throw 'Baseline not validated.' }
foreach ($entry in $manifest.InstalledHashes.PSObject.Properties) {
    if ((Get-LabSha256 (Join-Path $lab $entry.Name)) -cne $entry.Value) { throw "Changed installed asset: $($entry.Name)" }
}
if ((Get-LabSha256 (Join-Path $lab 'Baldur.exe')) -cne $config.ExeSha256) { throw 'Changed game executable.' }
$diagnosticPath = Join-Path $lab 'cbr-diagnostics.json'
Assert-LabNoReparsePath $diagnosticPath
$diagnostics = Get-Content -LiteralPath $diagnosticPath -Raw | ConvertFrom-Json
if ($diagnostics.InstanceId -cne $manifest.InstanceId -or $diagnostics.Mode -cne 'observation_only') {
    throw 'Diagnostic identity mismatch.'
}
foreach ($entry in $diagnostics.Files.PSObject.Properties) {
    if (-not (Test-LabPathWithin (Join-Path $lab $entry.Name) $lab)) { throw 'Invalid diagnostic path.' }
    if ((Get-LabSha256 (Join-Path $lab $entry.Name)) -cne $entry.Value) { throw "Changed diagnostic asset: $($entry.Name)" }
}
if (-not $Launch) {
    $processes = @(Get-CimInstance Win32_Process | Where-Object Name -in @('Baldur.exe','InfinityLoader.exe'))
    [pscustomobject]@{Validated=$true; LabRoot=$lab; Profile=$config.ProfileRoot;
        GameProcesses=$processes.Count; Launched=$false} | ConvertTo-Json -Compress
    return
}
$mutex = [Threading.Mutex]::new($false, 'Local\ChrizInfinityEngineLab')
$owned = $false
try {
    try { $owned = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $owned = $true }
    if (-not $owned) { throw 'Another cooperating lab owns the runtime mutex.' }
    Assert-LabNoGameProcess
    $loader = Join-Path $lab 'InfinityLoader.exe'
    # Hidden startup helper; no user desktop/window automation is performed.
    $started = Start-Process -FilePath $loader -WorkingDirectory $lab -WindowStyle Hidden -PassThru
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    $game = $null
    do {
        Start-Sleep -Milliseconds 500
        $games = @(Get-CimInstance Win32_Process -Filter "Name='Baldur.exe'")
        $ours = @($games | Where-Object { $_.ExecutablePath -ieq (Join-Path $lab 'Baldur.exe') })
        if ($games.Count -ne $ours.Count) { throw 'A foreign game appeared; no game commands will be sent.' }
        if ($ours.Count -gt 1) { throw 'Ambiguous owned game process.' }
        if ($ours.Count -eq 1) { $game=$ours[0]; break }
    } while ([DateTime]::UtcNow -lt $deadline)
    if (-not $game) { throw 'No owned game appeared. Inspect loader logs before any retry.' }
    $session = [ordered]@{InstanceId=$manifest.InstanceId; LauncherPid=$PID;
        LoaderPid=$started.Id; GamePid=$game.ProcessId; GamePath=$game.ExecutablePath;
        StartedUtc=[DateTime]::UtcNow.ToString('o'); Mutex='Local\ChrizInfinityEngineLab'}
    $sessionPath = Join-Path $lab 'cbr-runtime-session.json'
    Assert-LabNoReparsePath $sessionPath
    [IO.File]::WriteAllText($sessionPath, ($session | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
    $session | ConvertTo-Json -Compress
    Wait-Process -Id $game.ProcessId -ErrorAction SilentlyContinue
    if (-not $started.HasExited) { $started.WaitForExit() }
}
finally {
    if ($owned) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
