@echo off

if not exist ".\logs\" (
  mkdir logs
)

set master_branch=4.1.x
set dart_version=4.1.5.1

REM if this is not a git repo, and the application was installed from zip file we just want to run update
REM if this is a cloned version of the git repo we want to pull from master, then run the update

git branch | find "* %master_branch%" > NULL & if not ERRORLEVEL 1 (
	echo "Updating Application"
	git pull origin %master_branch% >> logs/start_dart.log
)

del NULL
call .\update.bat
