# Requirements
* Python 3.10+
* Git

# Installation
1. Before installation you must have Python 3.10 and [Git](https://git-scm.com/) installed.

## Windows
1. Open a windows file explorer and navigate to the directory you wish to install DART
1. In the address bar, where the current working directory is specified, type `cmd`
1. In the command window type `git clone http://github.com/upsonp/dart`
1. When the application has been checked out, type 'cd dart' to change to the dart project directory
1. Type start_dart.bat to start the application for the first time.

The first time running the application may take several minutes to start while python packages and the inital local database is created. When you see `Listening on TCP address 127.0.0.1:8000` in the command window, open a web browser and enter localhost:8000 in the address bar.

To stop the server, close the command window.

***NOTE:***  
If the application had issues installing the cx_Oracle package you'll have to install [Microsoft Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)

# Settings
The default settings do not require modification, but using the .env file you can change the name of the default database. Running the 'start_dart.bat' or 'update.bat' script will be required to recreate the database with the new name. 'update.bat' will run the updates without downloading DART application updates from the github repository

# Starting DART

After the initial setup the application can be started at any time by navigating to the dart directory and double clicking the 'start_dart.bat' file or 'server.bat' scripts. Using 'server.bat' instead of 'start_dart.bat' will skip the process of updating the application from git hub and will just start the webserver, at which point entering 'localhost:8000' in a web browser (Chrome or FireFox is prefered) will access the applications main page.
