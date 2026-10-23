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
# The Time Clocks lab: Install-TimeClocks.ps1 records the WeiDU.log it left and the mod's files.
$clocks = $null
if ($config.Variant -ceq 'timeclocks') {
    $clocksPath = Join-Path $lab 'cbr-timeclocks.json'
    Assert-LabNoReparsePath $clocksPath
    if (Test-Path -LiteralPath $clocksPath) {
        $clocks = [IO.File]::ReadAllText($clocksPath) | ConvertFrom-Json
        if ($clocks.InstanceId -cne $manifest.InstanceId) { throw 'Time Clocks record identity mismatch.' }
    }
}
foreach ($entry in $manifest.InstalledHashes.PSObject.Properties) {
    $path = Join-Path $lab $entry.Name
    # The loader adds its own address cache to InfinityLoader.ini on every launch.
    $hash = if ($entry.Name -ceq 'InfinityLoader.ini') { Get-LabLoaderConfigurationSha256 $path } else { Get-LabSha256 $path }
    $expected = if ($clocks -and $entry.Name -ceq 'WeiDU.log') { $clocks.WeiDULogSha256 } else { $entry.Value }
    if ($hash -cne $expected) { throw "Changed installed asset: $($entry.Name)" }
}
if ($clocks) {
    $stack = Get-LabWeiDUStack ([IO.File]::ReadAllText((Join-Path $lab 'WeiDU.log')))
    if ((@($stack.EEex) -join ',') -cne '0,1,8' -or (@($stack.TimeClocks) -join ',') -cne (@($clocks.Components) -join ',')) {
        throw 'Time Clocks components differ from their record.'
    }
    foreach ($entry in $clocks.Installed.PSObject.Properties) {
        if (-not (Test-LabPathWithin -Path (Join-Path $lab $entry.Name) $lab)) { throw 'Invalid Time Clocks path.' }
        if ((Get-LabSha256 (Join-Path $lab $entry.Name)) -cne $entry.Value) { throw "Changed Time Clocks file: $($entry.Name)" }
    }
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
    $mod = if ($clocks) { [pscustomobject]@{Commit=$clocks.ModCommit; Components=@($clocks.Components)} } else { $null }
    [pscustomobject]@{Validated=$true; LabRoot=$lab; Profile=$config.ProfileRoot; TimeClocks=$mod;
        GameProcesses=$processes.Count; Launched=$false} | ConvertTo-Json -Compress -Depth 4
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
