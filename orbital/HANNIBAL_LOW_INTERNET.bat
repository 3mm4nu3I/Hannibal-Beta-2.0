@echo off
REM PROJECT HANNIBAL - LOW INTERNET launcher (orbital directorate, telemetry 1.2.0)
REM Slow or dropping connection: patient timeouts, more retries, less data, longer cache.
REM Put this file next to hannibal_orbital.py. Extra switches pass straight through.
chcp 65001 >nul
title PROJECT HANNIBAL - ORBITAL DIRECTORATE [LOW INTERNET]
color 0E
cd /d "%~dp0"
set "HANNIBAL_NET_PROFILE=low"
cls
echo.
echo  ========================================================================
echo                                    /\
echo                                   /  \
echo                                  /    \
echo                     ____________/      \____________
echo                     \                              /
echo                       \       PROJECT  HANNIBAL  /
echo                         \ ORBITAL  DIRECTORATE /
echo                         /                      \
echo                        /         ______         \
echo                       /       .-'      '-.       \
echo                      /     .-'            '-.     \
echo                     /   .-'                  '-.   \
echo                    /_.-'                        '-._\
echo.
echo                  ОРБИТАЛЬНОЕ УПРАВЛЕНИЕ  *  КАНАЛ: СЛАБЫЙ
echo  ========================================================================
echo    NETWORK PROFILE: LOW
echo      * 20 s connect / 60 s read, 3 retries 5/15/30 s apart
echo      * up to 50 observations per satellite - less data
echo      * stops after 1 dead satellite, rest from last scan *
echo      * auto-rescan every 6 h; N2YO/Space-Track/NASA/FRED cache 4x longer
echo  ------------------------------------------------------------------------
echo                POYEKHALI!  -  LET'S GO, EVEN ON A BAD LINE
echo  ========================================================================
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
echo      with Python installed, and no HANNIBAL.exe. Move this file into the
echo      Hannibal folder and run it again.

:done
echo.
pause
