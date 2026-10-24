#Requires -Version 7.0
[CmdletBinding()]
# The Remote Console source may be any clean checkout or worktree at the pin, so a
# moved main checkout never has to be switched back for staging.
param([switch] $Refresh, [string] $RemoteConsoleRoot = 'C:\src\private\eeex-remote-console')
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Lab.Common.ps1')

function Get-VerifiedRemoteSource {
    param([string] $Root)
    $pin = '661927e56e28435541a3128568cd4ee6d5d80164'
    $head = @(& git -C $Root rev-parse HEAD 2>&1)
    if ($LASTEXITCODE -ne 0 -or $head.Count -ne 1 -or $head[0] -cne $pin) {
        throw "Remote console HEAD differs from the reviewed pin $pin. Pass -RemoteConsoleRoot with a clean checkout or worktree at that commit."
    }
    $files = @('eeexremote/M_EEexRC.lua', 'eeexremote/EEexRC.menu')
    $dirty = @(& git -C $Root status --porcelain --untracked-files=all -- @files 2>&1)
    if ($LASTEXITCODE -ne 0 -or $dirty.Count -ne 0) { throw 'Remote console source files must match their clean pinned revision.' }
    $blobs = [ordered]@{}
    $hashes = [ordered]@{}
    foreach ($relative in $files) {
        $path = Join-Path $Root $relative
        Assert-LabNoReparsePath $path
        $expected = @(& git -C $Root rev-parse ($pin + ':' + $relative) 2>&1)
        if ($LASTEXITCODE -ne 0 -or $expected.Count -ne 1) { throw 'Cannot read the pinned remote console blob.' }
        # --path honors the repository's checkout/EOL conversion; raw SHA256 below
        # separately identifies the exact bytes copied to the Windows game.
        $actual = @(& git -C $Root hash-object ('--path=' + $relative) -- $path 2>&1)
        if ($LASTEXITCODE -ne 0 -or $actual.Count -ne 1 -or $actual[0] -cne $expected[0]) {
            throw 'Remote console bytes do not match the pinned Git source.'
        }
        $blobs[$relative] = [string] $expected[0]
        $hashes[$relative] = Get-LabSha256 $path
    }
    [pscustomobject]@{Root=$Root; Commit=[string]$head[0]; GitBlobs=$blobs; Sha256=$hashes}
}

function Get-CurrentFixtureSpecification {
    $builder = Join-Path $PSScriptRoot 'build_fixtures.py'
    $encoder = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) 'tests\ie_formats.py'
    $builderHash = Get-LabSha256 $builder
    $encoderHash = Get-LabSha256 $encoder
    $program = @'
import hashlib, importlib.util, json, sys
spec = importlib.util.spec_from_file_location("cbr_lab_fixture_spec", sys.argv[1])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
files = {name: hashlib.sha256(data).hexdigest() for name, data in module.fixture_bytes().items()}
digest = hashlib.sha256("".join(f"{name}\t{files[name]}\n" for name in sorted(files)).encode()).hexdigest()
print(json.dumps({"Files":files, "Digest":digest}, separators=(",", ":")))
'@
    $result = @(& python -B -c $program $builder)
    if ($LASTEXITCODE -ne 0 -or $result.Count -ne 1) { throw 'Cannot derive the current deterministic fixture specification.' }
    if ((Get-LabSha256 $builder) -cne $builderHash -or (Get-LabSha256 $encoder) -cne $encoderHash) {
        throw 'Fixture sources changed while deriving their specification.'
    }
    $specification = $result[0] | ConvertFrom-Json
    [pscustomobject]@{Files=$specification.Files; Digest=$specification.Digest;
        BuilderSha256=$builderHash; EncoderSha256=$encoderHash}
}

function Get-CurrentQAMenu {
    # The lab-only UI.MENU copy that names stock buttons for queued clicks (qa_menu.py).
    param([Parameter(Mandatory)][string] $Lab)
    $builder = Join-Path $PSScriptRoot 'qa_menu.py'
    $builderHash = Get-LabSha256 $builder
    $result = @(& python -B $builder describe $Lab)
    if ($LASTEXITCODE -ne 0 -or $result.Count -ne 1) { throw 'Cannot derive the QA menu from the stock UI.MENU.' }
    if ((Get-LabSha256 $builder) -cne $builderHash) { throw 'QA menu builder changed while deriving it.' }
    $description = $result[0] | ConvertFrom-Json
    if ($description.sha256 -notmatch '^[0-9a-f]{64}$') { throw 'Invalid QA menu description.' }
    [pscustomobject]@{Sha256=[string]$description.sha256; StockSha256=[string]$description.stock_sha256;
        BuilderSha256=$builderHash}
}

$mutex = [Threading.Mutex]::new($false, 'Local\ChrizInfinityEngineLab')
$owned = $false
try {
try { $owned = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $owned = $true }
if (-not $owned) { throw 'Another cooperating lab owns the runtime mutex.' }
$config = Get-LabConfiguration
$lab = Assert-LabRoot
$manifest = Read-LabManifest
Assert-LabProfile $manifest
if ($manifest.Phase -cne 'Validated') { throw 'Validate the baseline lab before staging diagnostics.' }
Assert-LabNoGameProcess
$marker = Join-Path $lab 'cbr-diagnostics.json'
Assert-LabNoReparsePath $marker
$old = if (Test-Path -LiteralPath $marker) { Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json } else { $null }
if ($old -and $old.InstanceId -cne $manifest.InstanceId) { throw 'Diagnostic ownership mismatch.' }

$remote = ConvertTo-LabFullPath $RemoteConsoleRoot
if (Test-LabPathWithin -Path $remote -Root $lab) { throw 'Remote console source must not be inside the lab.' }
$remoteSource = Get-VerifiedRemoteSource $remote
$fixtures = Get-CurrentFixtureSpecification
# A content-specific folder lets an explicit refresh create revised fixtures
# without overwriting or deleting the preceding experiment's inputs.
$generated = Join-Path $lab ('cbr-generated-fixtures-' + $fixtures.Digest.Substring(0, 16))
Assert-LabNoReparsePath $generated
if (-not (Test-Path -LiteralPath $generated)) {
    & python -B (Join-Path $PSScriptRoot 'build_fixtures.py') $generated
    if ($LASTEXITCODE -ne 0) { throw 'Fixture generation failed.' }
}
foreach ($entry in $fixtures.Files.PSObject.Properties) {
    if ((Get-LabSha256 (Join-Path $generated $entry.Name)) -cne $entry.Value) {
        throw "Generated fixture differs from the current deterministic builder: $($entry.Name)"
    }
}
$sources = [ordered]@{
    'override\CBRTObs.lua' = Join-Path $PSScriptRoot 'CBRTObs.lua'
    'override\CBRTFix.lua' = Join-Path $PSScriptRoot 'CBRTFix.lua'
    'override\M_CBRTS.lua' = Join-Path $PSScriptRoot 'M_CBRTS.lua'
    'override\M_EEexRC.lua' = Join-Path $remote 'eeexremote\M_EEexRC.lua'
    'override\EEexRC.menu' = Join-Path $remote 'eeexremote\EEexRC.menu'
}
foreach ($entry in $fixtures.Files.PSObject.Properties) {
    $sources["override\$($entry.Name)"] = Join-Path $generated $entry.Name
}
# Built from the stock UI.MENU in the lab's own BIF, never from an override copy.
$qaMenu = Get-CurrentQAMenu $lab
$qaFolder = Join-Path $lab ('cbr-generated-qa-menu-' + $qaMenu.Sha256.Substring(0, 16))
Assert-LabNoReparsePath $qaFolder
if (-not (Test-Path -LiteralPath $qaFolder)) {
    & python -B (Join-Path $PSScriptRoot 'qa_menu.py') build $lab $qaFolder
    if ($LASTEXITCODE -ne 0) { throw 'QA menu generation failed.' }
}
if ((Get-LabSha256 (Join-Path $qaFolder 'UI.MENU')) -cne $qaMenu.Sha256) {
    throw 'Generated QA menu differs from the current builder.'
}
$sources['override\UI.MENU'] = Join-Path $qaFolder 'UI.MENU'
$writes = @()
foreach ($entry in $sources.GetEnumerator()) {
    $target = Join-Path $lab $entry.Key
    Assert-LabNoReparsePath $entry.Value
    Assert-LabNoReparsePath $target
    $hash = Get-LabSha256 $entry.Value
    $remoteRelative = switch ($entry.Key) {
        'override\M_EEexRC.lua' { 'eeexremote/M_EEexRC.lua' }
        'override\EEexRC.menu' { 'eeexremote/EEexRC.menu' }
        default { $null }
    }
    if ($remoteRelative -and $hash -cne $remoteSource.Sha256[$remoteRelative]) { throw 'Remote console source changed during staging.' }
    if (Test-Path -LiteralPath $target) {
        $current = Get-LabSha256 $target
        if ($current -cne $hash) {
            if (-not $Refresh -or -not $old -or -not $old.Files.PSObject.Properties[$entry.Key] -or
                $old.Files.($entry.Key) -cne $current) { throw "Refusing to overwrite unowned/changed asset: $target" }
        }
    }
    $writes += [pscustomobject]@{Source=$entry.Value; Target=$target; Relative=$entry.Key; Hash=$hash}
}
$idPath = Join-Path $lab 'CBRTSLab.id'
Assert-LabNoReparsePath $idPath
$idText = "CBR TimeStop Lab 2730`n"
if ((Test-Path -LiteralPath $idPath) -and [IO.File]::ReadAllText($idPath) -cne $idText) { throw 'Lab ID collision.' }
$output = Join-Path $lab 'cbr-timestop-output'
Assert-LabNoReparsePath $output
$null = [IO.Directory]::CreateDirectory($output)
$utf8 = [Text.UTF8Encoding]::new($false)
$hashes = [ordered]@{}
$loaderBaseline = Join-Path $lab 'cbr-loader-baseline.ini'
Assert-LabNoReparsePath $loaderBaseline
if (Test-Path -LiteralPath $loaderBaseline) {
    if ((Get-LabSha256 $loaderBaseline) -cne $manifest.InstalledHashes.'InfinityLoader.ini') { throw 'Loader baseline snapshot mismatch.' }
}
else {
    $loaderIni = Join-Path $lab 'InfinityLoader.ini'
    if ((Get-LabSha256 $loaderIni) -cne $manifest.InstalledHashes.'InfinityLoader.ini') {
        throw 'Create the loader baseline from the validated pre-launch configuration.'
    }
    [IO.File]::Copy($loaderIni, $loaderBaseline, $false)
}
Assert-LabNoGameProcess
foreach ($write in $writes) {
    [IO.File]::Copy($write.Source, $write.Target, $true)
    if ((Get-LabSha256 $write.Target) -cne $write.Hash) { throw 'Staged asset hash mismatch.' }
    $hashes[$write.Relative] = $write.Hash
}
[IO.File]::WriteAllText($idPath, $idText, $utf8)
$hashes['CBRTSLab.id'] = Get-LabSha256 $idPath
$hashes['cbr-loader-baseline.ini'] = Get-LabSha256 $loaderBaseline
# A new isolated settings file, never inherited from a playthrough profile.
$settings = Join-Path $config.ProfileRoot 'Baldur.lua'
Assert-LabNoReparsePath $settings
if (-not (Test-Path -LiteralPath $settings)) {
    [IO.File]::WriteAllText($settings, @"
SetPrivateProfileString('Program Options','Debug Mode','1')
SetPrivateProfileString('Program Options','Full Screen','0')
SetPrivateProfileString('Program Options','Window Width','1280')
SetPrivateProfileString('Program Options','Window Height','720')
SetPrivateProfileString('Language','Text','en_US')
"@, $utf8)
}
$state = [ordered]@{Schema=1; InstanceId=$manifest.InstanceId; Mode='observation_and_inert_correction';
    RemoteSource=$remoteSource.Root; RemoteCommit=$remoteSource.Commit; RemoteGitBlobs=$remoteSource.GitBlobs;
    RemoteSha256=$remoteSource.Sha256; FixtureBuilderSha256=$fixtures.BuilderSha256;
    FixtureEncoderSha256=$fixtures.EncoderSha256; FixtureDigest=$fixtures.Digest;
    QAMenuBuilderSha256=$qaMenu.BuilderSha256; QAMenuStockSha256=$qaMenu.StockSha256; QAMenuSha256=$qaMenu.Sha256;
    Files=$hashes; StagedUtc=[DateTime]::UtcNow.ToString('o'); GameLaunched=$false}
[IO.File]::WriteAllText($marker, ($state | ConvertTo-Json -Depth 5), $utf8)
[pscustomobject]@{LabRoot=$lab; Profile=$config.ProfileRoot; Assets=$hashes.Count;
    AutoPatch=$false; GameLaunched=$false} | ConvertTo-Json -Compress
}
finally {
    if ($owned) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
