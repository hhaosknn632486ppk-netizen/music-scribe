@echo off
setlocal
if "%~1"=="" (
  echo Drag one audio file onto this launcher for optional Demucs separation.
  echo Separation requires installed torch/torchaudio and cached Demucs weights.
  pause
  exit /b 2
)
set "MUSIC_SCRIBE_OUTPUT=%~dp0runs\%~n1_separated_%RANDOM%_%RANDOM%"
call "%~dp0music_scribe_cli.cmd" "%~1" -o "%MUSIC_SCRIBE_OUTPUT%" --title "%~n1" --separate --stems other,bass
if errorlevel 1 (
  echo Separation or transcription failed. See diagnostics above.
  pause
  exit /b 1
)
start "" "%MUSIC_SCRIBE_OUTPUT%\report.html"
