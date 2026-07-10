$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$python = if (Test-Path ".venv\Scripts\python.exe") {
    ".venv\Scripts\python.exe"
} else {
    "python"
}

function Invoke-Checked {
    param(
        [string]$Executable,
        [string[]]$Arguments
    )
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Executable $Arguments"
    }
}

Invoke-Checked $python @("-m", "pip", "install", "-e", ".[dev]")
Invoke-Checked $python @("-m", "pytest", "-q")
Invoke-Checked $python @(
    "-m",
    "PyInstaller",
    "--clean",
    "--noconfirm",
    "conf-edit.spec"
)

$executable = Join-Path $repoRoot "dist\ConfEdit.exe"
if (-not (Test-Path $executable)) {
    throw "dist\ConfEdit.exe was not produced"
}

$hash = Get-FileHash -Algorithm SHA256 -LiteralPath $executable
Write-Host "Built $executable"
Write-Host "SHA256 $($hash.Hash)"
