@echo off
REM Check if a branch name is passed as an argument, otherwise default to master
if "%~1"=="" (
  set master_branch=master
) else (
  set master_branch=%~1
)

git branch | find "* %master_branch%" >NUL 2>&1
if ERRORLEVEL 1 (
    git checkout %master_branch%
)

REM Get the hash code of the local branch
for /f "tokens=1,2,3 delims= " %%a in ('git branch -v ^| find "* %master_branch%"') do (
    set local_hash=%%c
)

REM Get the hash code of the remote branch
for /f "tokens=1,2 delims= " %%a in ('git branch -v -a ^| find "origin/%master_branch%"') do (
    set remote_hash=%%b
)

REM Compare the hash codes and pull if they are different
if not "%local_hash%"=="%remote_hash%" (
    echo "Updates were found, Pulling changes..."
    git pull origin %master_branch%
)