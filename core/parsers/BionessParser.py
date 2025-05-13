import logging
import numpy as np
from django.db import IntegrityError

from pandas import DataFrame

from django.utils.translation import gettext as _
from django.db.models import QuerySet

from core import models as core_models
from core.parsers import parser_utils

from settingsdb.models import FileConfiguration

logger = logging.getLogger('dart')
user_logger = logging.getLogger('dart.user')


def get_or_create_file_config() -> QuerySet[FileConfiguration]:
    file_type = 'phytoplankton'
    fields = [("Comment", "COMMENT", _("Label identifying the Comment line")),  # Optional
              ("Event #", "EVENT", _("Label identifying the Event ID line")),  # Required, this is how the file is matched to an event
              ]

    return parser_utils._get_or_create_file_config(file_type, fields)

def parse_bioness(mission: core_models.Mission, file):
    pass