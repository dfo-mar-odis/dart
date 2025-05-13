@echo off

set dart_version=4.1.5

if not exist ".\logs\" (
  mkdir logs
)

if "%server_path%"=="" (
  call dart_env\Scripts\activate.bat
)

echo "Starting webserver: http://localhost:8000/"

Rem Start the webserver
daphne dart.asgi:application >> logs/start_dart.log