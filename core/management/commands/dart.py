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

class StdoutRedirect:
    """Redirects stdout/stderr to Qt signal"""

    def __init__(self, signal_emitter, stream_type):
        self.signal_emitter = signal_emitter
        self.stream_type = stream_type
        self.original_stream = sys.stdout if stream_type == 'stdout' else sys.stderr

    def write(self, text):
        # Send to Qt widget
        if text.strip():  # Only emit non-empty strings
            self.signal_emitter.output_signal.emit(text, self.stream_type)

        # Also write to original stream for debugging if needed
        self.original_stream.write(text)

    def flush(self):
        self.original_stream.flush()

class OutputSignalEmitter(QThread):
    """Signal emitter for thread-safe output to Qt widgets"""
    output_signal = pyqtSignal(str, str)  # text, stream_type

class DartMainWindow(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle('DFO At-sea Reporting Template - Console')
        self.setGeometry(100, 100, 800, 600)

        # Set the application icon
        self.setWindowIcon(QIcon('staticfiles/dart/icons/dart-light.ico'))

        self.setup_ui()
        self.setup_output_redirection()

    def setup_ui(self):
        layout = QVBoxLayout()

        # Status label
        self.status_label = QLabel("Server Status: Starting...")
        self.status_label.setStyleSheet("font-weight: bold; padding: 10px;")
        layout.addWidget(self.status_label)

        # Log console
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setFont(QFont("Consolas", 9))
        self.log_console.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #555;
            }
        """)
        layout.addWidget(self.log_console)

        self.setLayout(layout)

    def setup_output_redirection(self):
        # Create signal emitter
        self.signal_emitter = OutputSignalEmitter()
        self.signal_emitter.output_signal.connect(self.append_output)

        # Create redirectors
        self.stdout_redirect = StdoutRedirect(self.signal_emitter, 'stdout')
        self.stderr_redirect = StdoutRedirect(self.signal_emitter, 'stderr')

        # Redirect stdout and stderr
        sys.stdout = self.stdout_redirect
        sys.stderr = self.stderr_redirect

        # Update status periodically
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(5000)  # Update every 5 seconds

    def append_output(self, text, stream_type):
        # Color code by stream type
        color = '#ff4444' if stream_type == 'stderr' else '#ffffff'

        # Escape HTML and preserve formatting
        safe_text = html.escape(text.rstrip())
        formatted_text = f'<span style="color: {color}">{safe_text}</span>'

        self.log_console.append(formatted_text)

        # Auto-scroll to bottom
        scrollbar = self.log_console.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

        # Limit console size to prevent memory issues
        if self.log_console.document().blockCount() > 1000:
            cursor = self.log_console.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.movePosition(cursor.MoveOperation.Down, cursor.MoveMode.KeepAnchor, 100)
            cursor.removeSelectedText()

    def update_status(self):
        # Check if server thread is alive
        if hasattr(self, 'server_thread') and self.server_thread.is_alive():
            self.status_label.setText(f"Server Status: Running on http://localhost:{server_port}/")
            self.status_label.setStyleSheet("color: green; font-weight: bold; padding: 10px;")
        else:
            self.status_label.setText("Server Status: Not Running")
            self.status_label.setStyleSheet("color: red; font-weight: bold; padding: 10px;")

    def closeEvent(self, event):
        # Restore original stdout/stderr when closing
        sys.stdout = self.stdout_redirect.original_stream
        sys.stderr = self.stderr_redirect.original_stream
        event.accept()

class Serverthread(threading.Thread):
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
        logger.info("DART Application initializing...")

        window = DartMainWindow()

        # Start server thread
        thread = Serverthread()
        window.server_thread = thread  # Store reference for status checking
        thread.start()

        logger.info("Starting web server...")
        # Wait for the server to start
        while not thread.is_alive():
            QThread.msleep(100)  # Sleep for 100ms to avoid busy-waiting

        logger.info("Attaching application to server")
        settings.app = app
        window.show()

        try:
            app.exec()
        finally:
            print("Application closing...")