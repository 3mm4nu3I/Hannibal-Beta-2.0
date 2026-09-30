@echo off
setlocal
cd /d "%~dp0"
title Hannibal 2+3 Installer
where py >nul 2>&1
if %errorlevel%==0 (
  py -3 integrate_hannibal_modules.py
) else (
  python integrate_hannibal_modules.py
)
if errorlevel 1 (
  echo.
  echo INSTALLATION FAILED. Read the error above.
  pause
  exit /b 1
)
echo.
echo Installation complete. Starting Hannibal...
if exist hannibal_kernel.py (
  where py >nul 2>&1 && py -3 hannibal_kernel.py || python hannibal_kernel.py
) else (
  where py >nul 2>&1 && py -3 hannibal_terminal.py || python hannibal_terminal.py
)
pause
