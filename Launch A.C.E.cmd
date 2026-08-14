@echo off
setlocal
cd /d "%~dp0"

if exist "A.C.E.exe" (
    start "A.C.E." "A.C.E.exe"
    exit /b 0
)

where pyw >nul 2>&1
if %errorlevel% equ 0 (
    start "A.C.E." pyw -3 main.py
    exit /b 0
)

echo A.C.E.exe or Python 3 was not found.
pause
exit /b 1
