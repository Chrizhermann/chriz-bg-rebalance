#Requires -Version 7.0
<#
Creates only the fixed disposable lab. Explicit phases keep the copy, official EEex
installation and final verification independently reviewable. This script never
launches the game, imports a save, uninstalls a component or removes a file.

Copy accepts the extracted EEex/ directory's parent from the pinned v1.3.1 tag.
Copy may resume its own files when their hashes match. A differing existing file
or an interrupted install stops for review; there is no destructive reset path.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('Copy', 'Install', 'Validate')][string] $Phase,
    [string] $EEexArchiveRoot,
    [string] $WeiduPath
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Lab.Common.ps1')
$config = Get-LabConfiguration
$lab = Assert-LabRoot
$manifestPath = Join-Path $lab $config.MarkerName
$utf8 = [Text.UTF8Encoding]::new($false)
$expectedEEexTree = 'cd776455c2c9202dcffa526d7ccd81c496bbf8c99d9cd4e260e9ed4bc3b826bd'
$expectedWeidu = '0d17e26e3f3ef5b36796eb0ee8ae73cb851d8b62c9702c2e224da2945caafb75'

function Write-OwnedJson {
    param([string] $Path, $Value)
    if (-not (Test-LabPathWithin -Path $Path -Root $lab) -and
        -not (Test-LabPathWithin -Path $Path -Root $config.ProfileRoot)) {
        throw 'CBR_LAB REFUSED_WRITE_OUTSIDE_LAB'
    }
    Assert-LabNoReparsePath $Path
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 8), $utf8)
}

function Save-Manifest {
    Assert-LabManifestValues $script:manifest
    Write-OwnedJson -Path $manifestPath -Value $script:manifest
}

function Get-TreeInventory {
    param([string] $Root)
    $full = ConvertTo-LabFullPath $Root
    foreach ($file in @(Get-LabPhysicalFiles $full)) {
        [pscustomobject]@{
            RelativePath = $file.FullName.Substring($full.Length + 1).Replace('\', '/')
            Size = $file.Length
            Sha256 = Get-LabSha256 $file.FullName
        }
    }
}

function Get-InventoryDigest {
    param([object[]] $Inventory)
    $rows = @{}
    foreach ($item in $Inventory) { $rows[$item.RelativePath] = $item.Sha256 }
    [string[]] $keys = @($rows.Keys)
    [Array]::Sort($keys, [StringComparer]::Ordinal)
    $lines = foreach ($key in $keys) { "$key`t$($rows[$key])" }
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = $utf8.GetBytes(($lines -join "`n") + "`n")
        ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    }
    finally { $sha.Dispose() }
}

function Copy-OwnedFile {
    param([string] $Source, [string] $Destination, [string] $ExpectedHash)
    if (-not (Test-LabPathWithin -Path $Destination -Root $lab)) { throw 'CBR_LAB COPY_OUTSIDE_LAB' }
    Assert-LabNoReparsePath $Source
    Assert-LabNoReparsePath $Destination
    if (Test-Path -LiteralPath $Destination) {
        if (-not (Test-Path -LiteralPath $Destination -PathType Leaf) -or
            (Get-LabSha256 $Destination) -cne $ExpectedHash) {
            throw "CBR_LAB EXISTING_FILE_DIFFERS_REVIEW_REQUIRED: $Destination"
        }
        return
    }
    $null = [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Destination))
    Assert-LabNoReparsePath $Destination
    # File.Copy creates independent physical files; it never creates a link.
    [IO.File]::Copy($Source, $Destination, $false)
    if ((Get-LabSha256 $Destination) -cne $ExpectedHash) { throw "CBR_LAB COPY_HASH_MISMATCH: $Destination" }
}

function Assert-LabPristineSource {
    Assert-LabNoReparsePath $config.SourceRoot
    if ((Get-LabSha256 (Join-Path $config.SourceRoot 'Baldur.exe')) -cne $config.ExeSha256) {
        throw 'CBR_LAB SOURCE_EXE_FINGERPRINT_MISMATCH'
    }
    $allowed = @('data', 'lang', 'Manuals', 'movies', 'music', 'scripts', 'Baldur.exe',
        'chitin.key', 'engine.lua', 'oalinst.exe', 'steam_api64.dll', 'steam_appid.txt', 'weidu.conf')
    foreach ($entry in @(Get-ChildItem -LiteralPath $config.SourceRoot -Force)) {
        if ($entry.Name -notin $allowed) { throw "CBR_LAB SOURCE_NOT_PRISTINE: $($entry.Name)" }
    }
    foreach ($relative in @('data\PATCH26.BIF', 'data\PATCH27.BIF', 'chitin.key', 'lang\en_US\dialog.tlk')) {
        if (-not (Test-Path -LiteralPath (Join-Path $config.SourceRoot $relative) -PathType Leaf)) {
            throw "CBR_LAB SOURCE_RESOURCE_MISSING: $relative"
        }
    }
}

function Assert-StagedInputs {
    if ((Get-LabSha256 (Join-Path $lab 'Baldur.exe')) -cne $config.ExeSha256 -or
        (Get-LabSha256 (Join-Path $lab 'weidu.exe')) -cne $expectedWeidu) {
        throw 'CBR_LAB STAGED_EXECUTABLE_MISMATCH'
    }
    $inventory = @(Get-TreeInventory (Join-Path $lab 'EEex'))
    if ((Get-InventoryDigest $inventory) -cne $expectedEEexTree) { throw 'CBR_LAB EEEX_STAGE_MISMATCH' }
    Assert-LabProfile $script:manifest
}

function Assert-InstalledEEex {
    $logPath = Join-Path $lab 'WeiDU.log'
    Assert-LabNoReparsePath $logPath
    $components = @(Get-LabEEexComponents ([IO.File]::ReadAllText($logPath)))
    if (($components -join ',') -cne '0,1,8') { throw 'CBR_LAB EEEX_COMPONENTS_INCOMPLETE' }
    $matches = @{
        'EEex.dll' = 'EEex\loader\v2.7.3.0\EEex.dll'
        'LuaBindings.dll' = 'EEex\loader\v2.7.3.0\LuaBindings.dll'
        'InfinityLoader.exe' = 'EEex\loader\InfinityLoader.exe'
        'InfinityLoaderDLL.dll' = 'EEex\loader\InfinityLoaderDLL.dll'
        'lua51.dll' = 'EEex\loader\LuaJIT\lua51.dll'
        'override\M___EEex.lua' = 'EEex\copy\override\M___EEex.lua'
        'EEex_scripts\profiler\function_names.db' = 'EEex\loader\v2.7.3.0\bg2ee\function_names.db'
    }
    $hashes = [ordered]@{}
    foreach ($relative in $matches.Keys) {
        $hash = Get-LabSha256 (Join-Path $lab $relative)
        if ($hash -cne (Get-LabSha256 (Join-Path $lab $matches[$relative]))) {
            throw "CBR_LAB INSTALLED_EEEX_FILE_MISMATCH: $relative"
        }
        $hashes[$relative] = $hash
    }
    $loaderPath = Join-Path $lab 'InfinityLoader.ini'
    Assert-LabNoReparsePath $loaderPath
    $loader = [IO.File]::ReadAllText($loaderPath)
    foreach ($line in @('LuaLibrary=lua51.dll', 'LuaPatchMode=REPLACE_INTERNAL_WITH_EXTERNAL', 'LuaVersionExternal=5.1-LuaJIT')) {
        if ([regex]::Matches($loader, '(?m)^' + [regex]::Escape($line) + '\r?$').Count -ne 1) {
            throw 'CBR_LAB LUAJIT_CONFIGURATION_MISMATCH'
        }
    }
    # Equal to the raw hash before the first launch; later launches only add the loader's cache.
    $hashes['InfinityLoader.ini'] = Get-LabLoaderConfigurationSha256 $loaderPath
    $hashes['WeiDU.log'] = Get-LabSha256 $logPath
    $hashes
}

if ($Phase -ceq 'Copy') {
    if ([string]::IsNullOrWhiteSpace($EEexArchiveRoot) -or [string]::IsNullOrWhiteSpace($WeiduPath)) {
        throw 'CBR_LAB COPY_REQUIRES_EEEX_ARCHIVE_AND_WEIDU'
    }
    $archive = ConvertTo-LabFullPath $EEexArchiveRoot
    $weidu = ConvertTo-LabFullPath $WeiduPath
    foreach ($inputPath in @($archive, $weidu)) {
        Assert-LabNoReparsePath $inputPath
        if (Test-LabPathWithin -Path $inputPath -Root $lab) { throw 'CBR_LAB INPUT_INSIDE_DESTINATION' }
    }
    Assert-LabPristineSource
    $eeexInventory = @(Get-TreeInventory (Join-Path $archive 'EEex'))
    if ((Get-InventoryDigest $eeexInventory) -cne $expectedEEexTree) { throw 'CBR_LAB PINNED_EEEX_ARCHIVE_REQUIRED' }
    if ((Get-LabSha256 $weidu) -cne $expectedWeidu -or
        [Diagnostics.FileVersionInfo]::GetVersionInfo($weidu).FileVersion -cne '251.00') {
        throw 'CBR_LAB PINNED_WEIDU_25100_REQUIRED'
    }
    # Hash and reject linked source trees before creating the destination.
    $sourceInventory = @(Get-TreeInventory $config.SourceRoot)
    Assert-LabNoReparsePath $config.ProfileRoot
    if (Test-Path -LiteralPath $lab) {
        $script:manifest = Read-LabManifest
        if ($manifest.Phase -cnotin @('Copying', 'Copied')) { throw 'CBR_LAB COPY_AFTER_INSTALL_REFUSED' }
        if ($manifest.EEexTreeSha256 -cne $expectedEEexTree -or $manifest.WeiduSha256 -cne $expectedWeidu -or
            $manifest.SourceTreeSha256 -cne (Get-InventoryDigest $sourceInventory)) {
            throw 'CBR_LAB COPY_INPUTS_CHANGED'
        }
        if (Test-Path -LiteralPath $config.ProfileRoot) {
            $profileMarker = Join-Path $config.ProfileRoot $config.MarkerName
            Assert-LabNoReparsePath $profileMarker
            if (-not (Test-Path -LiteralPath $profileMarker -PathType Leaf) -or
                ([IO.File]::ReadAllText($profileMarker) | ConvertFrom-Json).InstanceId -cne $manifest.InstanceId) {
                throw 'CBR_LAB PROFILE_ALREADY_EXISTS_UNRELATED'
            }
        }
    }
    else {
        if (Test-Path -LiteralPath $config.ProfileRoot) { throw 'CBR_LAB PROFILE_ALREADY_EXISTS_UNRELATED' }
        $script:manifest = [pscustomobject][ordered]@{
            SchemaVersion = 1; LabId = 'cbr-timestop-2730'; InstanceId = [guid]::NewGuid().ToString()
            LabRoot = $lab; ProfileRoot = $config.ProfileRoot; EngineName = $config.EngineName
            SourceRoot = $config.SourceRoot; ExeSha256 = $config.ExeSha256
            EEexCommit = $config.EEexCommit; EEexVersion = $config.EEexVersion
            EEexTreeSha256 = $expectedEEexTree; WeiduSha256 = $expectedWeidu; WeiduVersion = 25100
            SourceTreeSha256 = Get-InventoryDigest $sourceInventory
            Phase = 'Copying'; CreatedUtc = [DateTime]::UtcNow.ToString('o'); InstalledHashes = $null
        }
        $null = [IO.Directory]::CreateDirectory($lab)
        Save-Manifest
    }
    if (-not (Test-Path -LiteralPath $config.ProfileRoot)) {
        $null = [IO.Directory]::CreateDirectory($config.ProfileRoot)
        Write-OwnedJson -Path (Join-Path $config.ProfileRoot $config.MarkerName) -Value $manifest
    }
    Write-OwnedJson -Path (Join-Path $lab 'cbr-source-inventory.json') -Value $sourceInventory
    foreach ($item in $sourceInventory) {
        if ($item.RelativePath -ceq 'engine.lua') { continue }
        Copy-OwnedFile -Source (Join-Path $config.SourceRoot $item.RelativePath) -Destination (Join-Path $lab $item.RelativePath) -ExpectedHash $item.Sha256
    }
    foreach ($item in $eeexInventory) {
        Copy-OwnedFile -Source (Join-Path (Join-Path $archive 'EEex') $item.RelativePath) -Destination (Join-Path (Join-Path $lab 'EEex') $item.RelativePath) -ExpectedHash $item.Sha256
    }
    Copy-OwnedFile -Source $weidu -Destination (Join-Path $lab 'weidu.exe') -ExpectedHash $expectedWeidu
    $engine = [IO.File]::ReadAllText((Join-Path $config.SourceRoot 'engine.lua'))
    $namePattern = '(?m)^engine_name\s*=\s*"[^"\r\n]+"\s*$'
    if ([regex]::Matches($engine, $namePattern).Count -ne 1) { throw 'CBR_LAB SOURCE_ENGINE_NAME_UNEXPECTED' }
    $engine = [regex]::Replace($engine, $namePattern, ('engine_name = "' + $config.EngineName + '"'))
    $enginePath = Join-Path $lab 'engine.lua'
    Assert-LabNoReparsePath $enginePath
    if (Test-Path -LiteralPath $enginePath) {
        if ([IO.File]::ReadAllText($enginePath) -cne $engine) { throw 'CBR_LAB EXISTING_ENGINE_CONFIG_DIFFERS' }
    }
    else { [IO.File]::WriteAllText($enginePath, $engine, $utf8) }
    Assert-StagedInputs
    $manifest.Phase = 'Copied'
    Save-Manifest
}
else {
    $script:manifest = Read-LabManifest
    Assert-LabProfile $manifest
    # Inspect every destination entry before allowing the installer to write there.
    $null = @(Get-LabPhysicalFiles $lab)
    $null = @(Get-LabPhysicalFiles $config.ProfileRoot)
    Assert-StagedInputs
    if ($Phase -ceq 'Install') {
        if ($manifest.Phase -ceq 'Installing') { throw 'CBR_LAB PREVIOUS_INSTALL_UNCERTAIN_REVIEW_REQUIRED' }
        if ($manifest.Phase -cin @('Installed', 'Validated')) {
            $null = Assert-InstalledEEex
        }
        elseif ($manifest.Phase -ceq 'Copied') {
            $logPath = Join-Path $lab 'WeiDU.log'
            if (Test-Path -LiteralPath $logPath) { throw 'CBR_LAB PREEXISTING_WEIDU_LOG_REVIEW_REQUIRED' }
            $arguments = @('EEex\EEex.tp2', '--game', $lab, '--force-install-list', '0', '1', '8',
                '--language', '0', '--use-lang', 'en_US', '--no-exit-pause', '--skip-at-view', '--noautoupdate',
                '--log', 'cbr-eeex-install.debug')
            $start = [Diagnostics.ProcessStartInfo]::new()
            $start.FileName = Join-Path $lab 'weidu.exe'
            $start.WorkingDirectory = $lab
            $start.UseShellExecute = $false
            $start.CreateNoWindow = $true
            $start.RedirectStandardInput = $true
            $start.RedirectStandardOutput = $true
            $start.RedirectStandardError = $true
            foreach ($argument in $arguments) { $start.ArgumentList.Add($argument) }
            $manifest.Phase = 'Installing'
            Save-Manifest
            # WeiDU writes only into this lab. A fail-closed snapshot right before it starts:
            # nothing of this lab may run or be starting, and the PC must not be reserved.
            # Other labs' games may run; no process is ever closed.
            try { Assert-LabNoGameProcess }
            catch { $manifest.Phase = 'Copied'; Save-Manifest; throw }
            $process = [Diagnostics.Process]::new()
            $process.StartInfo = $start
            try {
                if (-not $process.Start()) { throw 'CBR_LAB WEIDU_START_FAILED' }
                $process.StandardInput.Close() # unexpected questions receive EOF, never user input
                $stdout = $process.StandardOutput.ReadToEndAsync()
                $stderr = $process.StandardError.ReadToEndAsync()
                $process.WaitForExit()
                $output = $stdout.GetAwaiter().GetResult() + "`n" + $stderr.GetAwaiter().GetResult()
                $capture = Join-Path $lab 'cbr-eeex-install-output.txt'
                Assert-LabNoReparsePath $capture
                [IO.File]::WriteAllText($capture, $output, $utf8)
                Assert-LabWeiDUResult -ExitCode $process.ExitCode -Text $output
            }
            finally { $process.Dispose() }
            $manifest.InstalledHashes = Assert-InstalledEEex
            $manifest.Phase = 'Installed'
            Save-Manifest
        }
        else { throw 'CBR_LAB COPY_PHASE_INCOMPLETE' }
    }
    else {
        if ($manifest.Phase -cnotin @('Installed', 'Validated')) { throw 'CBR_LAB SUCCESSFUL_INSTALL_REQUIRED' }
        $manifest.InstalledHashes = Assert-InstalledEEex
        # This checks that all pristine inputs remain byte-identical after setup.
        $sourceInventory = @(Get-TreeInventory $config.SourceRoot)
        if ((Get-InventoryDigest $sourceInventory) -cne $manifest.SourceTreeSha256) {
            throw 'CBR_LAB SOURCE_CHANGED_SINCE_COPY'
        }
        $manifest.Phase = 'Validated'
        Save-Manifest
    }
}

[pscustomobject]@{ Phase = $manifest.Phase; LabRoot = $lab; ProfileRoot = $config.ProfileRoot;
    GameLaunched = $false; SavesImported = $false } | ConvertTo-Json -Compress
