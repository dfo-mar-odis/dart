@echo off

if not exist ".\logs\" (
  mkdir logs
)

REM If this was run from a clone repo we can force an update of the python libraries, collectstatic or a
REM migration on the database by changing the update version

set update_version=3.3.0

set first_run=0
set server_path=.\dart_env\Scripts\activate.bat
if not exist ".\dart_env\" (
  set first_run=1
  copy .env_sample .env
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
if (%dart_version%==%update_version%) goto start_server

echo "Updating Python Libraries, this may take several minutes"
python -m pip install -r .\requirements.txt >> logs/start_dart.log

:start_server
echo "Creating/Updating local database"
python .\manage.py migrate >> logs/start_dart.log

echo "Collecting static files, this may take a moment"
python .\manage.py collectstatic --noinput

call server.bat
