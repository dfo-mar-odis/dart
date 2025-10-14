import os
import logging

from crispy_forms.utils import render_crispy_form

from crispy_forms.layout import Row

from django.http import HttpResponse
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _

from core import forms as core_forms, form_biochem_database

logger = logging.getLogger('dart')
user_logger = logger.getChild('user')

_page_limit = 50

card_name = "biochem_mission_summary"


# This form is for after a user has connected to a Biochem database. It will query the database for a "BcBatches" tabel
# and if found will give the user the ablity to select and remove batches as well as view errors associated with a batch
class BiochemMissionSummaryForm(core_forms.CardForm):
    class BiochemMissionSummaryIdBuilder(core_forms.CardForm.CardFormIdBuilder):
        pass

    @staticmethod
    def get_id_builder_class():
        return BiochemMissionSummaryForm.BiochemMissionSummaryIdBuilder

    class Meta:
        pass
        # fields = ['selected_mission']

    def get_card_body(self):
        body = super().get_card_body()

        return body

    def __init__(self, *args, **kwargs):
        super().__init__(*args, card_name="mission_summary", card_title=_("Mission Selection"), **kwargs)


def get_summary_card(request):
    form = BiochemMissionSummaryForm()

    form.get_alert_area().set_status("danger").set_message(_("No Connected Database"))

    return HttpResponse(render_crispy_form(form))


urlpatterns = [
    path('biochem/clear_summary/', get_summary_card, name='form_biochem_mission_summary'),
]
