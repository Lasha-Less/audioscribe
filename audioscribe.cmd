@echo off
setlocal
set "PATH=%~dp0.venv\Scripts;%PATH%"
set "PYTHONPATH=%~dp0;%PYTHONPATH%"
"%~dp0.venv\Scripts\python.exe" -m audioscribe %*
exit /b %errorlevel%