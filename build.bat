@echo off
:: ============================================================
:: PIKO SmartControl Protocol Analyzer — Windows build script
::
:: Requirements:
::   Python 3.11+ in PATH
::   Run from the project root (where this file lives)
:: ============================================================

setlocal enabledelayedexpansion

set VENV=.venv_build
set DIST=dist\PIKO_Analyzer
set LOG=build_log.txt

echo.
echo === PIKO Analyzer Windows Build ===
echo.

:: 1. Create venv if it doesn't exist
if not exist "%VENV%\Scripts\python.exe" (
    echo [1/5] Creating virtual environment...
    python -m venv %VENV%
    if errorlevel 1 (
        echo ERROR: Failed to create venv. Is Python 3.11+ installed and in PATH?
        pause & exit /b 1
    )
) else (
    echo [1/5] Virtual environment already exists.
)

:: 2. Install / upgrade dependencies
echo [2/5] Installing dependencies...
%VENV%\Scripts\pip install --upgrade pip --quiet
%VENV%\Scripts\pip install -r requirements.txt pyinstaller --quiet
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause & exit /b 1
)

:: 3. Run tests before building
echo [3/5] Running tests...
%VENV%\Scripts\python -m pytest tests\ -q --tb=short > %LOG% 2>&1
if errorlevel 1 (
    echo ERROR: Tests failed. See %LOG% for details.
    type %LOG%
    pause & exit /b 1
)
echo       Tests passed.

:: 4. Build with PyInstaller
echo [4/5] Building executable (this may take 1-3 minutes)...
%VENV%\Scripts\pyinstaller piko_analyzer.spec --clean --noconfirm >> %LOG% 2>&1
if errorlevel 1 (
    echo ERROR: PyInstaller failed. See %LOG% for details.
    type %LOG%
    pause & exit /b 1
)

:: 5. Verify output
echo [5/5] Verifying output...
if exist "%DIST%\PIKO_Analyzer.exe" (
    echo.
    echo ============================================================
    echo  BUILD SUCCESSFUL
    echo  Output: %DIST%\
    echo  Executable: %DIST%\PIKO_Analyzer.exe
    echo ============================================================
    echo.
    :: Show folder size
    for /f "tokens=3" %%a in ('dir /s /-c "%DIST%" ^| findstr /c:"File(s)"') do (
        echo  Total size: %%a bytes
    )
) else (
    echo ERROR: Expected executable not found at %DIST%\PIKO_Analyzer.exe
    type %LOG%
    pause & exit /b 1
)

echo.
echo Done. Press any key to open the output folder.
pause > nul
explorer %DIST%
