@echo off
setlocal
set "ORT_DISABLE_TELEMETRY=1"
set "MUSIC_SCRIBE_RUNTIME=%MUSIC_SCRIBE_PYTHON%"
if defined MUSIC_SCRIBE_RUNTIME goto run
if exist "%~dp0.venv\Scripts\python.exe" (
  set "MUSIC_SCRIBE_RUNTIME=%~dp0.venv\Scripts\python.exe"
  goto run
)
set "MUSIC_SCRIBE_RUNTIME=python"
:run
"%MUSIC_SCRIBE_RUNTIME%" "%~dp0music_scribe.py" %*
exit /b %ERRORLEVEL%
