@echo off

if exist "logs\start_dart.log" del "logs\start_dart.log"
if not exist ".\logs\" (
  mkdir logs
)

set master_branch=master
set /p dart_version=<current_version.txt

echo ============================================ >> logs/start_dart.log
echo Version: %dart_version% >> logs/start_dart.log
echo ============================================ >> logs/start_dart.log

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