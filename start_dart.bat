@echo off

if not exist ".\logs\" (
  mkdir logs
)

set dart_version=0.0

echo "Updating Application"
git pull origin master >> logs/stat_dart.log

call .\update.bat