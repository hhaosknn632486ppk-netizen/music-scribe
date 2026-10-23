@echo off
setlocal
if "%~1"=="" (
  echo Drag an audio file onto this launcher.
  echo For all options use music_scribe_cli.cmd --help
  pause
  exit /b 2
)
set "MUSIC_SCRIBE_OUTPUT=%~dp0runs\%~n1_%RANDOM%_%RANDOM%"
call "%~dp0music_scribe_cli.cmd" "%~1" -o "%MUSIC_SCRIBE_OUTPUT%" --title "%~n1"
if errorlevel 1 (
  echo Analysis or score generation failed. See diagnostics above.
  pause
  exit /b 1
)
start "" "%MUSIC_SCRIBE_OUTPUT%\report.html"
