@echo off

if not exist ".\logs\" (
  mkdir logs
)

if "%server_path%"=="" (
  call dart_env\Scripts\activate.bat
)

if exist ".\settings\DefaultElogConfiguration.json" python .\manage.py loaddata DefaultElogConfiguration

echo "Starting webserver: http://localhost:8000/"

Rem Start the webserver
daphne dart2.asgi:application >> logs/start_dart.log