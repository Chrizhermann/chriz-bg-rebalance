#Requires -Version 7.0
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Lab.Common.ps1')
$script:passed = 0

function Check {
    param([string] $Name, [scriptblock] $Body)
    & $Body
    $script:passed++
    Write-Output "PASS $Name"
}

function Must-Reject {
    param([scriptblock] $Body, [string] $Code)
    $failure = $null
    try { $null = & $Body }
    catch { $failure = $_.Exception.Message }
    if ($null -eq $failure -or -not $failure.Contains($Code, [StringComparison]::Ordinal)) {
        throw "Expected $Code, got: $failure"
    }
}

$config = Get-LabConfiguration
Check 'Each lab variant has its own folder, profile, ID and markers; unknown variants fail' {
    $saved = $env:CBR_LAB_VARIANT
    try {
        $labs = @{}
        foreach ($variant in @('', 'timestop', 'timeclocks')) {
            $env:CBR_LAB_VARIANT = $variant
            $labs[$variant] = Get-LabConfiguration
        }
        $documents = [IO.Path]::GetDirectoryName($config.ProfileRoot)
        foreach ($expected in @(
                @('', 'timestop', 'CBR-TimeStop-2.7.3.0', 'CBR TimeStop Lab 2730', 'cbr-timestop-2730', '.cbr-timestop-lab.json'),
                @('timestop', 'timestop', 'CBR-TimeStop-2.7.3.0', 'CBR TimeStop Lab 2730', 'cbr-timestop-2730', '.cbr-timestop-lab.json'),
                @('timeclocks', 'timeclocks', 'CBR-TimeClocks-2.7.3.0', 'CBR TimeClocks Lab 2730', 'cbr-timeclocks-2730', '.cbr-timeclocks-lab.json'))) {
            $lab = $labs[$expected[0]]
            if ($lab.Variant -cne $expected[1] -or $lab.LabRoot -cne (Join-Path $env:USERPROFILE ('Games\' + $expected[2])) -or
                $lab.EngineName -cne $expected[3] -or $lab.ProfileRoot -cne (Join-Path $documents $expected[3]) -or
                $lab.LabId -cne $expected[4] -or $lab.MarkerName -cne $expected[5] -or $lab.IdText -cne ($expected[3] + "`n") -or
                $lab.SourceRoot -cne $config.SourceRoot -or $lab.ExeSha256 -cne $config.ExeSha256 -or
                $lab.EEexCommit -cne $config.EEexCommit) {
                throw "Wrong configuration for variant '$($expected[0])'."
            }
        }
        foreach ($name in @('LabRoot', 'ProfileRoot', 'EngineName', 'LabId', 'MarkerName', 'IdText')) {
            if ($labs['timestop'].$name -ieq $labs['timeclocks'].$name) { throw "The labs share $name." }
        }
        foreach ($variant in @('TimeClocks', 'timeclocks ', 'other')) {
            $env:CBR_LAB_VARIANT = $variant
            Must-Reject { Get-LabConfiguration } 'UNKNOWN_VARIANT'
        }
        # A marker of the one lab is never accepted as the other's.
        $env:CBR_LAB_VARIANT = 'timeclocks'
        $other = $labs['timestop']
        $foreign = [pscustomobject]@{
            SchemaVersion=1; LabId=$other.LabId; InstanceId=[guid]::NewGuid().ToString()
            LabRoot=$other.LabRoot; ProfileRoot=$other.ProfileRoot; EngineName=$other.EngineName
            SourceRoot=$other.SourceRoot; ExeSha256=$other.ExeSha256; EEexCommit=$other.EEexCommit; Phase='Validated'
        }
        Must-Reject { Assert-LabManifestValues $foreign } 'INVALID_OWNERSHIP_MARKER'
        Must-Reject { Assert-LabRoot $other.LabRoot } 'EXACT_DISPOSABLE_ROOT_REQUIRED'
        $own = $labs['timeclocks']
        $ownMarker = $foreign | ConvertTo-Json | ConvertFrom-Json
        $ownMarker.LabId = $own.LabId; $ownMarker.LabRoot = $own.LabRoot; $ownMarker.ProfileRoot = $own.ProfileRoot
        $ownMarker.EngineName = $own.EngineName
        Assert-LabManifestValues $ownMarker
        $ownMarker.LabId = $other.LabId
        Must-Reject { Assert-LabManifestValues $ownMarker } 'INVALID_OWNERSHIP_MARKER'
    }
    finally {
        if ($null -eq $saved) { Remove-Item Env:\CBR_LAB_VARIANT -ErrorAction SilentlyContinue }
        else { $env:CBR_LAB_VARIANT = $saved }
    }
}
Check 'Exact lab root accepted without creating it' {
    if ((Assert-LabRoot) -cne $config.LabRoot) { throw 'Wrong lab path.' }
}
Check 'Playthrough and sibling roots rejected' {
    Must-Reject { Assert-LabRoot "C:\Games\Baldur's Gate II Enhanced Edition modded" } 'EXACT_DISPOSABLE_ROOT_REQUIRED'
    Must-Reject { Assert-LabRoot ($config.LabRoot + '-other') } 'EXACT_DISPOSABLE_ROOT_REQUIRED'
    Must-Reject { Assert-LabRoot ($config.LabRoot + '\..\another') } 'EXACT_DISPOSABLE_ROOT_REQUIRED'
    Must-Reject { Assert-LabRoot ($config.LabRoot + '\bg2') } 'EXACT_DISPOSABLE_ROOT_REQUIRED'
}
Check 'Relative paths and sibling prefix rejected' {
    Must-Reject { ConvertTo-LabFullPath '..\Games' } 'ABSOLUTE_PATH_REQUIRED'
    Must-Reject { ConvertTo-LabFullPath 'C:Games' } 'ABSOLUTE_PATH_REQUIRED'
    if (Test-LabPathWithin -Path ($config.LabRoot + '-other\file') -Root $config.LabRoot) { throw 'Accepted sibling prefix.' }
    if (-not (Test-LabPathWithin -Path ($config.LabRoot + '\override\file') -Root $config.LabRoot)) { throw 'Rejected child.' }
}
Check 'Only Microsoft Cloud variants qualify; surrogate and unknown tags fail' {
    foreach ($variant in 0..15) {
        if (-not (Test-LabCloudReparseTag ([uint32](0x9000001AL + ($variant * 0x1000))))) {
            throw "Rejected Cloud variant $variant."
        }
    }
    foreach ($hex in @('A0000003', 'A000000C', 'B000701A', '1000701A', '9001001A', '9000701B', '80000021')) {
        if (Test-LabCloudReparseTag ([Convert]::ToUInt32($hex, 16))) { throw "Accepted unknown or surrogate tag $hex." }
    }
}
Check 'Cloud exception is confined to OS Documents ancestry and exact profile' {
    $documents = [IO.Path]::GetDirectoryName($config.ProfileRoot)
    if (-not (Test-LabCloudProfileScope -Path $documents -RequestedPath $config.ProfileRoot)) { throw 'Documents ancestor rejected.' }
    if (-not (Test-LabCloudProfileScope -Path ($config.ProfileRoot + '\Baldur.lua') -RequestedPath $config.ProfileRoot)) { throw 'Own profile rejected.' }
    foreach ($path in @($config.LabRoot, $config.SourceRoot, ($config.ProfileRoot + '-other'), (Join-Path $documents 'Another game'))) {
        if (Test-LabCloudProfileScope -Path $path -RequestedPath $path) { throw "Cloud allowance leaked to $path." }
    }
    if (Test-LabCloudProfileScope -Path $documents -RequestedPath $config.LabRoot) { throw 'Documents ancestor relaxed executable guard.' }
}
Check 'Actual OS Documents profile ancestry passes read-only metadata verification' {
    Assert-LabNoReparsePath $config.ProfileRoot
}
Check 'Either game or loader blocks regardless of path or case' {
    Must-Reject { Assert-LabNoGameProcess -Processes @([pscustomobject]@{Name='BALDUR.EXE'}) } 'GAME_PROCESS_OPEN'
    Must-Reject { Assert-LabNoGameProcess -Processes @([pscustomobject]@{Name='InfinityLoader.exe'}) } 'GAME_PROCESS_OPEN'
    Assert-LabNoGameProcess -Processes @([pscustomobject]@{Name='pwsh.exe'})
    Assert-LabNoGameProcess -Processes @()
}
$valid = [pscustomobject]@{
    SchemaVersion=1; LabId=$config.LabId; InstanceId=[guid]::NewGuid().ToString()
    LabRoot=$config.LabRoot; ProfileRoot=$config.ProfileRoot; EngineName=$config.EngineName
    SourceRoot=$config.SourceRoot; ExeSha256=$config.ExeSha256; EEexCommit=$config.EEexCommit; Phase='Copying'
}
Check 'Ownership marker binds root, profile and version' {
    Assert-LabManifestValues $valid
    foreach ($name in @('LabRoot','ProfileRoot','EngineName','SourceRoot','ExeSha256','EEexCommit','InstanceId','Phase')) {
        $bad = $valid | ConvertTo-Json | ConvertFrom-Json
        $bad.$name = 'unrelated'
        Must-Reject { Assert-LabManifestValues $bad } 'INVALID_OWNERSHIP_MARKER'
    }
    Must-Reject { Assert-LabManifestValues ([pscustomobject]@{LabId=$config.LabId}) } 'INVALID_OWNERSHIP_MARKER'
    $previousPin = $valid | ConvertTo-Json | ConvertFrom-Json
    $previousPin.EEexCommit = '9e8098ee696ca4b0bc055e7ff74b283704a8c02e' # EEex v1.3.0
    Must-Reject { Assert-LabManifestValues $previousPin } 'INVALID_OWNERSHIP_MARKER'
}
Check 'WeiDU late errors and skipped components fail even with exit zero' {
    Assert-LabWeiDUResult -ExitCode 0 -Text 'SUCCESSFULLY INSTALLED'
    foreach ($text in @('SKIPPING: prerequisite', 'NOT INSTALLED', "SUCCESSFULLY INSTALLED`nERROR: TLK locked",
        'FATAL ERROR', 'FAILURE: no game', 'Sys_error("permission denied")')) {
        Must-Reject { Assert-LabWeiDUResult -ExitCode 0 -Text $text } 'WEIDU_INSTALL_FAILED_REVIEW_LOG'
    }
    Must-Reject { Assert-LabWeiDUResult -ExitCode 1 -Text 'SUCCESSFULLY INSTALLED' } 'WEIDU_INSTALL_FAILED_REVIEW_LOG'
}
# WeiDU's own CRLF log format, with the English component names of EEex v1.3.1.
$logHeader = "// Log of Currently Installed WeiDU Mods`r`n// The top of the file is the 'oldest' mod`r`n" +
    "// ~TP2_File~ #language_number #component_number // [Subcomponent Name -> ] Component Name [ : Version]"
$eeexLine = @{
    0 = '~EEEX/EEEX.TP2~ #0 #0 // Quick Menu Core: v1.3.1'
    1 = '~EEEX/EEEX.TP2~ #0 #1 // EEex: v1.3.1'
    8 = '~EEEX/EEEX.TP2~ #0 #8 // Experimental - Use LuaJIT: Can help stuttering | WARNING: May cause crashes when combined with certain mods: v1.3.1'
    9 = '~EEEX/EEEX.TP2~ #0 #9 // Enable attack info module: Show to-hit chances when hovering attack cursor over target: v1.3.1'
}
$fullLog = (@($logHeader, $eeexLine[0], $eeexLine[1], $eeexLine[8]) -join "`r`n") + "`r`n"
Check 'Only official 1.3.1 components in installation order are accepted' {
    if ((@(Get-LabEEexComponents $fullLog) -join ',') -cne '0,1,8') { throw 'Correct stack rejected.' }
    if ((@(Get-LabEEexComponents ($fullLog -replace "`r`n", "`n")) -join ',') -cne '0,1,8') { throw 'LF stack rejected.' }
    if ((@(Get-LabEEexComponents "~EEEX/EEEX.TP2~ #0 #0 // Quick Menu Core: v$($config.EEexVersion)") -join ',') -cne '0') {
        throw 'Log version pin disagrees with the configured EEex version.'
    }
    if (@(Get-LabEEexComponents "// ~EEEX.TP2~ #0 #0 // removed: v1.3.1").Count -ne 0) { throw 'Inactive entry accepted.' }
    Must-Reject { Get-LabEEexComponents ($fullLog + '~EEEX.TP2~ #0 #8 // duplicate: v1.3.1') } 'INVALID_COMPONENT_ORDER_OR_DUPLICATE'
    Must-Reject { Get-LabEEexComponents '~EEEX.TP2~ #0 #8 // wrong order: v1.3.1' } 'INVALID_COMPONENT_ORDER_OR_DUPLICATE'
    Must-Reject { Get-LabEEexComponents '~ANOTHER.TP2~ #0 #0 // another: v1.3.1' } 'UNEXPECTED_WEIDU_COMPONENT_OR_VERSION'
    Must-Reject { Get-LabEEexComponents '~EEEX.TP2~ #0 #0 // old: v1.2.0' } 'UNEXPECTED_WEIDU_COMPONENT_OR_VERSION'
}
$clockLine = @{
    100 = '~SETUP-CHRIZ-BG-TIME-CLOCKS.TP2~ #0 #100 // Time Stop: the effects of frozen creatures wait out the stop: v0.1.0-proto'
    110 = '~SETUP-CHRIZ-BG-TIME-CLOCKS.TP2~ #0 #110 // Time Stop option: effects put on frozen creatures during the stop run on: v0.1.0-proto'
    200 = '~SETUP-CHRIZ-BG-TIME-CLOCKS.TP2~ #0 #200 // Haste and Slow: regeneration, poison and other periodic effects at the normal rate: v0.1.0-proto'
    220 = '~SETUP-CHRIZ-BG-TIME-CLOCKS.TP2~ #0 #220 // Haste and Slow option: Slow keeps the game''s halved rate: v0.1.0-proto'
    230 = '~SETUP-CHRIZ-BG-TIME-CLOCKS.TP2~ #0 #230 // Haste: hasted creatures check their effects'' expiry once per second, as at normal speed: v0.1.0-proto'
}
Check 'Time Clocks components follow EEex in the Time Clocks lab only' {
    $saved = $env:CBR_LAB_VARIANT
    try {
        $env:CBR_LAB_VARIANT = 'timeclocks'
        $stack = Get-LabWeiDUStack $fullLog
        if ((@($stack.EEex) -join ',') -cne '0,1,8' -or @($stack.TimeClocks).Count -ne 0) { throw 'EEex-only log misread.' }
        $withMod = $fullLog + (@($clockLine[100], $clockLine[110], $clockLine[200], $clockLine[230]) -join "`r`n") + "`r`n" +
            "// Recently Uninstalled: ~SETUP-CHRIZ-BG-TIME-CLOCKS.TP2~ #0 #120`r`n"
        $stack = Get-LabWeiDUStack $withMod
        if ((@($stack.EEex) -join ',') -cne '0,1,8' -or (@($stack.TimeClocks) -join ',') -cne '100,110,200,230') { throw 'Mod stack misread.' }
        $folder = $withMod.Replace('~SETUP-CHRIZ-BG-TIME-CLOCKS.TP2~ #0 #230', '~chriz-bg-time-clocks/setup-chriz-bg-time-clocks.tp2~ #0 #230')
        if ((@((Get-LabWeiDUStack $folder).TimeClocks) -join ',') -cne '100,110,200,230') { throw 'Folder spelling misread.' }
        foreach ($bad in @(
                ($fullLog.Replace($eeexLine[8], $clockLine[100] + "`r`n" + $eeexLine[8])),   # EEex after the mod
                ($fullLog + $clockLine[110] + "`r`n"),                                        # option without its base
                ($fullLog + $clockLine[200] + "`r`n" + $clockLine[100] + "`r`n"),             # not ascending
                ($fullLog + $clockLine[100] + "`r`n" + $clockLine[100] + "`r`n"),             # twice
                ($fullLog + $clockLine[100].Replace('#100', '#130') + "`r`n"),                # unknown component
                ($fullLog + $clockLine[100] + "`r`n" + '~OTHER.TP2~ #0 #0 // other: v1' + "`r`n"))) {
            $failure = $null
            try { $null = Get-LabWeiDUStack $bad } catch { $failure = $_.Exception.Message }
            if ($null -eq $failure -or $failure -notmatch 'CBR_LAB (UNEXPECTED_WEIDU_COMPONENT_OR_VERSION|TIMECLOCKS_|UNKNOWN_TIMECLOCKS_COMPONENT)') {
                throw "Accepted or misreported: $bad -> $failure"
            }
        }
        $env:CBR_LAB_VARIANT = 'timestop'
        Must-Reject { Get-LabWeiDUStack ($fullLog + $clockLine[100] + "`r`n") } 'UNEXPECTED_WEIDU_COMPONENT_OR_VERSION'
        if ((@((Get-LabWeiDUStack $fullLog).EEex) -join ',') -cne '0,1,8') { throw 'Time Stop lab log misread.' }
    }
    finally {
        if ($null -eq $saved) { Remove-Item Env:\CBR_LAB_VARIANT -ErrorAction SilentlyContinue }
        else { $env:CBR_LAB_VARIANT = $saved }
    }
}
Check 'Time Clocks components set exactly their switches' {
    $names = 'TIME_STOP,STOP_NEW_EFFECTS,STOP_ACTORS,HASTE,HASTE_SCOPE,SLOW,HASTE_EXPIRY'
    foreach ($case in @(
            @(@(), '0,0,0,0,0,0,0'), @(@(100, 200), '1,0,0,1,0,1,0'), @(@(100, 110), '1,1,0,0,0,0,0'),
            @(@(100, 120, 200), '1,0,1,1,0,1,0'), @(@(200, 210), '0,0,0,1,1,1,0'), @(@(200, 220), '0,0,0,1,0,0,0'),
            @(@(100, 200, 220, 230), '1,0,0,1,0,0,1'), @(@(230), '0,0,0,0,0,0,1'))) {
        $switches = Get-LabTimeClocksSwitches $case[0]
        if ((@($switches.Keys) -join ',') -cne $names -or (@($switches.Values) -join ',') -cne $case[1]) {
            throw "Wrong switches for $($case[0] -join ','): $(@($switches.Values) -join ',')"
        }
    }
    Must-Reject { Get-LabTimeClocksSwitches @(110) } 'TIMECLOCKS_OPTION_WITHOUT_BASE'
    Must-Reject { Get-LabTimeClocksSwitches @(220) } 'TIMECLOCKS_OPTION_WITHOUT_BASE'
    Must-Reject { Get-LabTimeClocksSwitches @(200, 100) } 'TIMECLOCKS_COMPONENTS_NOT_ASCENDING'
    Must-Reject { Get-LabTimeClocksSwitches @(100, 100) } 'TIMECLOCKS_COMPONENTS_NOT_ASCENDING'
    Must-Reject { Get-LabTimeClocksSwitches @(100, 300) } 'UNKNOWN_TIMECLOCKS_COMPONENT'
    $shipped = "2DA V1.0`r`n0`r`n                 VALUE`r`nTIME_STOP        1`r`nSTOP_NEW_EFFECTS 0`r`nSLOW 1`r`n"
    $table = Read-LabTimeClocksTable $shipped
    if ((@($table.Keys) -join ',') -cne 'TIME_STOP,STOP_NEW_EFFECTS,SLOW' -or (@($table.Values) -join ',') -cne '1,0,1') { throw 'Table misread.' }
    foreach ($bad in @("2DA V1.0`n0`nOTHER`nTIME_STOP 1`n", "2DA V1.0`n0`nVALUE`nTIME_STOP 1`nTIME_STOP 0`n",
            "2DA V1.0`n0`nVALUE`nTIME_STOP one`n", "2DA V2.0`n0`nVALUE`nTIME_STOP 1`n", "")) {
        Must-Reject { Read-LabTimeClocksTable $bad } 'TIMECLOCKS_TABLE_MALFORMED'
    }
}
Check 'The mod installer refuses the Time Stop lab before reading anything' {
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = (Get-Process -Id $PID).Path
    foreach ($argument in @('-NoProfile', '-NonInteractive', '-File', (Join-Path $PSScriptRoot 'Install-TimeClocks.ps1'),
            '-ModRoot', 'C:\does-not-exist', '-Components', '100')) { $start.ArgumentList.Add($argument) }
    $start.UseShellExecute = $false
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    foreach ($variant in @($null, 'timestop')) {
        $start.Environment.Remove('CBR_LAB_VARIANT') | Out-Null
        if ($variant) { $start.Environment['CBR_LAB_VARIANT'] = $variant }
        $process = [Diagnostics.Process]::Start($start)
        $out = $process.StandardOutput.ReadToEndAsync(); $err = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        $text = $out.GetAwaiter().GetResult() + $err.GetAwaiter().GetResult()
        if ($process.ExitCode -eq 0 -or $text -notmatch 'TIMECLOCKS_LAB_ONLY') { throw "Not refused for '$variant': $text" }
    }
}
Check 'Previous 1.3.0 pin and the unrequested Attack Info component are refused' {
    Must-Reject { Get-LabEEexComponents $fullLog.Replace(': v1.3.1', ': v1.3.0') } 'UNEXPECTED_WEIDU_COMPONENT_OR_VERSION'
    # Component 9 only enables an in-game UI module; this lab installs exactly 0, 1 and 8.
    Must-Reject { Get-LabEEexComponents $eeexLine[9] } 'UNEXPECTED_WEIDU_COMPONENT_OR_VERSION'
    Must-Reject { Get-LabEEexComponents (@($eeexLine[0], $eeexLine[1], $eeexLine[9], $eeexLine[8]) -join "`r`n") } 'UNEXPECTED_WEIDU_COMPONENT_OR_VERSION'
}

# Shortened from the lab's InfinityLoader.ini before and after its first launch on 2026-10-20;
# the loader mixes LF and CRLF lines and appends its cache lines with CRLF.
$loaderValidated = "[General]`n`nLuaPatchMode=REPLACE_INTERNAL_WITH_EXTERNAL`n`n; auto-generated below`n`n" +
    "[Auto-Generated]`n`n[Hardcoded_free]`r`nPattern=743753`r`nOperations=ADD -3`r`n"
$loaderLaunched = $loaderValidated.Replace("[Auto-Generated]`n", "[Auto-Generated]`nCachedExeTime=13426715583127`r`n").
    Replace("Operations=ADD -3`r`n", "Operations=ADD -3`r`nCachedAddress=5374075924`r`n")
Check 'Loader address cache is ignored, loader configuration changes are not' {
    if ((ConvertTo-LabLoaderConfiguration $loaderLaunched) -cne $loaderValidated) { throw 'Loader cache not removed exactly.' }
    if ((ConvertTo-LabLoaderConfiguration $loaderValidated) -cne $loaderValidated) { throw 'Validated configuration changed.' }
    foreach ($changed in @(
            $loaderLaunched.Replace('REPLACE_INTERNAL_WITH_EXTERNAL', 'INTERNAL'),
            $loaderLaunched.Replace("[General]`n", "[General]`nCachedAddress=1`n"),
            $loaderLaunched.Replace('CachedAddress=5374075924', 'CachedAddress=0x140000000'),
            $loaderLaunched.Replace('CachedAddress=5374075924', 'CachedAddress=1 ; note'),
            ($loaderLaunched + "LuaLibrary=other.dll`r`n"))) {
        if ((ConvertTo-LabLoaderConfiguration $changed) -ceq $loaderValidated) { throw 'Configuration change accepted.' }
    }
    Must-Reject { ConvertTo-LabLoaderConfiguration ($loaderLaunched + "[Auto-Generated]`r`n") } 'LOADER_CONFIGURATION_AMBIGUOUS'
}

$tempParent = ConvertTo-LabFullPath ([IO.Path]::GetTempPath())
Assert-LabNoReparsePath $tempParent
$fixture = Join-Path $tempParent ('cbr-lab-guards-' + [guid]::NewGuid().ToString('N'))
$null = [IO.Directory]::CreateDirectory($fixture)
$junction = Join-Path $fixture 'junction'
try {
    $physical = Join-Path $fixture 'physical'
    $null = [IO.Directory]::CreateDirectory($physical)
    [IO.File]::WriteAllText((Join-Path $physical 'payload.txt'), 'sentinel')
    Check 'Physical files enumerate without following links' {
        if (@(Get-LabPhysicalFiles $physical).Count -ne 1) { throw 'Physical tree count wrong.' }
    }
    $null = New-Item -ItemType Junction -Path $junction -Target $physical
    Check 'Junction paths and nested tree enumeration rejected' {
        Must-Reject { Assert-LabNoReparsePath (Join-Path $junction 'payload.txt') } 'REPARSE_PATH_REJECTED'
        Must-Reject { Get-LabPhysicalFiles $fixture } 'LINKED_TREE_ENTRY_REJECTED'
    }
    # Remove only the junction itself, after checking its exact synthetic path.
    if (-not (Test-LabPathWithin -Path $junction -Root $fixture)) { throw 'Unsafe fixture path.' }
    Remove-Item -LiteralPath $junction -Force
    $null = New-Item -ItemType HardLink -Path (Join-Path $fixture 'hardlink.txt') -Target (Join-Path $physical 'payload.txt')
    Check 'Hard-linked files cannot enter or become write targets in the lab' {
        Must-Reject { Assert-LabNoReparsePath (Join-Path $fixture 'hardlink.txt') } 'HARDLINK_REJECTED'
        Must-Reject { Get-LabPhysicalFiles $fixture } 'LINKED_TREE_ENTRY_REJECTED'
    }
    $loaderDirectory = Join-Path $fixture 'loader'
    $null = [IO.Directory]::CreateDirectory($loaderDirectory)
    Check 'Launched loader file hashes to the validated loader bytes' {
        $latin1 = [Text.Encoding]::Latin1
        $validatedPath = Join-Path $loaderDirectory 'validated.ini'
        $launchedPath = Join-Path $loaderDirectory 'launched.ini'
        [IO.File]::WriteAllBytes($validatedPath, $latin1.GetBytes($loaderValidated))
        [IO.File]::WriteAllBytes($launchedPath, $latin1.GetBytes($loaderLaunched))
        if ((Get-LabLoaderConfigurationSha256 $validatedPath) -cne (Get-LabSha256 $validatedPath)) { throw 'Validated loader hash changed.' }
        if ((Get-LabLoaderConfigurationSha256 $launchedPath) -cne (Get-LabSha256 $validatedPath)) { throw 'Launched loader file rejected.' }
    }
}
finally {
    $resolved = ConvertTo-LabFullPath $fixture
    if (-not (Test-LabPathWithin -Path $resolved -Root $tempParent) -or $resolved -eq $tempParent -or
        [IO.Path]::GetFileName($resolved) -notmatch '^cbr-lab-guards-[0-9a-f]{32}$') {
        throw 'Refused unsafe test cleanup.'
    }
    $link = Get-Item -LiteralPath $junction -Force -ErrorAction SilentlyContinue
    if ($null -ne $link -and ($link.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        Remove-Item -LiteralPath $junction -Force
    }
    Assert-LabNoReparsePath $resolved
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
Write-Output "PASS $script:passed guard groups; no game files or profiles touched."
