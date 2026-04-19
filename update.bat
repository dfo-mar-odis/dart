@echo off

if not exist ".\logs\" (
  mkdir logs
)

REM If this was run from a clone repo we can force an update of the python libraries, collectstatic or a
REM migration on the database by changing the update version

set /p update_version=<version.txt
echo %update_version%> current_version.txt

REM Install uv if not already present
where uv >NUL 2>&1
if ERRORLEVEL 1 (
  echo Installing uv...
  powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  REM Refresh PATH so uv is available in this session
  set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)

set first_run=0
if not exist ".venv\" (
  set first_run=1
  if not exist ".env" (
    copy .env_sample .env
  )
)

echo Checking if update required
echo DART version: '%dart_version%'
echo Update to version: '%update_version%'

REM If this is not the first run and the dart version matches skip updating packages.
if not defined dart_version goto do_sync
if %first_run%==1 goto do_sync
if (%dart_version%==%update_version%) goto start_server

:do_sync
echo "Installing/updating Python libraries via uv, this may take several minutes"
uv sync >> logs/start_dart.log 2>&1

:start_server
echo "Creating/Updating local database"
uv run python .\manage.py migrate >> logs/start_dart.log

echo "Collecting static files, this may take a moment"
uv run python .\manage.py collectstatic --noinput

call server.bat
