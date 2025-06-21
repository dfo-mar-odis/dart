import os
import shutil
import tempfile
import unittest

from django.conf import settings

from config import utils

class TestUtils(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_name = "TEST_DB"
        self.db_path = os.path.join(self.tmp_dir, f"{self.db_name}.sqlite3")
        self._orig_db_dir = getattr(settings, "BASE_DIR", None)
        settings.BASE_DIR = self.tmp_dir

    def tearDown(self):
        if 'dart_active' in settings.DATABASES:
            del settings.DATABASES['dart_active']

        shutil.rmtree(self.tmp_dir)
        if self._orig_db_dir is not None:
            settings.BASE_DIR = self._orig_db_dir


    def test_create_database(self):
        conn = utils.create_database(self.db_name, db_dir=self.tmp_dir)
        self.assertTrue(os.path.isfile(self.db_path))
        self.assertIsNotNone(conn)

    def test_create_database_exists(self):
        utils.create_database(self.db_name, db_dir=self.tmp_dir)
        with self.assertRaises(FileExistsError):
            utils.create_database(self.db_name, db_dir=self.tmp_dir)

    def test_connect_database(self):
        utils.create_database(self.db_name, db_dir=self.tmp_dir)
        conn = utils.connect_database(self.db_name, db_dir=self.tmp_dir)
        self.assertIsNotNone(conn)

    def test_connect_database_not_found(self):
        with self.assertRaises(FileNotFoundError):
            utils.connect_database("MISSING_DB", db_dir=self.tmp_dir)

    def test_load_svg(self):
        icons_dir = os.path.join(self.tmp_dir, "icons")
        os.makedirs(icons_dir)
        svg_name = "test_icon"
        svg_path = os.path.join(icons_dir, f"{svg_name}.svg")
        with open(svg_path, "w") as f:
            f.write("<svg></svg>")
        settings.STATIC_ROOT = self.tmp_dir
        settings.BS_ICONS_CUSTOM_PATH = "icons"
        result = utils.load_svg(svg_name)
        self.assertIn("<svg>", result)
