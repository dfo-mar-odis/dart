# Notes
I started 4.2.x as a complete rewrite for Dart that didn't use Crispy forms and had planed on porting over the logic 
while just rewriting the interface. As Dart developed into 4.1.x I realized there were far too many ways to work with 
HTML and it would be a headache for anyone comming in that was new to the project to figure out what method to use and 
when. This version of Dart does have a better way of interacting with local SQL database and the project is better 
organized based on lessons learned, but as I've been working with it I realize how much crispy forms actually does in 
terms of validation. It adds complexity, and HTML templates are easier to read, but the extra work required to handle 
validation, labels, passing variables to the templates and how unreadale the templates become anyway with Django 
templating statements is a headache as well. It's better to use crispy forms. 

So I'm putting this version on the back burner.

Some of the things I'd like to take from this 4.2.x and incorporate into 4.1.x are the DB handling, with the middleware 
that checks what DB the user is connected to. At the moment in 4.1.x if a user opens one mission, then opens another in 
another tab and makes changes, then switches back to the first tab to make changes to the first mission they can 
override/corrupt the second mission's database. The config.middleware.py module fixes the issue by checking the user 
is connected to the database specified in the URL before letting them update data so switching between multiple 
missions in multiple tabs is fine.

I'd also like to include a modal dialog for websocket communications instead of having a notification area in the
title of cards that have interactive features.

# Requirements
* Python 3.13+
* Git
* C++ Visual Build Tools - required for oracle connections

# Installation
1. Before installation you must have Python 3.13 and [Git](https://git-scm.com/) installed.
2. If you have a python version of between 3.10 and 3.12 you will requier Dart in the 4.0.x branch instead of this version. You can check your python verion by opening a command window and typing `python -V`

## Windows
1. Open a windows file explorer and navigate to the directory you wish to install DART
1. In the address bar, where the current working directory is specified, type `cmd`
1. In the command window type `git -b 4.1.x clone https://github.com/dfo-mar-odis/dart`
1. When the application has been checked out, type 'cd dart' to change to the dart project directory
1. Type `start_dart.bat` to start the application for the first time.

The first time running the application may take several minutes to start while python packages and the initial local database is created. When you see `Listening on TCP address 127.0.0.1:8000` in the command window, open a web browser and enter localhost:8000 in the address bar.

***NOTE:***  
If the application had issues installing the cx_Oracle package you'll have to install [Microsoft Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/), which can also be installed from the DFO software center.

You'll also need to install Oracle Instant Client, from the DFO software center.

To stop the server, close the command window.

# Starting DART

The initial setup of the application should be run using the `start_dart.bat` file. After which the Dart server can be started at any time by navigating to the dart directory and double clicking the 'start_dart.bat' file or 'server.bat' scripts.

`start_dart.bat` is an update script that will download any new updates for the application from the github location. It then calls the `update.bat` script to install python packages, initialize the local database, if it doesn't already exist, and populate default tables with the standard Dart fixtures.

`server.bat` will skip the process of updating the application from git hub and will start the webserver in its current state, at which point entering 'localhost:8000' in a web browser (Chrome or FireFox are preferred) will access the applications main page.
