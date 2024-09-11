# Requirements
* Python 3.10+
* Git
* C++ Visual Build Tools - required for oracle connections

# Installation
1. Before installation you must have Python 3.10 and [Git](https://git-scm.com/) installed.

## Windows
1. Open a windows file explorer and navigate to the directory you wish to install DART
1. In the address bar, where the current working directory is specified, type `cmd`
1. In the command window type `git clone https://github.com/dfo-mar-odis/dart`
1. When the application has been checked out, type 'cd dart' to change to the dart project directory
1. Type `start_dart.bat` to start the application for the first time.

The first time running the application may take several minutes to start while python packages and the initial local database is created. When you see `Listening on TCP address 127.0.0.1:8000` in the command window, open a web browser and enter localhost:8000 in the address bar.

***NOTE:***  
If the application had issues installing the cx_Oracle package you'll have to install [Microsoft Build Tools](https://visualstudio.microsoft.com/downloads/)

To stop the server, close the command window.

# Starting DART

The initial setup of the application should be run using the `start_dart.bat` file. After which the Dart server can be started at any time by navigating to the dart directory and double clicking the 'start_dart.bat' file or 'server.bat' scripts.

`start_dart.bat` is an update script that will download any new updates for the application from the github location. It then calls the `update.bat` script to install python packages, initialize the local database, if it doesn't already exist, and populate default tables with the standard Dart fixtures.

`server.bat` will skip the process of updating the application from git hub and will start the webserver in its current state, at which point entering 'localhost:8000' in a web browser (Chrome or FireFox are preferred) will access the applications main page.
