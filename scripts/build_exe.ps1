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

$Logo = Join-Path $Root "assets\logo.png"
$IconArgs = @()
# PyInstaller wants .ico for --icon; PNG still bundled as data
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
Write-Host "EXE ready:"
Write-Host "  $Exe"
Write-Host "  $Versioned"
Write-Host ""
Write-Host "Users download BotEts.exe, double-click it."
Write-Host "First launch downloads Chromium into %LOCALAPPDATA%\BotEts"
