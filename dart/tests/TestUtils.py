from .DartTestCase import DartTestCase

from dart import utils

import logging

logger = logging.getLogger('dart.test')


class TestUtils(DartTestCase):

    def test_load_svg(self):
        icon = utils.load_svg('bell')

        self.assertIsNotNone(icon)


