@echo off
setlocal
set "POWERSHELL=powershell.exe"
if defined SystemRoot if exist "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" set "POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"

"%POWERSHELL%" -ExecutionPolicy Bypass -File "%~dp0install_deps.ps1"
exit /b %errorlevel%
