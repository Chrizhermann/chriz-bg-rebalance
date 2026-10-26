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
$valid = [pscustomobject]@{
    SchemaVersion=1; LabId='cbr-timestop-2730'; InstanceId=[guid]::NewGuid().ToString()
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
    Must-Reject { Assert-LabManifestValues ([pscustomobject]@{LabId='cbr-timestop-2730'}) } 'INVALID_OWNERSHIP_MARKER'
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

    # Synthetic process lists and a fixture coordination folder: the PC's real processes,
    # locks and slots are never read here, and no game folder is written.
    $coordination = Join-Path $fixture 'coordination'
    $otherLab = Join-Path $fixture 'other-lab'
    $stockGame = Join-Path $fixture 'stock-game' # no engine.lua: the engine's stock profile
    $labCopy = Join-Path $fixture 'lab-copy'
    foreach ($folder in @($coordination, $otherLab, $stockGame, $labCopy)) { $null = [IO.Directory]::CreateDirectory($folder) }
    [IO.File]::WriteAllText((Join-Path $otherLab 'engine.lua'),
        "engine_name = `"Other Lab 2730`"`r`nengine_mode = 1 -- 0 = BGEE, 1 = BG2EE, 2 = IWDEE`r`n")
    [IO.File]::WriteAllText((Join-Path $labCopy 'engine.lua'), "engine_name = `"$($config.EngineName)`"`r`n")
    $documents = [IO.Path]::GetDirectoryName($config.ProfileRoot)
    $otherProfile = Join-Path $documents 'Other Lab 2730'
    function New-LabTestProcess {
        param([string] $Name, [AllowNull()][object] $Path)
        [pscustomobject]@{ProcessId=4242; Name=$Name; ExecutablePath=$Path}
    }
    function Write-LabTestSlot {
        param([string] $Name, [string] $Game, [string] $SlotProfile)
        [IO.File]::WriteAllText((Join-Path $coordination $Name), ([ordered]@{schema='bg-lab-slot-v1'
            owner='Claude Code: guard test'; game=$Game.Replace('\', '/'); profile=$SlotProfile.Replace('\', '/')} | ConvertTo-Json))
    }
    $otherGames = @(
        (New-LabTestProcess 'Baldur.exe' (Join-Path $otherLab 'Baldur.exe')),
        (New-LabTestProcess 'InfinityLoader.exe' (Join-Path $otherLab 'InfinityLoader.exe')),
        (New-LabTestProcess 'icewind.exe' (Join-Path $stockGame 'icewind.exe')),
        (New-LabTestProcess 'Baldur.exe' ($config.LabRoot + '-other\Baldur.exe')))
    $ownGame = New-LabTestProcess 'Baldur.exe' (Join-Path $config.LabRoot 'Baldur.exe')
    Check "Another lab's game, loader or slot leaves staging allowed" {
        Write-LabTestSlot 'bg-lab-slot-1.lock' $otherLab $otherProfile
        [IO.File]::WriteAllText((Join-Path $coordination 'bg-game-install.lock.released-20261026T010203Z-0123abcd'), '{}')
        Write-LabTestSlot 'bg-lab-slot-2.lock.released-20261026T010203Z-4567cdef' $config.LabRoot $config.ProfileRoot
        $unrelated = @(
            (New-LabTestProcess 'weidu.exe' (Join-Path $otherLab 'weidu.exe')),
            (New-LabTestProcess 'conhost.exe' '\\?\C:\WINDOWS\system32\conhost.exe'),
            # Many system processes never show their path to a normal shell.
            (New-LabTestProcess 'svchost.exe' $null), (New-LabTestProcess 'setup-other.exe' $null))
        Assert-LabNoGameProcess -Processes ($otherGames + $unrelated) -CoordinationRoot $coordination
        Assert-LabNoGameProcess -Processes @() -CoordinationRoot $coordination
        # Without the shared coordination folder nothing is reserved.
        Assert-LabNoGameProcess -Processes $otherGames -CoordinationRoot (Join-Path $fixture 'missing\coordination')
    }
    Check "This lab's game, loader, installer or profile refuses staging, also beside other labs" {
        foreach ($process in @($ownGame,
                (New-LabTestProcess 'BALDUR.EXE' (Join-Path $config.LabRoot 'Baldur.exe').ToUpperInvariant()),
                (New-LabTestProcess 'InfinityLoader.exe' ('\\?\' + (Join-Path $config.LabRoot 'InfinityLoader.exe'))),
                (New-LabTestProcess 'icewind.exe' (Join-Path $config.LabRoot 'icewind.exe')),
                (New-LabTestProcess 'weidu.exe' (Join-Path $config.LabRoot 'weidu.exe')),
                (New-LabTestProcess 'InfinityLoader.exe' (Join-Path $config.LabRoot 'EEex\loader\InfinityLoader.exe')),
                (New-LabTestProcess 'helper.exe' (Join-Path $config.ProfileRoot 'helper.exe')),
                # A copy of this lab, or this lab through another spelling of its path, uses its profile.
                (New-LabTestProcess 'Baldur.exe' (Join-Path $labCopy 'Baldur.exe')))) {
            Must-Reject { Assert-LabNoGameProcess -Processes @($process) -CoordinationRoot $coordination } 'GAME_PROCESS_OPEN'
        }
        Must-Reject { Assert-LabNoGameProcess -Processes ($otherGames + $ownGame) -CoordinationRoot $coordination } 'GAME_PROCESS_OPEN'
        foreach ($engine in @("engine_name = 'cbr timestop lab 2730' -- other case",
                "engine_name = `"$($config.EngineName). `"", "engine_name = `"$($config.EngineName)/nested`"",
                "engine_name = `"Old name`"`r`nengine_name = `"$($config.EngineName)`"")) {
            [IO.File]::WriteAllText((Join-Path $labCopy 'engine.lua'), $engine)
            Must-Reject { Assert-LabNoGameProcess -Processes @(New-LabTestProcess 'InfinityLoader.exe' (Join-Path $labCopy 'InfinityLoader.exe')) -CoordinationRoot $coordination } 'GAME_PROCESS_OPEN'
        }
    }
    Check 'A game or loader whose path or profile cannot be read refuses staging' {
        foreach ($process in @((New-LabTestProcess 'Baldur.exe' $null), (New-LabTestProcess 'InfinityLoader.exe' ''),
                (New-LabTestProcess 'ICEWIND.EXE' 'icewind.exe'), (New-LabTestProcess 'Baldur.exe' '\Device\HarddiskVolume3\Lab\Baldur.exe'),
                [pscustomobject]@{Name='Baldur.exe'})) {
            Must-Reject { Assert-LabNoGameProcess -Processes @($process) -CoordinationRoot $coordination } 'GAME_PROCESS_UNKNOWN'
        }
        $odd = Join-Path $fixture 'odd-engine'
        $null = [IO.Directory]::CreateDirectory($odd)
        $oddGame = New-LabTestProcess 'Baldur.exe' (Join-Path $odd 'Baldur.exe')
        foreach ($engine in @('engine_name = "CBR " .. suffix', 'engine_name = [[CBR TimeStop Lab 2730]]', 'engine_name = "a\"b"')) {
            [IO.File]::WriteAllText((Join-Path $odd 'engine.lua'), $engine)
            Must-Reject { Assert-LabNoGameProcess -Processes @($oddGame) -CoordinationRoot $coordination } 'GAME_PROCESS_UNKNOWN'
        }
        [IO.File]::WriteAllText((Join-Path $odd 'engine.lua'), 'engine_name = "Odd Lab"')
        $held = [IO.File]::Open((Join-Path $odd 'engine.lua'), 'Open', 'ReadWrite', 'None')
        try { Must-Reject { Assert-LabNoGameProcess -Processes @($oddGame) -CoordinationRoot $coordination } 'GAME_PROCESS_UNKNOWN' }
        finally { $held.Dispose() }
        Assert-LabNoGameProcess -Processes @($oddGame) -CoordinationRoot $coordination
        $folderEngine = Join-Path $fixture 'folder-engine'
        $null = [IO.Directory]::CreateDirectory((Join-Path $folderEngine 'engine.lua'))
        Must-Reject { Assert-LabNoGameProcess -Processes @(New-LabTestProcess 'icewind.exe' (Join-Path $folderEngine 'icewind.exe')) -CoordinationRoot $coordination } 'GAME_PROCESS_UNKNOWN'
    }
    Check 'The desktop launch refuses every game or loader, whatever its path or case' {
        foreach ($process in @($otherGames + $ownGame + [pscustomobject]@{Name='BALDUR.EXE'} + (New-LabTestProcess 'icewind.exe' $null))) {
            Must-Reject { Assert-LabNoGameProcess -Processes @($process) -CoordinationRoot $coordination -Anywhere } 'GAME_PROCESS_OPEN'
        }
        Must-Reject { Assert-LabNoGameProcess -Processes @(New-LabTestProcess 'weidu.exe' (Join-Path $config.LabRoot 'weidu.exe')) -CoordinationRoot $coordination -Anywhere } 'GAME_PROCESS_OPEN'
        Assert-LabNoGameProcess -Processes @(New-LabTestProcess 'pwsh.exe' 'C:\Program Files\PowerShell\7\pwsh.exe') -CoordinationRoot $coordination -Anywhere
        Assert-LabNoGameProcess -Processes @() -CoordinationRoot $coordination -Anywhere
    }
    Check 'The exclusive PC reservation refuses staging and launch, with every reason named' {
        $exclusive = Join-Path $coordination 'bg-game-install.lock'
        [IO.File]::WriteAllText($exclusive, '{"token":"0123abcd","owner":"Codex: install into another game","max_seconds":600}')
        Must-Reject { Assert-LabNoGameProcess -Processes @() -CoordinationRoot $coordination } 'EXCLUSIVE_LOCK_HELD'
        Must-Reject { Assert-LabNoGameProcess -Processes $otherGames -CoordinationRoot $coordination } 'Codex: install into another game'
        Must-Reject { Assert-LabNoGameProcess -Processes @() -CoordinationRoot $coordination -Anywhere } 'EXCLUSIVE_LOCK_HELD'
        [IO.File]::WriteAllText($exclusive, 'not a JSON record')
        Must-Reject { Assert-LabNoGameProcess -Processes @() -CoordinationRoot $coordination } 'EXCLUSIVE_LOCK_HELD'
        Must-Reject { Assert-LabNoGameProcess -Processes @($ownGame) -CoordinationRoot $coordination } 'GAME_PROCESS_OPEN'
        Must-Reject { Assert-LabNoGameProcess -Processes @($ownGame) -CoordinationRoot $coordination } 'EXCLUSIVE_LOCK_HELD'
        Remove-Item -LiteralPath $exclusive
        $null = [IO.Directory]::CreateDirectory($exclusive)
        Must-Reject { Assert-LabNoGameProcess -Processes @() -CoordinationRoot $coordination } 'EXCLUSIVE_LOCK_HELD'
        Remove-Item -LiteralPath $exclusive
        Assert-LabNoGameProcess -Processes $otherGames -CoordinationRoot $coordination
    }
    Check "A lab slot naming this lab's folder or profile refuses staging, an unreadable one too" {
        foreach ($pair in @(@($config.LabRoot, $config.ProfileRoot), @((Join-Path $config.LabRoot 'nested'), $otherProfile),
                @([IO.Path]::GetDirectoryName($config.LabRoot), $otherProfile), @($otherLab, $config.ProfileRoot),
                @($otherLab, (Join-Path $config.ProfileRoot 'nested')))) {
            Write-LabTestSlot 'bg-lab-slot-3.lock' $pair[0] $pair[1]
            Must-Reject { Assert-LabNoGameProcess -Processes @() -CoordinationRoot $coordination } 'LAB_SLOT_HELD'
        }
        # A profile that only contains this one is not written into by the slot's game.
        Write-LabTestSlot 'bg-lab-slot-3.lock' $otherLab $documents
        Assert-LabNoGameProcess -Processes @() -CoordinationRoot $coordination
        foreach ($text in @('{', '[]', '{"owner":"no folders"}', ('{"game":"eet","profile":"' + $otherProfile.Replace('\', '/') + '"}'))) {
            [IO.File]::WriteAllText((Join-Path $coordination 'bg-lab-slot-3.lock'), $text)
            Must-Reject { Assert-LabNoGameProcess -Processes @() -CoordinationRoot $coordination } 'LAB_SLOT_UNKNOWN'
        }
        Write-LabTestSlot 'bg-lab-slot-3.lock' $otherLab $otherProfile
        Assert-LabNoGameProcess -Processes $otherGames -CoordinationRoot $coordination
    }
    Check 'An unreadable coordination folder refuses; the default is the shared folder' {
        $notFolder = Join-Path $fixture 'coordination-file'
        [IO.File]::WriteAllText($notFolder, '')
        Must-Reject { Assert-LabNoGameProcess -Processes @() -CoordinationRoot $notFolder } 'COORDINATION_UNREADABLE'
        if ($config.CoordinationRoot -cne (Join-Path $env:USERPROFILE '.codex\coordination')) { throw 'Not the shared coordination folder.' }
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
