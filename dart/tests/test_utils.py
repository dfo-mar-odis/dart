import unittest
from django.test import TestCase, tag
from dart.utils import distance, is_locked, is_integer_string
from unittest.mock import patch

@tag('utils')
class TestDistanceFunction(TestCase):
    def test_zero_distance(self):
        # Same point
        self.assertAlmostEqual(distance([0, 0], [0, 0]), 0.0, places=6)

    def test_known_distance(self):
        # London (51.5074, -0.1278) to Paris (48.8566, 2.3522) ~343 km
        d = distance([51.5074, -0.1278], [48.8566, 2.3522])
        self.assertAlmostEqual(d, 343, delta=2)

    def test_antipodal_points(self):
        # Opposite sides of the globe, should be about half Earth's circumference
        d = distance([0, 0], [0, 180])
        self.assertAlmostEqual(d, 20015, delta=10)

    def test_symmetry(self):
        # Distance should be the same regardless of order
        a = [34.05, -118.25]  # Los Angeles
        b = [40.7128, -74.0060]  # New York
        self.assertAlmostEqual(distance(a, b), distance(b, a), places=6)


class TestIsLocked(unittest.TestCase):
    @patch("os.path.exists")
    @patch("os.rename")
    def test_file_not_exists(self, mock_rename, mock_exists):
        mock_exists.return_value = False
        self.assertFalse(is_locked("dummy.txt"))
        mock_rename.assert_not_called()

    @patch("os.path.exists")
    @patch("os.rename")
    def test_file_exists_and_not_locked(self, mock_rename, mock_exists):
        mock_exists.return_value = True
        mock_rename.return_value = None
        self.assertFalse(is_locked("dummy.txt"))
        mock_rename.assert_called_once_with("dummy.txt", "dummy.txt")

    @patch("os.path.exists")
    @patch("os.rename", side_effect=OSError)
    def test_file_exists_and_locked(self, mock_rename, mock_exists):
        mock_exists.return_value = True
        self.assertTrue(is_locked("dummy.txt"))
        mock_rename.assert_called_once_with("dummy.txt", "dummy.txt")

class TestIsIntegerString(unittest.TestCase):
    def test_valid_integer_strings(self):
        self.assertTrue(is_integer_string("123"))
        self.assertTrue(is_integer_string("-456"))
        self.assertTrue(is_integer_string("0"))

    def test_invalid_integer_strings(self):
        self.assertFalse(is_integer_string("12.3"))
        self.assertFalse(is_integer_string("abc"))
        self.assertFalse(is_integer_string("123abc"))
        self.assertFalse(is_integer_string(""))

    def test_whitespace(self):
        self.assertTrue(is_integer_string("  42  "))
        self.assertFalse(is_integer_string("  "))

    def test_plus_sign(self):
        self.assertTrue(is_integer_string("+7"))