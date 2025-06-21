import unittest
from unittest.mock import patch
from bs4 import BeautifulSoup
from config.components import modal, websocket_modal, completed

class TestModalFunctions(unittest.TestCase):
    @patch("config.components.render_to_string")
    def test_modal_default(self, mock_render):
        # Provide a minimal modal HTML structure
        mock_render.return_value = """
        <div>
            <div id="modalDialog">
                <div id="modalTitle"></div>
                <div id="modalContent"><div></div></div>
                <div id="modalProgressBar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
                    <div class="progress-bar-striped"></div>
                </div>
            </div>
        </div>
        """
        dialog = modal("Test Title")
        self.assertEqual(dialog.find(id="modalTitle").string, "Test Title")
        self.assertEqual(dialog.find(id="modalProgressBar")["aria-valuenow"], "0")
        self.assertIn("progress-bar-striped", dialog.find("div", class_="progress-bar-striped")["class"])

    @patch("config.components.render_to_string")
    def test_modal_success(self, mock_render):
        mock_render.return_value = """
        <div>
            <div id="modalDialog">
                <div id="modalTitle"></div>
                <div id="modalContent"><div></div></div>
                <div id="modalProgressBar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
                    <div class="progress-bar-striped"></div>
                </div>
            </div>
        </div>
        """
        dialog = modal("Done", completion=completed.success)
        sub_progress = dialog.find(id="modalProgressBar").find("div")
        self.assertIn("bg-success", sub_progress["class"])
        self.assertEqual(sub_progress.string, "100%")

    @patch("config.components.render_to_string")
    def test_modal_failure(self, mock_render):
        mock_render.return_value = """
        <div>
            <div id="modalDialog">
                <div id="modalTitle"></div>
                <div id="modalContent"><div></div></div>
                <div id="modalProgressBar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
                    <div class="progress-bar-striped"></div>
                </div>
            </div>
        </div>
        """
        dialog = modal("Failed", completion=completed.failure)
        sub_progress = dialog.find(id="modalProgressBar").find("div")
        self.assertIn("bg-danger", sub_progress["class"])
        self.assertEqual(sub_progress.string, "")

    @patch("config.components.render_to_string")
    def test_modal_swap_oob(self, mock_render):
        mock_render.return_value = """
        <div>
            <div id="modalDialog">
                <div id="modalTitle"></div>
                <div id="modalContent"><div></div></div>
                <div id="modalProgressBar"><div class="progress-bar-striped"></div></div>
            </div>
        </div>
        """
        dialog = modal("Swap OOB", swap_oob=True)
        self.assertEqual(dialog.attrs.get("hx-swap-oob"), "true")

    @patch("config.components.render_to_string")
    def test_websocket_modal(self, mock_render):
        mock_render.return_value = """
        <div>
            <div id="modalDialog">
                <div id="modalTitle"></div>
            </div>
        </div>
        """
        dialog = websocket_modal("WS Title", "logger1", path="/some/path/")
        self.assertEqual(dialog["hx-swap-oob"], "true")
        self.assertEqual(dialog["hx-post"], "/some/path/")
        self.assertEqual(dialog["hx-trigger"], "load")
        self.assertEqual(dialog["hx-ext"], "ws")
        self.assertEqual(dialog["ws-connect"], "/ws/notification/logger1/")
        self.assertEqual(dialog.find(id="modalTitle").string, "WS Title")