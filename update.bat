@echo off

if not exist ".\logs\" (
  mkdir logs
)

REM If this was run from a clone repo we can force an update of the python libraries, collectstatic or a
REM migration on the database by changing the update version

set /p update_version=<version.txt
echo %update_version%> current_version.txt

set first_run=0
set server_path=.\dart_env\Scripts\activate.bat
if not exist ".\dart_env\" (
  set first_run=1
  echo "Creating .env file" >> logs/start_dart.log
  copy .env_sample .env >> logs/start_dart.log
  python -m venv ".\dart_env" >> logs/start_dart.log
)

call %server_path% >> logs/start_dart.log

python -m pip install --upgrade pip

echo Checking if update required
echo DART version: '%dart_version%'
echo Update to version: '%update_version%'
Rem If this is not the first run and the dart version matches that in the start_dart.bat file skip updating.
if not defined dart_version (
	if %first_run%==0 goto start_server
)
if %dart_version%==%update_version% goto start_server

echo "Updating Python Libraries, this may take several minutes"
python -m pip install matplotlib --only-binary :all:
python -m pip install -r .\requirements.txt

:start_server
echo "Creating/Updating local database"

REM If the local database already exists we can skip the initial loading of fixtures, this will speed up the update process.
if not exist ".\dart_local.sqlite3" (
  echo "No local settings db"
  set init_settings=0
) else (
  set init_settings=1
)

python .\manage.py migrate >> logs/start_dart.log
python .\manage.py loaddata default_biochem_fixtures >> logs/start_dart.log
if defined init_settings (
  if %init_settings%==0 (
    echo "Loading default settings fixtures"
    python .\manage.py loaddata default_settings_fixtures >> logs/start_dart.log
  )
)

echo "Collecting static files, this may take a moment"
python .\manage.py collectstatic --noinput

call server.bat
