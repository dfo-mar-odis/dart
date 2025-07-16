from bs4 import BeautifulSoup

from crispy_forms.utils import render_crispy_form

from django.http import HttpResponse
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _

from core import views, models, forms
from core.form_mission_sample_type import BioChemDataType, MissionSampleTypeFilter

from config.views import GenericDetailView
from settingsdb import models as settingsdb_models


class SampleTypeDetails(GenericDetailView):
    model = models.MissionSampleType
    page_title = _("Sample Type")
    template_name = "core/mission_sample_type.html"

    def get_page_title(self):
        return _("Mission Sample Type") + f" : {self.object.mission.name} - {self.object.name}"

    def get_settings_url(self):
        return reverse_lazy("core:mission_edit", args=(self.object.pk,))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['mission_sample_type'] = self.object
        data_type_seq = self.object.datatype

        database = self.kwargs['database']
        initial = {'sample_type_id': self.object.id, 'mission_id': self.object.mission.id}
        if data_type_seq:
            initial['data_type_code'] = data_type_seq.data_type_seq

        context['biochem_form'] = BioChemDataType(mission_sample_type=self.object)
        context['filter_form'] = MissionSampleTypeFilter(mission_sample_type=self.object)

        context['reports'] = {key: reverse_lazy(views.reports[key], args=(database, self.object.mission.pk,)) for key in
                              views.reports.keys()}

        return context


def sample_type_card(request, sample_type_id):
    mission_sample_type = models.MissionSampleType.objects.get(pk=sample_type_id)

    sample_type_form = forms.CardForm(card_title=str(mission_sample_type), card_name="mission_sample_type")
    sample_type_html = render_crispy_form(sample_type_form)
    sample_type_soup = BeautifulSoup(sample_type_html, 'html.parser')

    card_body_div = sample_type_soup.find(id=sample_type_form.get_card_body_id())

    form_soup = BeautifulSoup(f'<div id="div_id_{sample_type_form.get_card_name()}"></div>', 'html.parser')
    form = form_soup.find('div')
    form.attrs['hx-swap-oob'] = "true"
    form.append(sample_type_soup)

    return HttpResponse(form_soup)


def delete_config(request, config_id):

    settingsdb_models.SampleTypeConfig.objects.get(pk=config_id).delete()
    return HttpResponse()

# ###### Mission Sample ###### #
mission_sample_type_urls = [
    path(f'<str:database>/sampletype/<int:pk>/', SampleTypeDetails.as_view(), name="mission_sample_type_details"),

    path(f'sampletype/card/<int:sample_type_id>/', sample_type_card, name="mission_sample_type_card"),
    path(f'sampletype/config/<int:config_id>/', delete_config, name="mission_sample_type_delete_config"),

]
