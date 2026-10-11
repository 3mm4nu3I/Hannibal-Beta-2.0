@echo off
REM PROJECT HANNIBAL - LOW INTERNET launcher (patch_telemetry 1.2.0)
REM Slow or dropping connection: patient timeouts, more retries, less data, longer cache.
REM Put this file next to hannibal_orbital.py (or next to dist\HANNIBAL.exe's folder).
REM Extra switches pass straight through, e.g.:  HANNIBAL_LOW_INTERNET.bat --help
title PROJECT HANNIBAL - ORBITAL DIRECTORATE [LOW INTERNET]
chcp 65001 >nul
color 0E
cd /d "%~dp0"
set "HANNIBAL_NET_PROFILE=low"

echo  ======================================================
echo   HANNIBAL :: network profile LOW
echo   20 s connect / 60 s read, 3 retries (5/15/30 s apart)
echo   up to 50 observations per satellite (less data)
echo   stops after 1 dead satellite, rest from last scan (*)
echo   auto-rescan every 6 h; N2YO/Space-Track/NASA cache 4x longer
echo  ======================================================
echo.

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"

if exist "hannibal_orbital.py" if defined PY (
    %PY% hannibal_orbital.py %*
    goto :done
)
if exist "hannibal_terminal.py" if defined PY (
    %PY% hannibal_terminal.py %*
    goto :done
)
if exist "dist\HANNIBAL.exe" (
    "dist\HANNIBAL.exe" %*
    goto :done
)
if exist "HANNIBAL.exe" (
    "HANNIBAL.exe" %*
    goto :done
)
echo  [!] Nothing to launch here: no hannibal_orbital.py / hannibal_terminal.py
echo      (with Python installed) and no HANNIBAL.exe. Move this file into the
echo      Hannibal folder and run it again.

:done
echo.
pause
