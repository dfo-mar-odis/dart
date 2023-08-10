from .DartTestCase import DartTestCase

from dart2 import utils


class TestUtils(DartTestCase):

    def test_load_svg(self):
        icon = utils.load_svg('bell')

        self.assertIsNotNone(icon)