@echo off

if not exist ".\logs\" (
  mkdir logs
)

REM If this was run from a clone repo we can force an update of the python libraries, collectstatic or a
REM migration on the database by changing the update version

set /p update_version=<version.txt

REM Install uv if not already present
where uv >NUL 2>&1
if ERRORLEVEL 1 (
  echo Installing uv...
  powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  REM Refresh PATH so uv is available in this session
  set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)

set first_run=0
if not exist ".env" (
  set first_run=1
  echo "Creating .env file" >> logs/start_dart.log
  copy .env_sample .env >> logs/start_dart.log
  REM python -m venv ".\dart_env" >> logs/start_dart.log
)

Rem If the dart version was set in the start_dart.bat and it matches the update_version set here we can skip the
REM python libray update. Start_dart.bat will load dart_version from the version.txt file, then pulls from git
REM if there was an update to git the new version is then set in update.bat as 'update_version'. If the two version
REM numbers are different it means there was an update and the python libs, fixture files, or static content may need
REM to be updated before the server starts. If the user just calls update.bat then the dart_version won't have been
REM set and we'll force an update to everything at the user's request.

echo Checking if update required
echo DART version: '%dart_version%'
echo Update to version: '%update_version%'

if not defined dart_version goto do_sync
if %dart_version%==%update_version% goto start_server

:do_sync
echo "Installing/updating Python libraries via uv, this may take several minutes"
uv sync

:start_server
echo "Creating/Updating local database"

REM If the local database already exists we can skip the initial loading of user settings fixtures.
REM We don't want to override any user settings if the user has created, but on a first run we need
REM to set some defaults.
if not exist ".\dart_local.sqlite3" (
  set init_settings=0
) else (
  set init_settings=1
)

echo "Running database migrations"
uv run .\manage.py migrate >> logs/start_dart.log

echo "Updating default biochem fixtures"
uv run .\manage.py loaddata default_biochem_fixtures >> logs/start_dart.log

if defined init_settings (
  if %init_settings%==0 (
    echo "Loading default settings fixtures"
    uv run .\manage.py loaddata default_settings_fixtures >> logs/start_dart.log
  )
)

echo "Collecting static files, this may take a moment"
uv run .\manage.py collectstatic --noinput

call server.bat
