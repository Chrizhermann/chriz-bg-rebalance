#Requires -Version 7.0
<#
Installs the Chriz BG Time Clocks mod into the Time Clocks lab (CBR_LAB_VARIANT=timeclocks) and
nowhere else: the Time Stop lab is refused before anything is read. It needs the validated lab
and no Baldur.exe or InfinityLoader.exe on the PC, and never launches the game.

1. The mod comes from -ModRoot, a clean checkout or worktree of chriz-bg-time-clocks: its
   committed installer and mod folder, checked blob by blob against HEAD.
2. The lab's installed Time Clocks components are uninstalled through WeiDU, the newest first.
   Then override and EEex_scripts must match the inventory recorded before the first install
   (the console's own eeex_remote_* files aside).
3. The lab's previous copy of the mod is moved aside into cbr-timeclocks-previous-<UTC>, never
   deleted, and the checkout's files take its place.
4. WeiDU installs -Components in order (none: the mod stays uninstalled). WeiDU.log must then
   list EEex 0, 1 and 8 and exactly these components; M_CBTC.lua and CBTC.db must equal the
   mod's files, and CBTCOPT.2DA must hold the switches the components set.
5. cbr-timeclocks.json records the commit, the components, the switches, the WeiDU.log hash and
   the installed files, for the preflight (Invoke-Lab.ps1).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $ModRoot,
    [Parameter(Mandatory)][AllowEmptyCollection()][int[]] $Components
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Lab.Common.ps1')
$config = Get-LabConfiguration
if ($config.Variant -cne 'timeclocks') { throw 'CBR_LAB TIMECLOCKS_LAB_ONLY: set CBR_LAB_VARIANT=timeclocks.' }
Assert-LabTimeClocksComponents $Components
$utf8 = [Text.UTF8Encoding]::new($false)
$tp2Name = 'setup-chriz-bg-time-clocks.tp2'
$modFolder = 'chriz-bg-time-clocks'
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')

function Get-VerifiedModSource {
    # The committed installer and mod folder of a clean checkout, each file's bytes checked
    # against its HEAD blob (with the checkout's line-end conversion, as Stage-Diagnostics does).
    param([string] $Root)
    $head = @(& git -C $Root rev-parse HEAD 2>&1)
    if ($LASTEXITCODE -ne 0 -or $head.Count -ne 1 -or $head[0] -notmatch '^[0-9a-f]{40}$') {
        throw 'CBR_LAB MOD_CHECKOUT_REQUIRED'
    }
    $dirty = @(& git -C $Root status --porcelain --untracked-files=all -- $tp2Name $modFolder 2>&1)
    if ($LASTEXITCODE -ne 0 -or $dirty.Count -ne 0) { throw 'CBR_LAB MOD_CHECKOUT_NOT_CLEAN' }
    $listed = @(& git -C $Root ls-files -- $tp2Name $modFolder 2>&1)
    if ($LASTEXITCODE -ne 0 -or $listed -cnotcontains $tp2Name -or
        $listed -cnotcontains "$modFolder/M_CBTC.lua" -or $listed -cnotcontains "$modFolder/CBTC.db" -or
        $listed -cnotcontains "$modFolder/CBTCOPT.2DA") {
        throw 'CBR_LAB MOD_FILES_MISSING'
    }
    $files = [ordered]@{}
    foreach ($relative in $listed) {
        if ($relative -notmatch '^[A-Za-z0-9_./-]+$' -or $relative -match '(^|/)\.\.(/|$)') { throw "CBR_LAB MOD_PATH_REFUSED: $relative" }
        $path = Join-Path $Root $relative
        Assert-LabNoReparsePath $path
        $expected = @(& git -C $Root rev-parse ($head[0] + ':' + $relative) 2>&1)
        $actual = @(& git -C $Root hash-object ('--path=' + $relative) -- $path 2>&1)
        if ($LASTEXITCODE -ne 0 -or $expected.Count -ne 1 -or $actual.Count -ne 1 -or $actual[0] -cne $expected[0]) {
            throw "CBR_LAB MOD_BYTES_DIFFER_FROM_COMMIT: $relative"
        }
        $files[$relative] = Get-LabSha256 $path
    }
    [pscustomobject]@{Root = $Root; Commit = [string] $head[0]; Files = $files}
}

function Get-OwnedInventory {
    # override and EEex_scripts, without the console's own request, result and ready files.
    $rows = foreach ($tree in @('override', 'EEex_scripts')) {
        foreach ($item in @(Get-LabTreeInventory (Join-Path $lab $tree))) {
            if ($tree -ceq 'override' -and $item.RelativePath -match '^eeex_remote_[^/]*$') { continue }
            [pscustomobject]@{RelativePath = "$tree/$($item.RelativePath)"; Size = $item.Size; Sha256 = $item.Sha256}
        }
    }
    $rows = @($rows)
    [pscustomobject]@{Digest = Get-LabInventoryDigest $rows; Files = $rows.Count}
}

function Invoke-LabWeiDU {
    # One WeiDU run on the lab's own pinned weidu.exe; its output is kept beside its debug log.
    param([string] $Name, [string[]] $Arguments)
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = Join-Path $lab 'weidu.exe'
    $start.WorkingDirectory = $lab
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardInput = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    foreach ($argument in $Arguments) { $start.ArgumentList.Add($argument) }
    foreach ($argument in @('--no-exit-pause', '--noautoupdate', '--log', "cbr-timeclocks-$stamp-$Name.debug")) {
        $start.ArgumentList.Add($argument)
    }
    # A fail-closed snapshot right before the run, never permission to close another process.
    Assert-LabNoGameProcess
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    try {
        if (-not $process.Start()) { throw 'CBR_LAB WEIDU_START_FAILED' }
        $process.StandardInput.Close() # unexpected questions receive EOF, never user input
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        $output = $stdout.GetAwaiter().GetResult() + "`n" + $stderr.GetAwaiter().GetResult()
        $capture = Join-Path $lab "cbr-timeclocks-$stamp-$Name-output.txt"
        Assert-LabNoReparsePath $capture
        [IO.File]::WriteAllText($capture, $output, $utf8)
        Assert-LabWeiDUResult -ExitCode $process.ExitCode -Text $output
    }
    finally { $process.Dispose() }
}

function Read-LabStack {
    $logPath = Join-Path $lab 'WeiDU.log'
    Assert-LabNoReparsePath $logPath
    $stack = Get-LabWeiDUStack ([IO.File]::ReadAllText($logPath))
    if ((@($stack.EEex) -join ',') -cne '0,1,8') { throw 'CBR_LAB EEEX_COMPONENTS_INCOMPLETE' }
    $stack
}

$mutex = [Threading.Mutex]::new($false, 'Local\ChrizInfinityEngineLab')
$owned = $false
try {
    try { $owned = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $owned = $true }
    if (-not $owned) { throw 'Another cooperating lab owns the runtime mutex.' }
    $lab = Assert-LabRoot
    $manifest = Read-LabManifest
    Assert-LabProfile $manifest
    if ($manifest.Phase -cne 'Validated') { throw 'Validate the lab before installing the mod.' }
    Assert-LabNoGameProcess
    $mod = ConvertTo-LabFullPath $ModRoot
    if (Test-LabPathWithin -Path $mod -Root $lab) { throw 'CBR_LAB INPUT_INSIDE_DESTINATION' }
    Assert-LabNoReparsePath $mod
    $source = Get-VerifiedModSource $mod
    # Inspect every destination entry before WeiDU may write there.
    $null = @(Get-LabPhysicalFiles $lab)

    $recordPath = Join-Path $lab 'cbr-timeclocks.json'
    Assert-LabNoReparsePath $recordPath
    $record = if (Test-Path -LiteralPath $recordPath) { [IO.File]::ReadAllText($recordPath) | ConvertFrom-Json } else { $null }
    if ($record -and $record.InstanceId -cne $manifest.InstanceId) { throw 'CBR_LAB TIMECLOCKS_RECORD_FOREIGN' }
    $stack = Read-LabStack
    $installed = @($stack.TimeClocks)
    if (-not $record) {
        # The first install: nothing of the mod may be there yet; this is the state to return to.
        if ($installed.Count -ne 0 -or (Test-Path -LiteralPath (Join-Path $lab $tp2Name)) -or
            (Test-Path -LiteralPath (Join-Path $lab $modFolder))) {
            throw 'CBR_LAB TIMECLOCKS_WITHOUT_RECORD_REVIEW_REQUIRED'
        }
        $base = Get-OwnedInventory
    }
    else {
        $base = $record.BaseInventory
        $logHash = Get-LabSha256 (Join-Path $lab 'WeiDU.log')
        if ($logHash -cne $record.WeiDULogSha256 -or (@($installed) -join ',') -cne (@($record.Components) -join ',')) {
            throw 'CBR_LAB TIMECLOCKS_RECORD_OUTDATED_REVIEW_REQUIRED'
        }
    }

    if ($installed.Count -gt 0) {
        $newestFirst = @($installed)
        [Array]::Reverse($newestFirst)
        Invoke-LabWeiDU -Name 'uninstall' -Arguments (@($tp2Name, '--game', $lab, '--language', '0',
            '--force-uninstall-list') + @($newestFirst | ForEach-Object { [string] $_ }))
        if (@((Read-LabStack).TimeClocks).Count -ne 0) { throw 'CBR_LAB TIMECLOCKS_UNINSTALL_INCOMPLETE' }
    }
    foreach ($relative in @('override/M_CBTC.lua', 'override/CBTCOPT.2DA', 'EEex_scripts/extra_pattern_dbs/CBTC.db')) {
        if (Test-Path -LiteralPath (Join-Path $lab $relative)) { throw "CBR_LAB TIMECLOCKS_FILE_LEFT: $relative" }
    }
    $after = Get-OwnedInventory
    if ($after.Digest -cne $base.Digest -or $after.Files -ne $base.Files) {
        throw 'CBR_LAB UNINSTALL_DID_NOT_RESTORE_OVERRIDE_REVIEW_REQUIRED'
    }

    # Replace the lab's copy of the mod; the old copy and its backup folder stay for review.
    $previous = $null
    foreach ($name in @($tp2Name, $modFolder)) {
        $path = Join-Path $lab $name
        Assert-LabNoReparsePath $path
        if (Test-Path -LiteralPath $path) {
            if (-not $previous) {
                $previous = Join-Path $lab "cbr-timeclocks-previous-$stamp"
                Assert-LabNoReparsePath $previous
                if (Test-Path -LiteralPath $previous) { throw 'CBR_LAB PREVIOUS_COPY_FOLDER_EXISTS' }
                $null = [IO.Directory]::CreateDirectory($previous)
            }
            Move-Item -LiteralPath $path -Destination (Join-Path $previous $name)
        }
    }
    foreach ($entry in $source.Files.GetEnumerator()) {
        $target = Join-Path $lab $entry.Key
        if (-not (Test-LabPathWithin -Path $target -Root $lab)) { throw 'CBR_LAB COPY_OUTSIDE_LAB' }
        Assert-LabNoReparsePath $target
        $null = [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))
        [IO.File]::Copy((Join-Path $source.Root $entry.Key), $target, $false)
        if ((Get-LabSha256 $target) -cne $entry.Value) { throw "CBR_LAB COPY_HASH_MISMATCH: $($entry.Key)" }
    }

    $files = [ordered]@{}
    $switches = Get-LabTimeClocksSwitches $Components
    if ($Components.Count -gt 0) {
        Invoke-LabWeiDU -Name 'install' -Arguments (@($tp2Name, '--game', $lab, '--language', '0', '--use-lang', 'en_US',
            '--skip-at-view', '--force-install-list') + @($Components | ForEach-Object { [string] $_ }))
        if ((@((Read-LabStack).TimeClocks) -join ',') -cne ($Components -join ',')) { throw 'CBR_LAB TIMECLOCKS_COMPONENTS_DIFFER' }
        foreach ($pair in @(@('override/M_CBTC.lua', "$modFolder/M_CBTC.lua"),
                @('EEex_scripts/extra_pattern_dbs/CBTC.db', "$modFolder/CBTC.db"))) {
            $hash = Get-LabSha256 (Join-Path $lab $pair[0])
            if ($hash -cne $source.Files[$pair[1]]) { throw "CBR_LAB INSTALLED_FILE_DIFFERS: $($pair[0])" }
            $files[$pair[0]] = $hash
        }
        $tablePath = Join-Path $lab 'override/CBTCOPT.2DA'
        $table = Read-LabTimeClocksTable ([IO.File]::ReadAllText($tablePath))
        if ((@($table.Keys) -join ',') -cne (@($switches.Keys) -join ',')) { throw 'CBR_LAB TIMECLOCKS_TABLE_ROWS_DIFFER' }
        foreach ($name in $switches.Keys) {
            if ($table[$name] -ne $switches[$name]) { throw "CBR_LAB TIMECLOCKS_SWITCH_DIFFERS: $name" }
        }
        $files['override/CBTCOPT.2DA'] = Get-LabSha256 $tablePath
    }

    $history = @(if ($record -and $record.PSObject.Properties['History']) { $record.History })
    $state = [ordered]@{Schema = 1; InstanceId = $manifest.InstanceId; ModRoot = $source.Root; ModCommit = $source.Commit
        ModFiles = $source.Files; Components = @($Components); Switches = $switches
        WeiDULogSha256 = Get-LabSha256 (Join-Path $lab 'WeiDU.log'); Installed = $files; BaseInventory = $base
        PreviousCopy = $previous; InstalledUtc = [DateTime]::UtcNow.ToString('o')
        History = @($history + [pscustomobject]@{Utc = $stamp; ModCommit = $source.Commit; Components = @($Components)})
        GameLaunched = $false}
    [IO.File]::WriteAllText($recordPath, ($state | ConvertTo-Json -Depth 6), $utf8)
    [pscustomobject]@{LabRoot = $lab; ModCommit = $source.Commit; Components = @($Components); Switches = $switches
        Uninstalled = $installed; GameLaunched = $false} | ConvertTo-Json -Compress -Depth 4
}
finally {
    if ($owned) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
