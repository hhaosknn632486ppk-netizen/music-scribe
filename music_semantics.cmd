@echo off
setlocal
if "%~1"=="" (
  echo Drag one audio file onto this launcher for local style and emotion analysis.
  pause
  exit /b 2
)
set "MUSIC_SCRIBE_OUTPUT=%~dp0runs\%~n1_semantics_%RANDOM%_%RANDOM%"
call "%~dp0music_scribe_cli.cmd" "%~1" -o "%MUSIC_SCRIBE_OUTPUT%" --semantics-only --semantics-cache "%~dp0cache"
if errorlevel 1 (
  echo Analysis failed. See diagnostics above.
  pause
  exit /b 1
)
start "" "%MUSIC_SCRIBE_OUTPUT%\semantics.html"
