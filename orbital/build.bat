@echo off
REM build.bat -- standalone build script for PROJECT HANNIBAL

echo ================================================================
echo  PROJECT HANNIBAL -- Standalone Build with Secret Masking
echo ================================================================
echo.
echo [1/3] Installing/updating dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo BUILD FAILED at dependency install. Check pip errors above.
    pause
    exit /b 1
)

echo.
echo [2/3] Cleaning previous build artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo [3/3] Building standalone executable...
python -m PyInstaller hannibal_terminal.spec --noconfirm
if errorlevel 1 (
    echo.
    echo BUILD FAILED during PyInstaller compilation.
    pause
    exit /b 1
)

REM Put the editable target list next to the exe (the engine reads it from there first).
if exist norad_targets.json copy /Y norad_targets.json dist\HANNIBAL_TERMINAL\norad_targets.json >nul

echo.
echo ================================================================
echo  BUILD COMPLETE
echo  Standalone binary output:
echo    dist\HANNIBAL_TERMINAL\HANNIBAL_TERMINAL.exe
echo ================================================================
pause