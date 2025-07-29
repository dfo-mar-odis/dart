import sys
import logging
import threading
import html

from daphne.cli import CommandLineInterface

from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QTextEdit, QLabel
from PyQt6.QtCore import QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QIcon

from django.core.management.base import BaseCommand
from django.conf import settings

logger = logging.getLogger('dart')

server_port = 8001


class ServerThread(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True

    def run(self):
        try:
            sys.argv = ['daphne', 'config.asgi:application', '--bind', '127.0.0.1', '--port', str(server_port)]
            CommandLineInterface.entrypoint()
        except Exception as e:
            logger.error(f"Server failed to start: {e}")

class Command(BaseCommand):

    help = "Runs Dart as a standalone application with log console"

    def handle(self, *args, **options):
        app = QApplication([])
        app.setQuitOnLastWindowClosed(False)
        settings.app = app

        logger.info("DART Application initializing...")

        # Start server thread
        thread = ServerThread()
        thread.start()

        logger.info("Starting web server...")
        # Wait for the server to start
        while not thread.is_alive():
            QThread.msleep(100)  # Sleep for 100ms to avoid busy-waiting

        logger.info("Attaching application to server")

        try:
            app.exec()
        finally:
            print("Application closing...")