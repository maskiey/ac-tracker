# 在项目根目录执行: powershell -ExecutionPolicy Bypass -File packaging/build_windows.ps1
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
python -m pip install -r requirements-desktop.txt
python -m PyInstaller packaging/acm_tracker.spec --noconfirm
Write-Host "输出: $Root\dist\AC-Tracker\AC-Tracker.exe"
