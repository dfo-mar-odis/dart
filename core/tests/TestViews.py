from core import models as core_models
from core.tests import CoreFactoryFloor

from dart2.tests.DartTestCase import DartTestCase

from django.test import tag, Client

import logging

logger = logging.getLogger('dart.test')
