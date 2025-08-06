import sys
import logging
import threading

from daphne.cli import CommandLineInterface

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QThread, QTimer

from django.core.management.base import BaseCommand
from django.conf import settings

logger = logging.getLogger('dart')

server_port = 8001


class ServerThread(threading.Thread):
    host = None
    port = None

    def __init__(self, host='127.0.0.1', port=8000):
        self.host = host
        self.port = port

        super().__init__()
        self.daemon = True

    def run(self):
        try:
            sys.argv = ['daphne', 'config.asgi:application', '--bind', self.host, '--port', str(self.port)]
            CommandLineInterface.entrypoint()
        except Exception as e:
            logger.error(f"Server failed to start: {e}")

class Command(BaseCommand):

    help = "Runs Dart as a standalone application with log console"

    def add_arguments(self, parser):
        parser.add_argument('--host', type=str, default='127.0.0.1', help='Host to bind the Django webserver to')
        parser.add_argument('-p', '--port', type=int, default=8000, help='Port to bind the server to')

    def handle(self, *args, **options):
        host = options['host']
        port = options['port']

        app = QApplication([])
        app.setQuitOnLastWindowClosed(False)
        settings.app = app

        logger.info("DART Application initializing...")

        # Start server thread
        thread = ServerThread(host, port)
        thread.start()

        logger.info("Starting web server...")
        # Wait for the server to start
        while not thread.is_alive():
            QThread.msleep(100)  # Sleep for 100ms to avoid busy-waiting

        logger.info("Attaching application to server")

        # Use QTimer to periodically check for signals
        def check_for_exit():
            if threading.main_thread().is_alive() is False:
                app.quit()

        timer = QTimer()
        timer.timeout.connect(check_for_exit)
        timer.start(100)  # Check every 100ms

        try:
            app.exec()
        finally:
            print("Application closing...")