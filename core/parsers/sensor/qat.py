import pandas as pd
import logging

from io import StringIO

from core.models import Mission

logger = logging.getLogger('dart')
logger_notifications = logging.getLogger('dart.user.qat')

class QATParser:

    def parse(self):
        data_frame = pd.read_csv(self.file, na_filter=False)


    def __init__(self, mission: Mission, file_name: str, file: StringIO):
        self.file_name = file_name
        self.file = file
        self.mission = mission