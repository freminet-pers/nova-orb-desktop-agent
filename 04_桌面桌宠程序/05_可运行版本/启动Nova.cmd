@echo off
chcp 65001 >nul
set "EXE=%~dp0NovaOrb\Coco.exe"
if not exist "%EXE%" (
  echo 未找到 Nova Orb 冻结包：%EXE%
  pause
  exit /b 1
)
rem Ask the existing Windows shell to launch Nova outside this command window.
explorer.exe "%EXE%"
