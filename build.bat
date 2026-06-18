@echo off
REM ===========================================================================
REM  Build Versatile Radio Programmer into a single-file Windows .exe (PyInstaller).
REM  Run this OUTSIDE Claude (double-click, or `build.bat` in a terminal).
REM
REM  PyInstaller freezes bytecode (no per-driver C compile like Nuitka), so
REM  this is fast -- usually well under a minute even with all 552 CHIRP
REM  drivers bundled. Full output is shown live AND saved to a timestamped
REM  build_*.log so we can debug a failure after the fact.
REM ===========================================================================
setlocal
cd /d "%~dp0"

REM Timestamped log name (PowerShell is always present on Win10/11).
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"`) do set "TS=%%i"
set "LOG=build_%TS%.log"

echo ============================================================
echo  Building Versatile Radio Programmer (PyInstaller single-file .exe)
echo  Bundles 552 CHIRP drivers + app.
echo  Live output is also saved to: %LOG%
echo ============================================================
echo.

echo [1/2] Installing build dependencies (uv sync --extra build)...
call uv sync --extra build
if errorlevel 1 (
  echo.
  echo Failed to install build dependencies. Is 'uv' installed and on PATH?
  pause
  exit /b 1
)

echo.
echo [2/2] Building...
REM Tee-Object shows output live AND writes the log; propagate the real exit code.
powershell -NoProfile -ExecutionPolicy Bypass -Command "uv run python build.py 2>&1 | Tee-Object -FilePath '%LOG%'; exit $LASTEXITCODE"
set "RC=%ERRORLEVEL%"

echo.
echo ============================================================
if "%RC%"=="0" (
  echo  BUILD SUCCEEDED.  Output: dist\vrp.exe
) else (
  echo  BUILD FAILED ^(exit code %RC%^).  See the log for details.
)
echo  Log: %LOG%
echo ============================================================
echo.
pause
endlocal
