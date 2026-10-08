@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHON=python"

if exist "%ROOT%.venv\Scripts\python.exe" set "PYTHON=%ROOT%.venv\Scripts\python.exe"

pushd "%ROOT%acs_routing"
"%PYTHON%" -m acs_routing.gui
set "EXIT_CODE=%ERRORLEVEL%"
popd

if not "%EXIT_CODE%"=="0" (
    echo.
    echo A GUI foi encerrada com erro. Codigo: %EXIT_CODE%
    pause
)

exit /b %EXIT_CODE%
