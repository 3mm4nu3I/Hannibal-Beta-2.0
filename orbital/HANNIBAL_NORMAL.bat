@echo off
REM PROJECT HANNIBAL - NORMAL LINK launcher (patch_telemetry 1.2.0)
REM Normal internet: fast timeouts, full SatNOGS window, rescans every 30 min.
REM Put this file next to hannibal_orbital.py (or next to dist\HANNIBAL.exe's folder).
REM Extra switches pass straight through, e.g.:  HANNIBAL_NORMAL.bat --help
title PROJECT HANNIBAL - ORBITAL DIRECTORATE [NORMAL LINK]
chcp 65001 >nul
color 0C
cd /d "%~dp0"
set "HANNIBAL_NET_PROFILE=normal"

echo  ===========================================================
echo   HANNIBAL :: network profile NORMAL
echo   10 s connect / 30 s read, 2 retries
echo   up to 150 observations per satellite
echo   auto-rescan every 30 min
echo  ===========================================================
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
