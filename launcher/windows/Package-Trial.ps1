param(
    [Parameter(Mandatory=$true)][string]$Bundle,
    [Parameter(Mandatory=$true)][string]$Destination,
    [version]$PackageVersion
)
$ErrorActionPreference = 'Stop'
$bundlePath = (Resolve-Path -LiteralPath $Bundle).Path
$packagePath = [IO.Path]::GetFullPath($Destination)
if (Test-Path -LiteralPath $packagePath) { throw 'Choose a new package destination.' }
$trial = Get-Content -Raw -LiteralPath (Join-Path $bundlePath 'Resources/trial.json') | ConvertFrom-Json
if ($trial.trial_only -ne $true -or $trial.trial_id -notmatch '^[0-9a-f]{32}$') { throw 'Only synthetic development trials can be packaged here.' }
if ($null -eq $trial.dirty_paths -or @($trial.dirty_paths).Count -ne 0) { throw 'The bundle was not assembled from a clean commit. Assemble it again.' }
# A package is traceable to its commit only if the bundle is byte for byte what assembly recorded.
$recorded = Get-Content -Raw -LiteralPath (Join-Path $bundlePath 'trial-hashes.json') | ConvertFrom-Json
$expected = @{}
$recorded.PSObject.Properties | ForEach-Object { $expected[$_.Name] = $_.Value }
$packaging = @('trial-hashes.json', 'AppxManifest.xml')
Get-ChildItem -LiteralPath $bundlePath -File -Recurse | ForEach-Object {
    $relative = $_.FullName.Substring($bundlePath.Length+1)
    if ($packaging -contains $relative -or $relative.StartsWith('Assets\')) { return }
    if (!$expected.ContainsKey($relative)) { throw "The bundle changed after assembly: $relative was added. Assemble it again." }
    if ((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected[$relative]) {
        throw "The bundle changed after assembly: $relative was edited. Assemble it again."
    }
    $expected.Remove($relative)
}
$missing = @($expected.Keys | Where-Object { $_ -ne 'AppxManifest.xml' -and !$_.StartsWith('Assets\') })
if ($missing.Count) { throw "The bundle changed after assembly: $($missing[0]) was removed. Assemble it again." }
$makeappx = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10/bin/10.0.26100.0/x64/makeappx.exe'
if (!(Test-Path -LiteralPath $makeappx)) { throw 'Windows SDK 10.0.26100.0 packaging tools are required.' }
& (Join-Path $bundlePath 'Resources/runtime/python.exe') -I -B (Join-Path $PSScriptRoot 'Tools/pe_certificates.py') $bundlePath
if ($LASTEXITCODE -ne 0) { throw 'A PE certificate table is invalid. Package signing would fail.' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'AppxManifest.xml') -Destination (Join-Path $bundlePath 'AppxManifest.xml')
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
New-Item -ItemType Directory -Force $assetDestination | Out-Null
Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'Assets') -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $assetDestination $_.Name)
}
$hashes = [ordered]@{}
Get-ChildItem -LiteralPath $bundlePath -File -Recurse | Where-Object {$_.FullName -ne (Join-Path $bundlePath 'trial-hashes.json')} | ForEach-Object {
    $relative = $_.FullName.Substring($bundlePath.Length+1)
    $hashes[$relative] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
}
$hashes | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $bundlePath 'trial-hashes.json') -Encoding UTF8
& $makeappx pack /d $bundlePath /p $packagePath
if ($LASTEXITCODE -ne 0) { throw 'MSIX validation or packing failed.' }
Get-FileHash -LiteralPath $packagePath -Algorithm SHA256
