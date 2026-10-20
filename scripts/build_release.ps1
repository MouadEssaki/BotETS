# Build a downloadable GitHub release zip (UI + logo + launch.bat).
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\build_release.ps1

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$Version = (Get-Content -Raw (Join-Path $Root "VERSION")).Trim()
if (-not $Version) { $Version = "1.0.0" }

$Name = "BotEts-$Version"
$Dist = Join-Path $Root "dist"
$Stage = Join-Path $Dist $Name
$Zip = Join-Path $Dist "$Name.zip"

if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
if (Test-Path $Zip) { Remove-Item $Zip -Force }
New-Item -ItemType Directory -Force -Path $Stage | Out-Null

$Include = @(
    "launch.bat",
    "run.bat",
    "config.yaml",
    ".env.example",
    "requirements.txt",
    "VERSION",
    "README.md",
    "selectors.md",
    "assets",
    "src",
    "tests"
)

foreach ($item in $Include) {
    $src = Join-Path $Root $item
    if (-not (Test-Path $src)) {
        Write-Warning "Missing: $item"
        continue
    }
    $dest = Join-Path $Stage $item
    if (Test-Path $src -PathType Container) {
        Copy-Item $src $dest -Recurse -Force
    } else {
        Copy-Item $src $dest -Force
    }
}

# Fresh local state for end users
@"
{
  "sigles": [],
  "bots": []
}
"@ | Set-Content -Path (Join-Path $Stage "launcher.json") -Encoding utf8

# Strip caches from the staged tree
Get-ChildItem $Stage -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem $Stage -Recurse -File -Filter "*.pyc" | Remove-Item -Force -ErrorAction SilentlyContinue

Compress-Archive -Path $Stage -DestinationPath $Zip -Force
Write-Host "Release package ready:"
Write-Host "  $Zip"
Write-Host ""
Write-Host "Publish on GitHub:"
Write-Host "  1. git tag v$Version && git push origin v$Version"
Write-Host "  2. Or open https://github.com/MouadEssaki/BotETS/releases/new"
Write-Host "  3. Upload $Name.zip as the release asset"
Write-Host "Users: unzip -> double-click launch.bat (Python 3.11+ required once)."
