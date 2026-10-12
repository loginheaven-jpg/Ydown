param([string]$Python = "", [switch]$SkipInstaller)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $root
if (!$Python) {
    $localPython = Join-Path $root ".venv\Scripts\python.exe"
    $Python = if (Test-Path -LiteralPath $localPython) { $localPython } else { "python" }
}
function Run-Python {
    & $Python @args
    if ($LASTEXITCODE -ne 0) { throw "Python command failed: $args" }
}
Run-Python scripts/fetch-runtime.py
Run-Python -m pytest -q
Run-Python -m PyInstaller --noconfirm --clean --name YDown --onedir --windowed `
    --add-data "templates;templates" --add-data "runtime;runtime" `
    --collect-all yt_dlp --collect-all yt_dlp_ejs --collect-all uvicorn `
    --collect-all certifi --hidden-import tkinter launch.py
$version = (& $Python -c "from version import VERSION; print(VERSION)").Trim()
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+\.\d+$') { throw "Invalid VERSION" }
Copy-Item -LiteralPath "README.md" -Destination "dist\YDown\README.md"
Copy-Item -LiteralPath "packaging\THIRD-PARTY-NOTICES.md" -Destination "dist\YDown\THIRD-PARTY-NOTICES.md"
Run-Python -m piplicenses --format=json --with-license-file --with-urls `
    --output-file=dist/YDown/third-party-licenses.json
Run-Python scripts/smoke-bundle.py dist/YDown/YDown.exe
$archive = Join-Path $root "dist\YDown-$version-windows-x64.zip"
Compress-Archive -Path "dist\YDown" -DestinationPath $archive -Force
if (!$SkipInstaller) {
    $candidates = @(
        (Join-Path $root ".tools\inno\ISCC.exe"),
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )
    $compiler = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (!$compiler) {
        $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($command) { $compiler = $command.Source }
    }
    if (!$compiler) { throw "Install Inno Setup 6, or build with -SkipInstaller for a portable ZIP." }
    & $compiler "/DAppVersion=$version" "packaging\YDown.iss"
    if ($LASTEXITCODE -ne 0) { throw "Installer compilation failed" }
    Run-Python scripts/smoke-installer.py dist/YDown-Setup-x64.exe
}
$assets = Get-ChildItem -LiteralPath (Join-Path $root "dist") -File | Where-Object { $_.Extension -in ".zip", ".exe" }
$checksums = foreach ($asset in $assets) {
    $hash = (Get-FileHash -LiteralPath $asset.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $($asset.Name)"
}
$checksums | Set-Content -Encoding ascii -LiteralPath (Join-Path $root "dist\SHA256SUMS.txt")
Write-Host "Ready: $($assets.Name -join ', ')"
