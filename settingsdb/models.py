from django.db import models
from django.utils.translation import gettext_lazy as _


class LocalSetting(models.Model):
    
    database_location = models.FilePathField(verbose_name=_("Mission Database(s) Path"), default="./missions",
                                             help_text=_("Location of individual mission databases"))
