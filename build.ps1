# Gera dist\Prisma.exe (arquivo único, pede administrador ao abrir).
# Uso: powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) {
    python -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
& .\.venv\Scripts\python.exe -m pip install --quiet PySide6-Essentials pyinstaller

& .\.venv\Scripts\python.exe tools\make_icon.py

& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin `
    --name Prisma --icon assets\prisma.ico `
    --exclude-module tkinter --exclude-module unittest --exclude-module pydoc `
    Prisma.py

Write-Host ""
Write-Host "Pronto: $PSScriptRoot\dist\Prisma.exe"
