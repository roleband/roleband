param(
    [Parameter(Mandatory=$true)][string]$Bundle,
    [Parameter(Mandatory=$true)][string]$Destination,
    [version]$PackageVersion
)
$ErrorActionPreference = 'Stop'
$bundlePath = (Resolve-Path -LiteralPath $Bundle).Path
$packagePath = [IO.Path]::GetFullPath($Destination)
if (Test-Path -LiteralPath $packagePath) { throw 'Choose a new package destination.' }
$trialPath = Join-Path $bundlePath 'Resources/trial.json'
$buildPath = Join-Path $bundlePath 'Resources/build.json'
# The bundle's marker decides the package: a trial keeps the trial identity, a release takes RoleBand's own.
if ((Test-Path -LiteralPath $buildPath) -and !(Test-Path -LiteralPath $trialPath)) {
    $marker = Get-Content -Raw -LiteralPath $buildPath | ConvertFrom-Json
    if ($marker.format -ne 1 -or $marker.channel -ne 'release') { throw 'The release marker is not one this script packages.' }
    $release = Get-Content -Raw -LiteralPath (Join-Path $bundlePath 'Resources/release-identity.json') | ConvertFrom-Json
    if ([string]::IsNullOrWhiteSpace($release.package_name) -or [string]::IsNullOrWhiteSpace($release.publisher)) {
        throw 'A release bundle needs the update identity that names its package and publisher.'
    }
} elseif ((Test-Path -LiteralPath $trialPath) -and !(Test-Path -LiteralPath $buildPath)) {
    $marker = Get-Content -Raw -LiteralPath $trialPath | ConvertFrom-Json
    if ($marker.trial_only -ne $true -or $marker.trial_id -notmatch '^[0-9a-f]{32}$') { throw 'Only synthetic development trials can be packaged as trials.' }
    $release = $null
} else { throw 'The bundle must name one channel: a trial or a release.' }
if ($null -eq $marker.dirty_paths -or @($marker.dirty_paths).Count -ne 0) { throw 'The bundle was not assembled from a clean commit. Assemble it again.' }
# A package is traceable to its commit only if the bundle is byte for byte what assembly recorded.
$recorded = Get-Content -Raw -LiteralPath (Join-Path $bundlePath 'bundle-hashes.json') | ConvertFrom-Json
$expected = @{}
$recorded.PSObject.Properties | ForEach-Object { $expected[$_.Name] = $_.Value }
$packaging = @('bundle-hashes.json', 'AppxManifest.xml', 'resources.pri')
Get-ChildItem -LiteralPath $bundlePath -File -Recurse | ForEach-Object {
    $relative = $_.FullName.Substring($bundlePath.Length+1)
    if ($packaging -contains $relative -or $relative.StartsWith('Assets\')) { return }
    if (!$expected.ContainsKey($relative)) { throw "The bundle changed after assembly: $relative was added. Assemble it again." }
    if ((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected[$relative]) {
        throw "The bundle changed after assembly: $relative was edited. Assemble it again."
    }
    $expected.Remove($relative)
}
$missing = @($expected.Keys | Where-Object { $packaging -notcontains $_ -and !$_.StartsWith('Assets\') })
if ($missing.Count) { throw "The bundle changed after assembly: $($missing[0]) was removed. Assemble it again." }
$makeappx = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10/bin/10.0.26100.0/x64/makeappx.exe'
$makepri = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10/bin/10.0.26100.0/x64/makepri.exe'
if (!(Test-Path -LiteralPath $makeappx) -or !(Test-Path -LiteralPath $makepri)) { throw 'Windows SDK 10.0.26100.0 packaging tools are required.' }
& (Join-Path $bundlePath 'Resources/runtime/python.exe') -I -B (Join-Path $PSScriptRoot 'Tools/pe_certificates.py') $bundlePath
if ($LASTEXITCODE -ne 0) { throw 'A PE certificate table is invalid. Package signing would fail.' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'AppxManifest.xml') -Destination (Join-Path $bundlePath 'AppxManifest.xml')
if ($release) {
    # The publisher is fixed for good: Windows updates a package in place only from the same publisher.
    $manifestPath = Join-Path $bundlePath 'AppxManifest.xml'
    [xml]$packageManifest = Get-Content -LiteralPath $manifestPath -Raw
    $namespaces = New-Object Xml.XmlNamespaceManager $packageManifest.NameTable
    $namespaces.AddNamespace('m', 'http://schemas.microsoft.com/appx/manifest/foundation/windows10')
    $namespaces.AddNamespace('uap', 'http://schemas.microsoft.com/appx/manifest/uap/windows10')
    $namespaces.AddNamespace('virtualization', 'http://schemas.microsoft.com/appx/manifest/virtualization/windows10')
    $packageManifest.Package.Identity.Name = [string]$release.package_name
    $packageManifest.Package.Identity.Publisher = [string]$release.publisher
    $packageManifest.Package.Identity.Version = "$($marker.version).0"
    $packageManifest.SelectSingleNode('/m:Package/m:Properties/m:DisplayName', $namespaces).InnerText = 'RoleBand'
    $packageManifest.SelectSingleNode('//virtualization:ExcludedDirectory', $namespaces).InnerText = '$(KnownFolder:LocalAppData)\RoleBand'
    $visual = $packageManifest.SelectSingleNode('//uap:VisualElements', $namespaces)
    $visual.DisplayName = 'RoleBand'
    $visual.Description = 'RoleBand'
    $packageManifest.Save($manifestPath)
}
if ($PackageVersion) {
    if ($PackageVersion.Revision -lt 0 -or @($PackageVersion.Major,$PackageVersion.Minor,$PackageVersion.Build,$PackageVersion.Revision | Where-Object {$_ -gt 65535}).Count) {
        throw 'MSIX versions require four components between 0 and 65535.'
    }
    $manifestPath = Join-Path $bundlePath 'AppxManifest.xml'
    [xml]$packageManifest = Get-Content -LiteralPath $manifestPath -Raw
    $packageManifest.Package.Identity.Version = $PackageVersion.ToString(4)
    $packageManifest.Save($manifestPath)
}
$assetDestination = Join-Path $bundlePath 'Assets'
# The provenance check leaves Assets to this step, so it starts empty: nothing placed there after assembly is packaged.
if (Test-Path -LiteralPath $assetDestination) { Remove-Item -LiteralPath $assetDestination -Recurse -Force }
New-Item -ItemType Directory -Force $assetDestination | Out-Null
Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'Assets') -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $assetDestination $_.Name)
}
# Windows finds the qualified logo files (targetsize, scale, altform) only through resources.pri
# at the package root. MRT Core loads that file before RoleBand.App.pri, so it must also hold
# everything RoleBand.App.pri does: the app's XAML (.xbf) and the Windows App SDK's resources.
# The index covers Assets and that file only; Resources holds a whole Python runtime.
$appPri = Join-Path $bundlePath 'RoleBand.App.pri'
if (!(Test-Path -LiteralPath $appPri)) { throw 'The bundle has no RoleBand.App.pri to merge into resources.pri.' }
$priWork = Join-Path ([IO.Path]::GetTempPath()) ('roleband-pri-' + [guid]::NewGuid().ToString('N'))
$priRoot = Join-Path $priWork 'root'
New-Item -ItemType Directory -Force $priRoot | Out-Null
try {
    Copy-Item -LiteralPath $assetDestination -Destination (Join-Path $priRoot 'Assets') -Recurse
    Copy-Item -LiteralPath $appPri -Destination $priRoot
    $priConfig = Join-Path $priWork 'priconfig.xml'
    Set-Content -LiteralPath $priConfig -Encoding UTF8 -Value @'
<?xml version="1.0" encoding="utf-8"?>
<resources targetOsVersion="10.0.0" majorVersion="1">
  <index root="\" startIndexAt="\">
    <default>
      <qualifier name="Language" value="en-US" />
      <qualifier name="Contrast" value="standard" />
      <qualifier name="Scale" value="100" />
      <qualifier name="HomeRegion" value="001" />
      <qualifier name="TargetSize" value="256" />
      <qualifier name="LayoutDirection" value="LTR" />
      <qualifier name="Theme" value="dark" />
      <qualifier name="AlternateForm" value="" />
      <qualifier name="DXFeatureLevel" value="DX9" />
      <qualifier name="Configuration" value="" />
      <qualifier name="DeviceFamily" value="Universal" />
      <qualifier name="Custom" value="" />
    </default>
    <indexer-config type="folder" foldernameAsQualifier="true" filenameAsQualifier="true" qualifierDelimiter="." />
    <indexer-config type="PRI" />
  </index>
</resources>
'@
    $priLog = & $makepri new /pr $priRoot /cf $priConfig /mn (Join-Path $bundlePath 'AppxManifest.xml') /of (Join-Path $bundlePath 'resources.pri') /o
    if ($LASTEXITCODE -ne 0) { $priLog | Write-Host; throw 'Building resources.pri failed.' }
} finally {
    Remove-Item -LiteralPath $priWork -Recurse -Force -ErrorAction SilentlyContinue
}
$hashes = [ordered]@{}
Get-ChildItem -LiteralPath $bundlePath -File -Recurse | Where-Object {$_.FullName -ne (Join-Path $bundlePath 'bundle-hashes.json')} | ForEach-Object {
    $relative = $_.FullName.Substring($bundlePath.Length+1)
    $hashes[$relative] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
}
$hashes | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $bundlePath 'bundle-hashes.json') -Encoding UTF8
& $makeappx pack /d $bundlePath /p $packagePath
if ($LASTEXITCODE -ne 0) { throw 'MSIX validation or packing failed.' }
Get-FileHash -LiteralPath $packagePath -Algorithm SHA256
