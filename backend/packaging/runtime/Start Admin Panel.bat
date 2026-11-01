@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"
set "TKD_RUNTIME_ROOT=%CD%"

set "EXE_PATH=.\PoomsaeServer\PoomsaeServer.exe"
if not exist "%EXE_PATH%" (
  echo [ERROR] Executable not found: %EXE_PATH%
  echo Make sure the PoomsaeServer folder is next to this .bat file
  pause
  exit /b 1
)

set "OPEN_HOST=127.0.0.1"
set "OPEN_PORT=8080"
set "ADMIN_PATH=/admin"

if exist ".env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
    set "K=%%A"
    set "V=%%B"
    if /I "!K!"=="TKD_PORT" set "OPEN_PORT=!V!"
    if /I "!K!"=="TKD_ADMIN_BASE_PATH" set "ADMIN_PATH=!V!"
  )
)

start "Poomsae Server" "%EXE_PATH%"
timeout /t 3 /nobreak >nul
start "Admin Panel" "http://%OPEN_HOST%:%OPEN_PORT%%ADMIN_PATH%"

exit /b 0
