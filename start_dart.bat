@echo off

if not exist ".\logs\" (
  mkdir logs
)

set dart_version=3.3.0

REM if this is not a git repo, and the application was installed from zip file we just want to run update
REM if this is a cloned version of the git repo we want to pull from master, then run the update

git branch | find "* master" > NULL & if ERRORLEVEL 1 (
	del NULL
	call .\update.bat
) else (
	echo "Updating Application"
	git pull origin master >> logs/start_dart.log

	del NULL
	call .\update.bat
)
