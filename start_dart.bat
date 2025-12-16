@echo off

if exist "logs\start_dart.log" del "logs\start_dart.log"
if not exist ".\logs\" (
  mkdir logs
)

REM Check if a branch name is passed as an argument, otherwise default to master
if "%~1"=="" (
  set master_branch=master
) else (
  set master_branch=%~1
)

set /p dart_version=<current_version.txt

echo ============================================ >> logs/start_dart.log
echo Version: %dart_version% >> logs/start_dart.log
echo ============================================ >> logs/start_dart.log

REM Check if Oracle Instant Client is in the CLASSPATH If not and the version number isn't empty
REM we'll give the user a popup saying we can't update to 4.2.0+ and just start the server
echo %CLASSPATH% | findstr /i "Oracle\12.2.0_Instant_x64" >nul
if errorlevel 1 (
    msg %username% "Oracle Instant Client 12 is required for DART 4.2.0+. Please install it from the DFO software center and run start_dart.bat again to update the applciation."
    del NULL
    call .\server.bat
)

REM if this is not a git repo, and the application was installed from zip file we just want to run update
REM if this is a cloned version of the git repo we want to pull from master, then run the update

git branch | find "* %master_branch%" > NULL
if ERRORLEVEL 1 (
	git checkout %master_branch%
	git pull origin %master_branch%
)

curl.exe -Is https://github.com > NUL
if ERRORLEVEL 1 (
    echo "No internet connection. Skipping update." >> logs/start_dart.log
    del NULL
    call .\server.bat
) else (
    echo "Updating Application" >> logs/start_dart.log
    git pull origin %master_branch% >> logs/start_dart.log
    del NULL
    call .\update.bat
)