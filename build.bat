@echo off
REM build.bat -- one-command standalone build for PROJECT HANNIBAL
REM Run this from C:\Users\B\Pictures\Hanibal (same folder as
REM hannibal_terminal.py, hannibal_terminal.spec, and requirements.txt).

echo ================================================================
echo  PROJECT HANNIBAL -- Standalone Build
echo ================================================================
echo.
echo [1/3] Installing/updating dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo BUILD FAILED at dependency install. Check the pip error above.
    echo If you see "'python' is not recognized", Python itself isn't on
    echo PATH -- reinstall Python and check "Add python.exe to PATH"
    echo during setup, or run this from an "x64 Native Tools" /
    echo "Python" command prompt shortcut instead of a plain cmd window.
    pause
    exit /b 1
)

echo.
echo [2/3] Cleaning previous build artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo [3/3] Building standalone executable...
REM Using "python -m PyInstaller" instead of calling "pyinstaller" directly.
REM Calling the bare command relies on pip having put Scripts\ on PATH,
REM which doesn't always happen (this is what caused the "not recognized"
REM error). Going through the interpreter that pip just used above finds
REM it every time, regardless of PATH.
python -m PyInstaller hannibal_terminal.spec --noconfirm
if errorlevel 1 (
    echo.
    echo BUILD FAILED during PyInstaller. Check the error output above.
    pause
    exit /b 1
)

echo.
echo ================================================================
echo  BUILD COMPLETE
echo  Your standalone terminal is at:
echo    dist\HANNIBAL_TERMINAL\HANNIBAL_TERMINAL.exe
echo.
echo  The whole dist\HANNIBAL_TERMINAL\ folder needs to travel together
echo  (the .exe depends on the _internal\ folder next to it) -- copy or
echo  shortcut the folder, don't move just the .exe by itself.
echo ================================================================
pause
