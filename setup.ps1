$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "LumiMatch: setting up local Python environment..."

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv .venv
    }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .venv
    }
    else {
        throw "Python 3.12+ was not found. Install Python and run setup.ps1 again."
    }
}

$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

$VersionOk = & $Python -c "import sys; print(int(sys.version_info >= (3, 12)))"
if ($VersionOk.Trim() -ne "1") {
    throw "LumiMatch requires Python 3.12+. The created .venv uses an older Python."
}

& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt
& $Python -m playwright install chromium

Write-Host ""
Write-Host "Ready. Python environment: $Python"
Write-Host "Codex should use this interpreter for all Python commands."
