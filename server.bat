@echo off

set /p dart_version=<version.txt

if not exist ".\logs\" (
  mkdir logs
)

echo "Starting webserver: http://localhost:8000/"

REM Start the webserver using uv run (no need to activate venv manually)
uv run manage.py dart
