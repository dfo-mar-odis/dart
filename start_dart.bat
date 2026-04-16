@echo off

if not exist ".\logs\" (
  mkdir logs
)
if exist "logs\start_dart.log" del "logs\start_dart.log"

REM Check if a branch name is passed as an argument, otherwise default to master
if "%~1"=="" (
  set master_branch=master
) else (
  set master_branch=%~1
)

if exist ".\current_version.txt" (
  set /p dart_version=<current_version.txt
) else (
  set dart_version=-1
)

echo ============================================ >> logs/start_dart.log
echo Version: %dart_version% >> logs/start_dart.log
echo ============================================ >> logs/start_dart.log

REM if this is not a git repo, and the application was installed from zip file we just want to run 
REM    the update script to install python libraries and create the local DB
REM if this is a cloned version of the git repo we want to pull from master, then run the update

git branch | find "* %master_branch%" > NULL
if ERRORLEVEL 1 (
    git checkout %master_branch%
    git pull origin %master_branch%
) else (
    call .\update.bat
)

REM Check to see if the user has access to github.com to see if the user has an internet connection
REM     If they don't have an internet conection just start the server, if they do, run the update script

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