@echo off

set /p dart_version=<version.txt

if not exist ".\logs\" (
  mkdir logs
)

if "%server_path%"=="" (
  call dart_env\Scripts\activate.bat
)

echo "Starting webserver: http://localhost:8000/"

Rem Start the webserver
python manage.py dart