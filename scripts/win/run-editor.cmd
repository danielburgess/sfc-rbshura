@echo off
REM Double-click wrapper: runs run-editor.ps1 with the execution policy bypassed
REM for this single invocation (does NOT change the machine's global policy) so
REM Windows does not block the unsigned project script. Forwards any args.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-editor.ps1" %*
if errorlevel 1 (
  echo.
  echo The script editor failed to launch. Review the messages above.
  pause
)
