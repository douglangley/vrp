@echo off
setlocal enabledelayedexpansion

rem Delete leftover pytest --basetemp roots (.test-tmp-*) from the repo root.
rem
rem Some of these end up with an ACL that denies the owning user outright:
rem Get-Acl, rmdir, and takeown all fail with "access denied" from a normal
rem shell, and every `git status` prints a permission warning for them. Taking
rem ownership needs elevation, so this script re-launches itself as admin.
rem
rem It only ever touches directories matching .test-tmp-* directly inside the
rem repo root, which is derived from this script's own location.

set "ROOT=%~dp0.."
pushd "%ROOT%" || (echo Could not enter the repo root. & pause & exit /b 1)
set "ROOT=%CD%"
popd

rem -- Re-launch elevated if we are not already admin -------------------------
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Administrator rights are required to take ownership of these folders.
    echo Approve the Windows prompt to continue.
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b 0
)

echo.
echo Cleaning leftover test temp folders in:
echo   %ROOT%
echo.

set /a FOUND=0
for /d %%D in ("%ROOT%\.test-tmp-*") do (
    set /a FOUND+=1
    echo Found: %%~nxD
)

if %FOUND%==0 (
    echo Nothing to clean. No .test-tmp-* folders remain.
    echo.
    pause
    exit /b 0
)

echo.
echo %FOUND% folder^(s^) will be deleted.
echo.

set /a GONE=0
set /a LEFT=0
for /d %%D in ("%ROOT%\.test-tmp-*") do (
    echo Removing %%~nxD
    takeown /f "%%D" /r /d y >nul 2>&1
    icacls "%%D" /grant "%USERNAME%:(F)" /t >nul 2>&1
    rmdir /s /q "%%D" >nul 2>&1
    if exist "%%D" (
        set /a LEFT+=1
        echo   FAILED: %%~nxD could not be removed.
    ) else (
        set /a GONE+=1
        echo   Removed.
    )
)

echo.
echo Done. Removed !GONE!, failed !LEFT!.
if !LEFT! gtr 0 (
    echo.
    echo A folder that still fails is usually held open by another program.
    echo Close editors, terminals, and antivirus scans on the repo, then rerun.
)
echo.
pause
endlocal
