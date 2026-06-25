@echo off
setlocal EnableExtensions
chcp 65001 > nul

cd /d "%~dp0"

set "PAUSE_ON_ERROR=pause"
if "%~1"=="--silent" set "PAUSE_ON_ERROR=timeout /t 10 > nul"
if "%~1"=="-s" set "PAUSE_ON_ERROR=timeout /t 10 > nul"

set "SYSTEM_PYTHON=python"
set "BUNDLED_PYTHON=C:\Users\pioterlee\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%BUNDLED_PYTHON%" set "SYSTEM_PYTHON=%BUNDLED_PYTHON%"

set "VENV_DIR=%~dp0.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo ==========================================================
    echo Setting up Python virtual environment...
    echo ==========================================================
    "%SYSTEM_PYTHON%" -m venv "%VENV_DIR%"
    if errorlevel 1 goto :fail
)

echo ==========================================================
echo Installing/updating project packages...
echo ==========================================================
"%PYTHON_EXE%" -m pip install --upgrade pip
if errorlevel 1 goto :fail
"%PYTHON_EXE%" -m pip install -r "%~dp0requirements-project.txt"
if errorlevel 1 goto :fail

echo ==========================================================
echo Running daily backend + frontend data update...
echo ==========================================================
"%PYTHON_EXE%" "%~dp0backend\daily_update.py" --push
if errorlevel 1 goto :fail

echo.
echo ==========================================================
echo Daily update complete.
echo ==========================================================
timeout /t 5 > nul
exit /b 0

:fail
echo.
echo ==========================================================
echo Daily update failed. Check logs and backend\data\update_status.json.
echo ==========================================================
if defined PAUSE_ON_ERROR %PAUSE_ON_ERROR%
exit /b 1
