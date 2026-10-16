@echo off
rem Command line for the atlasmd plugin on Windows. Put this folder on PATH, or call it by path.
rem It uses the Python launcher when it exists, and python when it does not.
setlocal
set "CLI=%~dp0..\atlasmd\cli.py"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%CLI%" %*
) else (
  python "%CLI%" %*
)
exit /b %errorlevel%
