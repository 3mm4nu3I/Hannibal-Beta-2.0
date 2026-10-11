@echo off
title PROJECT HANNIBAL - ORBITAL DIRECTORATE INTEGRATION
color 0C
echo ================================================================
echo  PROJECT HANNIBAL -- ORBITAL DIRECTORATE INTEGRATION
echo ================================================================
echo.

REM Run this from the folder that holds the module files. It installs them into the folder
REM that contains YOUR hannibal_terminal.py (the parent folder if it is there, else this one),
REM then patches that terminal in place. Your terminal is never replaced: patch_hannibal.py makes
REM a backup (hannibal_terminal.py.pre-orbital.bak) and adds only the orbital keys.
if exist "..\hannibal_terminal.py" (
    set "TARGET_DIR=.."
) else (
    set "TARGET_DIR=."
)
echo [*] Target directory: %TARGET_DIR%
echo.

echo [*] Copying orbital module files...
for %%F in (hannibal_orbital.py hannibal_net.py hannibal_spacetrack.py hannibal_nasa.py hannibal_n2yo.py hannibal_login.py hannibal_creds.py hannibal_vault.py hannibal_art.py hannibal_feeder.py run_telemetry.py hannibal_telemetry_node.py hannibal_blueglobe.py hannibal_geoint.py blueglobe_dashboard.html secret_masking.py hannibal_security_bootstrap.py sitecustomize.py patch_hannibal.py requirements.txt hannibal_terminal.spec build.bat run_standalone.bat) do (
    if exist "%%F" (
        if not "%TARGET_DIR%"=="." copy /Y "%%F" "%TARGET_DIR%\%%F" >nul
    )
)

REM Never overwrite the user's own target list / credentials.
if not exist "%TARGET_DIR%\norad_targets.json" (
    if not "%TARGET_DIR%"=="." copy "norad_targets.json" "%TARGET_DIR%\norad_targets.json" >nul
    echo [+] Installed default norad_targets.json
) else (
    echo [=] Kept your existing norad_targets.json
)

echo.
echo [*] Installing dependencies...
python -m pip install -r "%TARGET_DIR%\requirements.txt" --quiet

echo.
echo [*] Patching hannibal_terminal.py (backup is made automatically)...
if exist "%TARGET_DIR%\hannibal_terminal.py" (
    python "%TARGET_DIR%\patch_hannibal.py" "%TARGET_DIR%\hannibal_terminal.py"
) else (
    echo [!] No hannibal_terminal.py in %TARGET_DIR% -- skipped. Standalone use still works.
)

echo.
echo [+] INTEGRATION COMPLETE.
echo [+] Terminal:   python hannibal_terminal.py   (L = fleet link health, B = 3D globe, V = Orbital Ops menu)
echo [+] Standalone: run_standalone.bat            (same menu, no terminal needed)
echo [+] Undo:       python patch_hannibal.py --revert
echo [+] Optional:   set SPACETRACK_USER / SPACETRACK_PASS  (re-entries, close approaches, box score, TLE epochs)
echo                 set BLUEGLOBE_API_KEY                   (if you have a BlueGlobe API key)
echo                 set HANNIBAL_HOME_LAT / HANNIBAL_HOME_LON / HANNIBAL_HOME_NAME  (your sky location)
echo.
pause
