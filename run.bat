@echo off
REM ===========================================================================
REM  Run Versatile Radio Programmer from source (Windows).
REM
REM  First run: clones the CHIRP library, downloads Python 3.11 + dependencies
REM  via uv, then launches the app. Subsequent runs just launch (fast).
REM
REM  Prerequisites (one-time):
REM    - uv     ->  winget install --id=astral-sh.uv
REM    - git    ->  https://git-scm.com/download/win  (Git for Windows)
REM  WebView2 runtime ships with Windows 11 / Microsoft Edge; if absent the
REM  channel grid falls back to a plain text view.
REM ===========================================================================
setlocal
cd /d "%~dp0"

REM The CHIRP commit this VRP version was tested against (reproducible pin).
set "CHIRP_SHA="
if exist CHIRP_COMMIT set /p CHIRP_SHA=<CHIRP_COMMIT

where uv >nul 2>&1
if errorlevel 1 (
  echo.
  echo 'uv' was not found on your PATH.
  echo Install it once with:   winget install --id=astral-sh.uv
  echo Then run this script again.
  echo.
  pause
  exit /b 1
)

where git >nul 2>&1
if errorlevel 1 (
  echo.
  echo 'git' was not found on your PATH. Install Git for Windows:
  echo   https://git-scm.com/download/win
  echo.
  pause
  exit /b 1
)

REM CHIRP is a required editable path dependency; clone it into .\chirp if missing,
REM pinned to the tested commit (CHIRP_COMMIT) for reproducibility.
if not exist "chirp\chirp\__init__.py" (
  echo Cloning the CHIRP radio library into .\chirp ...
  git clone --depth=1 https://github.com/kk7ds/chirp.git chirp
  if errorlevel 1 (
    echo.
    echo Failed to clone CHIRP. Check your internet connection and try again.
    pause
    exit /b 1
  )
  if not "%CHIRP_SHA%"=="" (
    echo Pinning CHIRP to %CHIRP_SHA% ...
    git -C chirp fetch --depth=1 origin %CHIRP_SHA% && git -C chirp checkout --quiet %CHIRP_SHA%
    if errorlevel 1 echo WARNING: could not pin CHIRP to that commit; using latest instead.
  )
)

echo Installing/updating dependencies (first run downloads Python 3.11 + packages)...
call uv sync
if errorlevel 1 (
  echo.
  echo Dependency installation failed. See the messages above.
  pause
  exit /b 1
)

echo Starting Versatile Radio Programmer...
uv run python main.py
if errorlevel 1 (
  echo.
  echo The app exited with an error. See the messages above.
  pause
)
endlocal
