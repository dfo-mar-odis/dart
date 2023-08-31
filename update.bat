@echo off

if not exist ".\logs\" (
  mkdir logs
)

set update_version=0.01
set first_run=0
set server_path=.\dart_env\Scripts\activate.bat
if not exist ".\dart_env\" (
  set first_run=1
  copy .env_sample .env
  python -m venv ".\dart_env" >> logs/start_dart.log
)

call %server_path% >> logs/start_dart.log

python -m pip install --upgrade pip

echo "Checking if update required"
Rem If this is not the first run and the dart version matches that in the start_dart.bat file skip updating.
if %first_run%==0 ( if %dart_version%==%update_version% goto start_server )

echo "Updating Python Libraries, this may take several minutes"
python -m pip install -r .\requirements.txt >> logs/start_dart.log

echo "Collecting static files, this may take a moment"
python .\manage.py collectstatic --noinput

:start_server
echo "Creating/Updating local database"
python .\manage.py migrate >> logs/start_dart.log

call server.bat
