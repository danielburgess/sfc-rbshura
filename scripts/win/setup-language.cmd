@echo off
REM Double-click wrapper: runs setup-language.ps1 with the execution policy
REM bypassed for this single invocation (does NOT change the machine's global
REM policy) so Windows does not block the unsigned project script. Forwards
REM any args (e.g. --from en --to fr --dry-run).
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-language.ps1" %*
if errorlevel 1 (
  echo.
  echo Language staging failed. Review the messages above.
  pause
)
