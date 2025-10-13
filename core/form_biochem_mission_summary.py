import os
import logging

from crispy_forms.utils import render_crispy_form
from django.db.models import QuerySet

import django.db.utils
from crispy_forms.layout import Column, Field, Row

from django import forms
from django.conf import settings
from django.http import HttpResponse
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _

from core import models as core_models
from core import forms as core_forms
from core import form_biochem_database
from biochem import models as biochem_models

from config.utils import load_svg

logger = logging.getLogger('dart')
user_logger = logger.getChild('user')

_page_limit = 50

card_name = "biochem_mission_summary"


# This form is for after a user has connected to a Biochem database. It will query the database for a "BcBatches" tabel
# and if found will give the user the ablity to select and remove batches as well as view errors associated with a batch
class BiochemMissionSummaryForm(core_forms.CollapsableCardForm):
    selected_mission = forms.ChoiceField(required=False)

    # I had to override the default Bootstrap template for fields, because someone thought putting 'mb-3'
    # as a default for field wrappers was a good idea and it creates a massive gap under the inputs when
    # used in a card title
    field_template = os.path.join(settings.TEMPLATE_DIR, "field.html")

    class BiochemMissionSummaryIdBuilder(core_forms.CollapsableCardForm.CollapsableCardIDBuilder):

        def get_batch_select_id(self):
            return f"control_id_database_select_{self.card_name}"

        def get_card_content_id(self):
            return f"div_id_summary_{self.card_name}"

        def get_batch_alert_area_id(self):
            return f"div_id_alert_area_{self.card_name}"

        def get_biochem_additional_button_id(self):
            return 'div_id_biochem_batch_button_area'

    @staticmethod
    def get_id_builder_class():
        return BiochemMissionSummaryForm.BiochemMissionSummaryIdBuilder


    class Meta:
        fields = ['selected_mission']

    def get_mission_select(self, init=False):

        batch_select_attributes = {
            'id': self.get_id_builder().get_batch_select_id(),
            'class': 'form-select form-select-sm mt-1',
            'name': 'selected_mission',
            'hx-swap': 'outerHTML'
        }
        if init:
            batch_select_attributes['hx-trigger'] = 'load, change'
            load_more_url = reverse_lazy("core:load_more_missions", kwargs={'page': 1})

        mission_select = Column(
            Field(
                'selected_mission', template=self.field_template,
                wrapper_class="col-auto",
                **batch_select_attributes,
                hx_get=f"{load_more_url}"
            ),
            id=f"div_id_batch_select_{self.card_name}",
            css_class="col-auto"
        )

        return mission_select

    def get_alert_area(self):
        msg_row = Row(id=self.get_id_builder().get_batch_alert_area_id())
        return msg_row

    def get_clear_body_url(self):
        return reverse_lazy("core:form_biochem_mission_summary_clear_summary")

    def get_card_header(self):
        header = super().get_card_header()

        header.fields[0].fields.append(self.get_mission_select(True))
        header.fields[0].fields.append(Column(Row()))  # Spacer column to align buttons to the right

        header.fields[0].fields.append(btn_col := Column(id=self.get_id_builder().get_biochem_additional_button_id(), css_class="col-auto"))

        # Add right aligned buttons here
        # btn_col.fields.append(self.get_download_button())

        header.fields.append(self.get_alert_area())
        return header

    def get_card_body(self):
        body = super().get_card_body()

        attrs = {
            'hx_get': self.get_clear_body_url(),
            'hx_swap': 'innerHTML',
            'hx_trigger': 'load, clear_batch from:body'
        }
        input_row = Row(
            Column(
                id=self.get_id_builder().get_card_content_id(),
                **attrs
            ),
        )
        body.append(input_row)

        return body

    # this can be overridden by an implementing class to be more specific about what batches it retrieves.
    def get_batch_choices(self, page=1, limit=20):
        offset = (page - 1) * limit
        missions = biochem_models.Bcmissions.objects.using('biochem')\
            .order_by('-start_date')[offset:offset+limit]

        choices = [(db.mission_seq, f"{db.name}: {db.descriptor}") for db in missions]

        # For initial page, reset choices first
        if page == 1:
            self.fields['selected_mission'].choices = [(None, "--- Select Mission ---")]

        self.fields['selected_mission'].choices += choices

        # Return if there are more results
        total = biochem_models.Bcmissions.objects.using('biochem').count()
        return offset + len(choices) < total

    # at a minimum a mission_id and what happens when the upload button are pressed must be supplied in
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, card_name=card_name, card_title=_("Biochem Mission Summary"))

        self.fields['selected_mission'].choices = [(None, "--- Select Mission ---")]


def get_summary_card(request, mission_id):
    form = BiochemMissionSummaryForm()

    return HttpResponse(render_crispy_form(form))


def load_more_missions(request, page=1):
    form = BiochemMissionSummaryForm()
    has_more = form.get_batch_choices(page=page)

    # Create select element with updated options
    options_html = ""
    for value, label in form.fields['selected_mission'].choices:
        options_html += f"<option value='{value}'>{label}</option>"

    last_url = None
    next_url = None

    # If there are more results, add load more option
    if page > 1:
        last_page = page - 1
        last_url = reverse_lazy("core:load_more_missions", kwargs={'mission_id': mission_id, 'page': last_page})
        options_html = f'<option value="previous_bc_options" hx-get="{last_url}" hx-swap="outerHTML" hx-target="this">Previous options...</option>' + options_html

    if has_more:
        next_page = page + 1
        next_url = reverse_lazy("core:load_more_missions", kwargs={'mission_id': mission_id, 'page': next_page})
        options_html += f'<option value="next_bc_options" hx-get="{next_url}" hx-swap="outerHTML" hx-target="this">Load more...</option>'

    select_html = f"""<select name="selected_mission" 
    id="control_id_database_select_biochem_mission_summary"
    class="form-select form-select-sm mt-1" 
    hx-swap="outerHTML" """

    if last_url:
        select_html += f"""
        hx-trigger="change[target.value=='previous_bc_options']" 
        hx-get="{last_url}"
        """
    if next_url:
        select_html += f"""
        hx-trigger="change[target.value=='next_bc_options']" 
        hx-get="{next_url}"
        """
    select_html += f""">
    {options_html}
    </select>"""
    return HttpResponse(select_html)


def clear_summary(request):
    return HttpResponse()


urlpatterns = [
    path('/biochem/clear_summary/', get_summary_card, name='form_biochem_mission_summary'),

    path('/biochem/load_more_missions/<int:page>/', load_more_missions, name='load_more_missions'),
    path('biochem/clear_summary/', clear_summary, name='form_biochem_mission_summary_clear_summary'),
]
