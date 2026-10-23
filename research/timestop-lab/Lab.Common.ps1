# Shared guards for the disposable labs. Dot-sourcing performs no I/O or setup.
Set-StrictMode -Version Latest

# The scripts build one of two labs, chosen by CBR_LAB_VARIANT: the Time Stop observation lab
# (unset or 'timestop') or the lab for the Chriz BG Time Clocks mod ('timeclocks'). Each has its
# own folder, engine name, profile, lab ID and ownership markers, so neither ever touches the
# other's files. Any other value is refused.
function Get-LabVariant {
    $name = if ([string]::IsNullOrEmpty($env:CBR_LAB_VARIANT)) { 'timestop' } else { $env:CBR_LAB_VARIANT }
    if ($name -ceq 'timestop') {
        return [pscustomobject]@{Name='timestop'; Folder='CBR-TimeStop-2.7.3.0'; EngineName='CBR TimeStop Lab 2730'
            LabId='cbr-timestop-2730'; MarkerName='.cbr-timestop-lab.json'}
    }
    if ($name -ceq 'timeclocks') {
        return [pscustomobject]@{Name='timeclocks'; Folder='CBR-TimeClocks-2.7.3.0'; EngineName='CBR TimeClocks Lab 2730'
            LabId='cbr-timeclocks-2730'; MarkerName='.cbr-timeclocks-lab.json'}
    }
    throw 'CBR_LAB UNKNOWN_VARIANT'
}

function Get-LabConfiguration {
    $documents = [Environment]::GetFolderPath([Environment+SpecialFolder]::MyDocuments)
    if ([string]::IsNullOrWhiteSpace($documents)) { throw 'CBR_LAB DOCUMENTS_PATH_UNAVAILABLE' }
    $variant = Get-LabVariant
    [pscustomobject]@{
        Variant = $variant.Name
        LabId = $variant.LabId
        LabRoot = (Join-Path $env:USERPROFILE ('Games\' + $variant.Folder))
        SourceRoot = "C:\Program Files (x86)\Steam\steamapps\common\Baldur's Gate II Enhanced Edition"
        EngineName = $variant.EngineName
        ProfileRoot = Join-Path $documents $variant.EngineName
        ExeSha256 = 'b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57'
        EEexCommit = 'a6d21abe44e20509f5d0259ccc6c7e7f9d12b285'
        EEexVersion = '1.3.1'
        MarkerName = $variant.MarkerName
        # The lab identity file the observer and the console client check.
        IdText = $variant.EngineName + "`n"
    }
}

function ConvertTo-LabFullPath {
    param([Parameter(Mandatory)][string] $Path)
    if (-not [IO.Path]::IsPathRooted($Path) -or $Path -match '^[^:]+:[^\\/]') {
        throw 'CBR_LAB ABSOLUTE_PATH_REQUIRED'
    }
    [IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
}

function Test-LabPathWithin {
    param([Parameter(Mandatory)][string] $Path, [Parameter(Mandatory)][string] $Root)
    $candidate = ConvertTo-LabFullPath $Path
    $parent = ConvertTo-LabFullPath $Root
    $candidate.Equals($parent, [StringComparison]::OrdinalIgnoreCase) -or
        $candidate.StartsWith($parent + '\', [StringComparison]::OrdinalIgnoreCase)
}

function Test-LabCloudReparseTag {
    param([Parameter(Mandatory)][uint32] $Tag)
    # Microsoft MS-FSCC: CLOUD / CLOUD_1..F are 0x9000001A + (n << 12).
    # https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-fscc/c8e77b37-3909-4fe6-a4ea-2b9d423b1ee4
    # Name-surrogate tags redirect to another entity and are never permitted.
    ($Tag -band 0x20000000) -eq 0 -and ($Tag -band 0xFFFF0FFFL) -eq 0x9000001AL
}

function Test-LabCloudProfileScope {
    param([Parameter(Mandatory)][string] $Path, [Parameter(Mandatory)][string] $RequestedPath)
    $config = Get-LabConfiguration
    $documents = [IO.Path]::GetDirectoryName($config.ProfileRoot)
    # The exception belongs only to the OS-known Documents ancestry and this
    # exact profile subtree. A shared ancestor must not relax executable guards.
    $requestAllowed = (Test-LabPathWithin -Path $documents -Root $RequestedPath) -or
        (Test-LabPathWithin -Path $RequestedPath -Root $config.ProfileRoot)
    $entryAllowed = (Test-LabPathWithin -Path $documents -Root $Path) -or
        (Test-LabPathWithin -Path $Path -Root $config.ProfileRoot)
    $requestAllowed -and $entryAllowed
}

function Get-LabReparseTag {
    param([Parameter(Mandatory)][string] $Path)
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::System)) 'fsutil.exe'
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    foreach ($argument in @('reparsepoint', 'query', (ConvertTo-LabFullPath $Path))) {
        $start.ArgumentList.Add($argument)
    }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    try {
        if (-not $process.Start()) { throw 'CBR_LAB REPARSE_TAG_QUERY_FAILED' }
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        $output = $stdout.GetAwaiter().GetResult()
        $null = $stderr.GetAwaiter().GetResult()
        # Accept one unambiguous DWORD field, independent of the localized label.
        $tags = [regex]::Matches($output, '(?m)^[^:\r\n]+:\s*0x([0-9a-fA-F]{8})\s*\r?$')
        if ($process.ExitCode -ne 0 -or $tags.Count -ne 1) { throw 'CBR_LAB REPARSE_TAG_QUERY_FAILED' }
        [Convert]::ToUInt32($tags[0].Groups[1].Value, 16)
    }
    finally { $process.Dispose() }
}

function Assert-LabNoReparsePath {
    param([Parameter(Mandatory)][string] $Path)
    $full = ConvertTo-LabFullPath $Path
    $cursor = [IO.Path]::GetPathRoot($full)
    foreach ($segment in ($full.Substring($cursor.Length) -split '[\\/]')) {
        if ($segment.Length -eq 0) { continue }
        $cursor = Join-Path $cursor $segment
        # Get-Item also detects dangling junctions; Test-Path alone can miss them.
        $item = Get-Item -LiteralPath $cursor -Force -ErrorAction SilentlyContinue
        if ($null -ne $item) {
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                if (-not (Test-LabCloudProfileScope -Path $cursor -RequestedPath $full) -or
                    -not (Test-LabCloudReparseTag (Get-LabReparseTag $cursor))) {
                    throw "CBR_LAB REPARSE_PATH_REJECTED: $cursor"
                }
            }
            if ($null -ne $item.PSObject.Properties['LinkType'] -and $item.LinkType -eq 'HardLink') {
                throw "CBR_LAB HARDLINK_REJECTED: $cursor"
            }
        }
    }
}

function Assert-LabRoot {
    param([string] $Path = (Get-LabConfiguration).LabRoot)
    $full = ConvertTo-LabFullPath $Path
    if (-not $full.Equals((Get-LabConfiguration).LabRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'CBR_LAB EXACT_DISPOSABLE_ROOT_REQUIRED'
    }
    Assert-LabNoReparsePath $full
    $full
}

function Get-LabPhysicalFiles {
    param([Parameter(Mandatory)][string] $Root)
    $full = ConvertTo-LabFullPath $Root
    Assert-LabNoReparsePath $full
    if (-not (Test-Path -LiteralPath $full -PathType Container)) { throw "CBR_LAB DIRECTORY_MISSING: $full" }
    $pending = [Collections.Generic.Stack[string]]::new()
    $pending.Push($full)
    while ($pending.Count -gt 0) {
        foreach ($item in @(Get-ChildItem -LiteralPath $pending.Pop() -Force -ErrorAction Stop)) {
            # The already-checked parent is traversed one level at a time, so a
            # junction is rejected before enumeration can follow it.
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                if (-not (Test-LabCloudProfileScope -Path $item.FullName -RequestedPath $full)) {
                    throw "CBR_LAB LINKED_TREE_ENTRY_REJECTED: $($item.FullName)"
                }
                Assert-LabNoReparsePath $item.FullName
            }
            if ($null -ne $item.PSObject.Properties['LinkType'] -and $item.LinkType -eq 'HardLink') {
                throw "CBR_LAB LINKED_TREE_ENTRY_REJECTED: $($item.FullName)"
            }
            if ($item.PSIsContainer) { $pending.Push($item.FullName) }
            else { $item }
        }
    }
}

function Get-LabSha256 {
    param([Parameter(Mandatory)][string] $Path)
    Assert-LabNoReparsePath $Path
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
}

function Get-LabTreeInventory {
    param([Parameter(Mandatory)][string] $Root)
    $full = ConvertTo-LabFullPath $Root
    foreach ($file in @(Get-LabPhysicalFiles $full)) {
        [pscustomobject]@{
            RelativePath = $file.FullName.Substring($full.Length + 1).Replace('\', '/')
            Size = $file.Length
            Sha256 = Get-LabSha256 $file.FullName
        }
    }
}

function Get-LabInventoryDigest {
    param([object[]] $Inventory)
    $rows = @{}
    foreach ($item in $Inventory) { $rows[$item.RelativePath] = $item.Sha256 }
    [string[]] $keys = @($rows.Keys)
    [Array]::Sort($keys, [StringComparer]::Ordinal)
    $lines = foreach ($key in $keys) { "$key`t$($rows[$key])" }
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($lines -join "`n") + "`n")
        ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    }
    finally { $sha.Dispose() }
}

function ConvertTo-LabLoaderConfiguration {
    # InfinityLoader writes its own cache into the [Auto-Generated] section on launch: the
    # executable's file time (CachedExeTime=) and resolved pattern addresses (CachedAddress=).
    # Without exactly those lines the file must equal the validated pre-launch configuration.
    # Text is Latin-1 decoded, so the result maps back to the original bytes one to one.
    param([Parameter(Mandatory)][AllowEmptyString()][string] $Text)
    $markers = [regex]::Matches($Text, '(?m)^\[Auto-Generated\]\r?$')
    if ($markers.Count -gt 1) { throw 'CBR_LAB LOADER_CONFIGURATION_AMBIGUOUS' }
    if ($markers.Count -eq 0) { return $Text }
    $start = $markers[0].Index
    $Text.Substring(0, $start) +
        [regex]::Replace($Text.Substring($start), '(?m)^Cached(?:ExeTime|Address)=[0-9]+(?:\r?\n|\z)', '')
}

function Get-LabLoaderConfigurationSha256 {
    param([Parameter(Mandatory)][string] $Path)
    Assert-LabNoReparsePath $Path
    $latin1 = [Text.Encoding]::Latin1
    $text = ConvertTo-LabLoaderConfiguration ($latin1.GetString([IO.File]::ReadAllBytes($Path)))
    $sha = [Security.Cryptography.SHA256]::Create()
    try { ([BitConverter]::ToString($sha.ComputeHash($latin1.GetBytes($text)))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
}

function Assert-LabNoGameProcess {
    param([object[]] $Processes)
    if (-not $PSBoundParameters.ContainsKey('Processes')) {
        $Processes = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    }
    $running = @($Processes | Where-Object { $_.Name -in @('Baldur.exe', 'InfinityLoader.exe') })
    if ($running.Count -gt 0) {
        $names = ($running | ForEach-Object { $_.Name }) -join ', '
        throw "CBR_LAB GAME_PROCESS_OPEN: $names. Leave other agents' processes alone and retry after their session ends."
    }
}

function Assert-LabManifestValues {
    param([Parameter(Mandatory)] $Manifest)
    $config = Get-LabConfiguration
    $required = @('SchemaVersion', 'LabId', 'InstanceId', 'LabRoot', 'ProfileRoot', 'EngineName', 'SourceRoot',
        'ExeSha256', 'EEexCommit', 'Phase')
    foreach ($property in $required) {
        if ($null -eq $Manifest.PSObject.Properties[$property]) { throw 'CBR_LAB INVALID_OWNERSHIP_MARKER' }
    }
    $instance = [guid]::Empty
    if ($Manifest.SchemaVersion -ne 1 -or $Manifest.LabId -cne $config.LabId -or
        -not [guid]::TryParse([string] $Manifest.InstanceId, [ref] $instance) -or
        $Manifest.LabRoot -ine $config.LabRoot -or $Manifest.ProfileRoot -ine $config.ProfileRoot -or
        $Manifest.EngineName -cne $config.EngineName -or $Manifest.SourceRoot -ine $config.SourceRoot -or
        $Manifest.ExeSha256 -cne $config.ExeSha256 -or $Manifest.EEexCommit -cne $config.EEexCommit -or
        $Manifest.Phase -cnotin @('Copying', 'Copied', 'Installing', 'Installed', 'Validated')) {
        throw 'CBR_LAB INVALID_OWNERSHIP_MARKER'
    }
}

function Read-LabManifest {
    $config = Get-LabConfiguration
    $null = Assert-LabRoot
    $path = Join-Path $config.LabRoot $config.MarkerName
    Assert-LabNoReparsePath $path
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'CBR_LAB OWNERSHIP_MARKER_REQUIRED' }
    $manifest = [IO.File]::ReadAllText($path) | ConvertFrom-Json
    Assert-LabManifestValues $manifest
    $manifest
}

function Assert-LabProfile {
    param([Parameter(Mandatory)] $Manifest)
    Assert-LabManifestValues $Manifest
    $config = Get-LabConfiguration
    Assert-LabNoReparsePath $config.ProfileRoot
    $path = Join-Path $config.ProfileRoot $config.MarkerName
    Assert-LabNoReparsePath $path
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'CBR_LAB PROFILE_OWNERSHIP_REQUIRED' }
    $profile = [IO.File]::ReadAllText($path) | ConvertFrom-Json
    foreach ($name in @('LabId', 'InstanceId', 'LabRoot', 'ProfileRoot', 'EngineName')) {
        if ($null -eq $profile.PSObject.Properties[$name] -or $profile.$name -cne $Manifest.$name) {
            throw 'CBR_LAB PROFILE_OWNERSHIP_MISMATCH'
        }
    }
    $engine = Join-Path $config.LabRoot 'engine.lua'
    Assert-LabNoReparsePath $engine
    $text = [IO.File]::ReadAllText($engine)
    $names = [regex]::Matches($text, '(?m)^\s*engine_name\s*=\s*"([^"\r\n]+)"\s*(?:--[^\r\n]*)?$')
    if ($names.Count -ne 1 -or $names[0].Groups[1].Value -cne $config.EngineName) {
        throw 'CBR_LAB UNIQUE_ENGINE_PROFILE_REQUIRED'
    }
}

function Assert-LabWeiDUResult {
    param([Parameter(Mandatory)][int] $ExitCode, [Parameter(Mandatory)][AllowEmptyString()][string] $Text)
    if ($ExitCode -ne 0 -or $Text -match '(?im)^\s*(?:ERROR\b|FATAL\b|SKIPPING\b|NOT INSTALLED\b)' -or
        $Text -match '(?i)FAILURE:|Sys_error\(') {
        throw 'CBR_LAB WEIDU_INSTALL_FAILED_REVIEW_LOG'
    }
}

function Get-LabEEexComponents {
    param([Parameter(Mandatory)][AllowEmptyString()][string] $LogText)
    $components = @()
    foreach ($line in ($LogText -split '\r?\n')) {
        if ($line -match '^\s*(?://.*)?$') { continue }
        if ($line -notmatch '^\s*~(?:EEEX[/\\])?EEEX\.TP2~\s+#0\s+#(0|1|8)\s+//.*\bv1\.3\.1\s*$') {
            throw 'CBR_LAB UNEXPECTED_WEIDU_COMPONENT_OR_VERSION'
        }
        $components += [int] $Matches[1]
    }
    if (($components -join ',') -cnotin @('', '0', '0,1', '0,1,8')) {
        throw 'CBR_LAB INVALID_COMPONENT_ORDER_OR_DUPLICATE'
    }
    $components
}

# The Chriz BG Time Clocks components (Time Clocks lab only) and the CBTCOPT.2DA switches each
# sets. Options need their base component; 220 turns off the SLOW switch 200 turns on.
# A plain hashtable: an ordered one would read an integer key as a position.
$script:LabTimeClocksComponents = @{
    100 = @{Requires = $null; Switches = @{TIME_STOP = 1}}
    110 = @{Requires = 100; Switches = @{STOP_NEW_EFFECTS = 1}}
    120 = @{Requires = 100; Switches = @{STOP_ACTORS = 1}}
    200 = @{Requires = $null; Switches = @{HASTE = 1; SLOW = 1}}
    210 = @{Requires = 200; Switches = @{HASTE_SCOPE = 1}}
    220 = @{Requires = 200; Switches = @{SLOW = 0}}
    230 = @{Requires = $null; Switches = @{HASTE_EXPIRY = 1}}
}
$script:LabTimeClocksSwitchNames = @('TIME_STOP', 'STOP_NEW_EFFECTS', 'STOP_ACTORS', 'HASTE', 'HASTE_SCOPE', 'SLOW',
    'HASTE_EXPIRY')

function Assert-LabTimeClocksComponents {
    # Known components, ascending (the install order), each once, each option after its base.
    param([AllowEmptyCollection()][int[]] $Components)
    $seen = @{}
    $previous = -1
    foreach ($component in $Components) {
        if (-not $script:LabTimeClocksComponents.Contains($component)) { throw "CBR_LAB UNKNOWN_TIMECLOCKS_COMPONENT: $component" }
        if ($component -le $previous) { throw 'CBR_LAB TIMECLOCKS_COMPONENTS_NOT_ASCENDING' }
        $base = $script:LabTimeClocksComponents[$component].Requires
        if ($null -ne $base -and -not $seen.ContainsKey($base)) { throw "CBR_LAB TIMECLOCKS_OPTION_WITHOUT_BASE: $component" }
        $seen[$component] = $true
        $previous = $component
    }
}

function Get-LabTimeClocksSwitches {
    # The switch values CBTCOPT.2DA must hold after installing these components in order.
    param([AllowEmptyCollection()][int[]] $Components)
    Assert-LabTimeClocksComponents $Components
    $switches = [ordered]@{}
    foreach ($name in $script:LabTimeClocksSwitchNames) { $switches[$name] = 0 }
    foreach ($component in $Components) {
        foreach ($entry in $script:LabTimeClocksComponents[$component].Switches.GetEnumerator()) {
            $switches[$entry.Key] = $entry.Value
        }
    }
    $switches
}

function Read-LabTimeClocksTable {
    # The rows of a CBTCOPT.2DA (2DA V1.0, column VALUE): name -> integer. Anything else fails.
    param([Parameter(Mandatory)][AllowEmptyString()][string] $Text)
    $lines = @($Text -split '\r?\n' | Where-Object { $_.Trim().Length -gt 0 })
    if ($lines.Count -lt 3 -or $lines[0].Trim() -cne '2DA V1.0' -or $lines[2].Trim() -cne 'VALUE') {
        throw 'CBR_LAB TIMECLOCKS_TABLE_MALFORMED'
    }
    $rows = [ordered]@{}
    foreach ($line in $lines[3..($lines.Count - 1)]) {
        if ($line -notmatch '^\s*([A-Z_][A-Z0-9_]*)\s+(-?[0-9]+)\s*$' -or $rows.Contains($Matches[1])) {
            throw 'CBR_LAB TIMECLOCKS_TABLE_MALFORMED'
        }
        $rows[$Matches[1]] = [int] $Matches[2]
    }
    $rows
}

function Get-LabWeiDUStack {
    # The lab's WeiDU.log in install order: EEex's components (Get-LabEEexComponents), then the
    # Chriz BG Time Clocks components (Time Clocks lab), nothing else and nothing in between.
    param([Parameter(Mandatory)][AllowEmptyString()][string] $LogText)
    $eeex = [Collections.Generic.List[string]]::new()
    $clocks = [Collections.Generic.List[int]]::new()
    foreach ($line in ($LogText -split '\r?\n')) {
        if ($line -match '^\s*(?://.*)?$') { continue }
        if ($line -match '^\s*~(?:[^~]*[/\\])?SETUP-CHRIZ-BG-TIME-CLOCKS\.TP2~\s+#0\s+#([0-9]+)\s+//') {
            $clocks.Add([int] $Matches[1])
            continue
        }
        if ($clocks.Count -gt 0) { throw 'CBR_LAB UNEXPECTED_WEIDU_COMPONENT_OR_VERSION' }
        $eeex.Add($line)
    }
    $components = @($clocks)
    if ($components.Count -gt 0 -and (Get-LabConfiguration).Variant -cne 'timeclocks') {
        throw 'CBR_LAB UNEXPECTED_WEIDU_COMPONENT_OR_VERSION'
    }
    Assert-LabTimeClocksComponents $components
    [pscustomobject]@{EEex = @(Get-LabEEexComponents ($eeex -join "`n")); TimeClocks = $components}
}
