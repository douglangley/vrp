@echo off
REM ===========================================================================
REM  Run Versatile Radio Programmer from source (Windows). See run-mac.sh for
REM  the macOS equivalent.
REM
REM  First run: clones the CHIRP library, downloads Python 3.11 + dependencies
REM  via uv, then launches the app (the native UI by default on Windows).
REM  Subsequent runs just launch (fast). Any arguments (e.g. --debug,
REM  --webview) are passed through to main.py.
REM
REM  Prerequisites (one-time):
REM    - uv     ->  winget install --id=astral-sh.uv
REM    - git    ->  https://git-scm.com/download/win  (Git for Windows)
REM  The --webview UI (VoiceOver-oriented; macOS's default) needs the
REM  WebView2 runtime, which ships with Windows 11 / Microsoft Edge; the
REM  default native UI doesn't need it.
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
REM --inexact: install the run dependencies but DON'T uninstall anything else
REM already in the venv. Without it, plain "uv sync" prunes the env to exactly
REM the base deps, removing dev tools like pytest every time a developer runs
REM the app (testers are unaffected — a fresh env has nothing extra to keep).
call uv sync --inexact
if errorlevel 1 (
  echo.
  echo Dependency installation failed. See the messages above.
  pause
  exit /b 1
)

echo Starting Versatile Radio Programmer...
uv run python main.py %*
if errorlevel 1 (
  echo.
  echo The app exited with an error. See the messages above.
  pause
)
endlocal
