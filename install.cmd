@echo off
setlocal
set "bindir=%USERPROFILE%\.local\bin"
if not exist "%bindir%" mkdir "%bindir%"
if errorlevel 1 exit /b 1
copy /y "%~dp0agentmeet.py" "%bindir%\agentmeet.py" >nul || exit /b 1
copy /y "%~dp0agentmeet.cmd" "%bindir%\agentmeet.cmd" >nul || exit /b 1
echo AgentMeet installed in "%bindir%".
