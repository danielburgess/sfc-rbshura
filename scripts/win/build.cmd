@echo off
REM Double-click wrapper: runs build.ps1 with the execution policy bypassed for
REM this single invocation (does NOT change the machine's global policy) so
REM Windows does not block the unsigned project script. Forwards any args
REM (e.g. -Patcher, -UpdateAudit).
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1" %*
if errorlevel 1 (
  echo.
  echo Build failed. Review the messages above.
  pause
)
