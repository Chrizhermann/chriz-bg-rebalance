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
Check 'Either game or loader blocks regardless of path or case' {
    Must-Reject { Assert-LabNoGameProcess -Processes @([pscustomobject]@{Name='BALDUR.EXE'}) } 'GAME_PROCESS_OPEN'
    Must-Reject { Assert-LabNoGameProcess -Processes @([pscustomobject]@{Name='InfinityLoader.exe'}) } 'GAME_PROCESS_OPEN'
    Assert-LabNoGameProcess -Processes @([pscustomobject]@{Name='pwsh.exe'})
    Assert-LabNoGameProcess -Processes @()
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
}
Check 'WeiDU late errors and skipped components fail even with exit zero' {
    Assert-LabWeiDUResult -ExitCode 0 -Text 'SUCCESSFULLY INSTALLED'
    foreach ($text in @('SKIPPING: prerequisite', 'NOT INSTALLED', "SUCCESSFULLY INSTALLED`nERROR: TLK locked",
        'FATAL ERROR', 'FAILURE: no game', 'Sys_error("permission denied")')) {
        Must-Reject { Assert-LabWeiDUResult -ExitCode 0 -Text $text } 'WEIDU_INSTALL_FAILED_REVIEW_LOG'
    }
    Must-Reject { Assert-LabWeiDUResult -ExitCode 1 -Text 'SUCCESSFULLY INSTALLED' } 'WEIDU_INSTALL_FAILED_REVIEW_LOG'
}
$fullLog = "~EEEX/EEEX.TP2~ #0 #0 // Quick Menu Core: v1.3.0`n~EEEX/EEEX.TP2~ #0 #1 // EEex: v1.3.0`n~EEEX/EEEX.TP2~ #0 #8 // LuaJIT: v1.3.0"
Check 'Only official 1.3.0 components in installation order are accepted' {
    if ((@(Get-LabEEexComponents $fullLog) -join ',') -cne '0,1,8') { throw 'Correct stack rejected.' }
    if (@(Get-LabEEexComponents "// ~EEEX.TP2~ #0 #0 // removed: v1.3.0").Count -ne 0) { throw 'Inactive entry accepted.' }
    Must-Reject { Get-LabEEexComponents ($fullLog + "`n~EEEX.TP2~ #0 #8 // duplicate: v1.3.0") } 'INVALID_COMPONENT_ORDER_OR_DUPLICATE'
    Must-Reject { Get-LabEEexComponents '~EEEX.TP2~ #0 #8 // wrong order: v1.3.0' } 'INVALID_COMPONENT_ORDER_OR_DUPLICATE'
    Must-Reject { Get-LabEEexComponents '~ANOTHER.TP2~ #0 #0 // another: v1.3.0' } 'UNEXPECTED_WEIDU_COMPONENT_OR_VERSION'
    Must-Reject { Get-LabEEexComponents '~EEEX.TP2~ #0 #0 // old: v1.2.0' } 'UNEXPECTED_WEIDU_COMPONENT_OR_VERSION'
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
