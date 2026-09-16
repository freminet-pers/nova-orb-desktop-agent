@echo off
chcp 65001 >nul
set "EXE=%~dp0NovaOrb\Coco.exe"
if not exist "%EXE%" (
  echo 未找到 Nova Orb 冻结包：%EXE%
  pause
  exit /b 1
)
rem This visible launch passes --settings to an already running single instance.
start "" "%EXE%" --settings
