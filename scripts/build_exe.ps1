# Build BotEts.exe (one-file). Users download this from GitHub Releases.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$Version = (Get-Content -Raw (Join-Path $Root "VERSION")).Trim()
if (-not $Version) { $Version = "1.0.0" }

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = (Get-Command python).Source
}

& $Python -m pip install -q -r requirements.txt pyinstaller
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

$Dist = Join-Path $Root "dist"
$Work = Join-Path $Root "build"
New-Item -ItemType Directory -Force -Path $Dist | Out-Null

$LogoPng = Join-Path $Root "assets\logo.png"
$LogoIco = Join-Path $Root "assets\logo.ico"
& $Python -m pip install -q pillow
& $Python -c @"
from pathlib import Path
from PIL import Image
png = Path(r'$LogoPng')
ico = Path(r'$LogoIco')
img = Image.open(png).convert('RGBA')
sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
img.save(ico, format='ICO', sizes=sizes)
print('Wrote', ico)
"@
if (-not (Test-Path $LogoIco)) { throw "Failed to create assets/logo.ico" }

$AddData = @(
    "assets;assets",
    "config.yaml;.",
    ".env.example;.",
    "VERSION;.",
    "selectors.md;."
)

$DataArgs = @()
foreach ($item in $AddData) {
    $DataArgs += "--add-data"
    $DataArgs += $item
}

$Hidden = @(
    "playwright",
    "playwright.sync_api",
    "playwright._impl",
    "src",
    "src.ui",
    "src.main",
    "src.worker",
    "src.catalog",
    "src.monitor",
    "src.navigation",
    "src.register",
    "src.browser",
    "src.notify",
    "src.alarm",
    "src.config_loader",
    "src.session",
    "src.paths",
    "src.timeutil",
    "src.capacity",
    "yaml",
    "dotenv",
    "loguru",
    "tkinter"
)

$HiddenArgs = @()
foreach ($mod in $Hidden) {
    $HiddenArgs += "--hidden-import"
    $HiddenArgs += $mod
}

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "BotEts" `
    --icon $LogoIco `
    --distpath $Dist `
    --workpath $Work `
    --paths $Root `
    @DataArgs `
    @HiddenArgs `
    --collect-all playwright `
    --collect-submodules src `
    (Join-Path $Root "botets_exe.py")

if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$Exe = Join-Path $Dist "BotEts.exe"
$Versioned = Join-Path $Dist "BotEts-$Version.exe"
Copy-Item $Exe $Versioned -Force

Write-Host ""
Write-Host "Upload THIS file to GitHub Releases:"
Write-Host "  $Exe"
Write-Host "(optional copy: $Versioned)"
Write-Host ""
Write-Host "Users: download BotEts.exe only, double-click it."
Write-Host "First launch shows a splash, then downloads Chromium into %LOCALAPPDATA%\BotEts"
