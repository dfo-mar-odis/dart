import os
import logging

from bs4 import BeautifulSoup
from crispy_forms.bootstrap import StrictButton
from crispy_forms.layout import Column, Field, Row
from crispy_forms.utils import render_crispy_form

from django import forms
from django.conf import settings
from django.core.cache import caches
from django.db import connections
from django.http import HttpResponse
from django.template.context_processors import csrf
from django.urls import path, reverse_lazy
from django.utils.translation import gettext as _

import core.models
from core import forms as core_forms
from biochem import upload
from biochem import models as biochem_models

from dart.utils import load_svg

logger = logging.getLogger('dart')
user_logger = logger.getChild('user')

_page_limit = 50


def get_biochem_additional_button_id():
    return 'div_id_biochem_batch_button_area'


# This form is for after a user has connected to a Biochem database. It will query the database for a "BcBatches" tabel
# and if found will give the user the ablity to select and remove batches as well as view errors associated with a batch
class BiochemBatchForm(core_forms.CollapsableCardForm):
    selected_batch = forms.ChoiceField(required=False)

    # I had to override the default Bootstrap template for fields, because someone thought putting 'mb-3'
    # as a default for field wrappers was a good idea and it creates a massive gap under the inputs when
    # used in a card title
    field_template = os.path.join(settings.TEMPLATE_DIR, "field.html")

    class Meta:
        fields = ['selected_batch']

    @staticmethod
    def get_batch_alert_area_id():
        return f"div_id_biochem_batch_alert_area"

    @staticmethod
    def get_delete_batch_button_id():
        return 'btn_id_delete_batch'

    @staticmethod
    def get_card_content_id():
        return 'btn_id_batch_validate_content'

    @staticmethod
    def get_upload_button_id():
        return 'btn_id_batch_upload'

    @staticmethod
    def get_validate_stage1_button_id():
        return 'btn_id_batch_stage1_validate'

    @staticmethod
    def get_validate_stage2_button_id():
        return 'btn_id_batch_stage2_validate'

    def get_biochem_batch_upload_url(self):
        pass

    def get_biochem_batch_url(self):
        pass

    def get_biochem_batch_clear_url(self):
        pass

    def get_batch_select(self):
        url = self.get_biochem_batch_url()

        title_id = f"control_id_database_select_{self.card_name}"

        batch_select_attributes = {
            'id': title_id,
            'class': 'form-select form-select-sm mt-1',
            'name': 'selected_batch',
            'hx-get': url,
            'hx-trigger': 'change, reload_batch from:body'
        }
        batch_select = Column(
            Field('selected_batch', template=self.field_template, **batch_select_attributes,
                  wrapper_class="col-auto"),
            id=f"div_id_batch_select_{self.card_name}",
            css_class="col-auto"
        )

        return batch_select

    def get_upload_button(self):
        attrs = {
            'id': self.get_upload_button_id(),
            'title': _('Create and Upload New Batch'),
            'name': 'upload_batch',
            'hx-get': self.get_biochem_batch_upload_url(),
            'hx-swap': 'none'
        }

        icon = load_svg('arrow-up-square')
        validate_button = StrictButton(icon, css_class="btn btn-primary btn-sm", **attrs)
        return validate_button

    def get_validate_stage1_button(self):
        validate_attrs = {
            'id': self.get_validate_stage1_button_id(),
            'title': _('Run Batch Validation'),
            'name': 'validate_stage1_batch',
            'disabled': 'disabled',
            'hx-swap': 'none'
        }

        icon = load_svg('1-square')
        validate_button = StrictButton(icon, css_class="btn btn-primary btn-sm", **validate_attrs)
        return validate_button

    def get_validate_stage2_button(self):
        validate_attrs = {
            'id': self.get_validate_stage2_button_id(),
            'title': _('Run Batch Validation'),
            'name': 'validate_stage2_batch',
            'disabled': 'disabled',
            'hx-swap': 'none'
        }

        icon = load_svg('2-square')
        validate_button = StrictButton(icon, css_class="btn btn-primary btn-sm", **validate_attrs)
        return validate_button

    def get_delete_button(self):
        attrs = {
            'id': self.get_delete_batch_button_id(),
            'title': _('Delete Batch'),
            'name': 'delete_batch',
            'disabled': 'disabled',
            'hx-swap': 'none',
            'hx-confirm': _("Are you Sure?")
        }

        icon = load_svg('dash-square')
        button = StrictButton(icon, css_class="btn btn-danger btn-sm", **attrs)
        return button

    def get_alert_area(self):
        msg_row = Row(id=self.get_batch_alert_area_id())
        return msg_row

    def get_card_header(self):
        header = super().get_card_header()

        header.fields[0].fields.append(self.get_batch_select())
        header.fields[0].fields.append(Column(Row()))  # Spacer column to align buttons to the right

        header.fields[0].fields.append(btn_col := Column(id=get_biochem_additional_button_id(), css_class="col-auto"))
        btn_col.fields.append(self.get_upload_button())
        btn_col.fields.append(self.get_validate_stage1_button())
        btn_col.fields.append(self.get_validate_stage2_button())
        btn_col.fields.append(self.get_delete_button())

        header.fields.append(self.get_alert_area())
        return header

    def get_card_body(self):
        body = super().get_card_body()

        attrs = {
            'hx_get': self.get_biochem_batch_clear_url(),
            'hx_swap': 'innerHTML',
            'hx_trigger': 'load, clear_batch from:body'
        }
        input_row = Row(
            Column(
                id=self.get_card_content_id(),
                **attrs
            ),
            #css_class="vertical-scrollbar",
        )
        body.append(input_row)

        return body

    # this can be overridden by an implementing class to be more specific about what batches it retrieves.
    def get_batch_choices(self):
        mission = core.models.Mission.objects.using(self.database).get(pk=self.mission_id)

        # only get batch ids that match the mission descriptor
        batches = biochem_models.Bcbatches.objects.using('biochem').filter(
            name=mission.mission_descriptor
        ).order_by('-batch_seq')
        self.fields['selected_batch'].choices += [(db.batch_seq, f"{db.batch_seq}: {db.name}") for db in batches]

    # at a minimum a mission_id and what happens when the upload button are pressed must be supplied in
    def __init__(self, *args, database, mission_id, **kwargs):
        self.database = database
        self.mission_id = mission_id

        super().__init__(*args, **kwargs, card_name="biochem_batch_details", card_title=_("Biochem Batches"))

        self.fields['selected_batch'].label = False
        self.fields['selected_batch'].choices = [(None, '------')]

        database_id = caches['biochem_keys'].get('database_id', default=None)
        password = caches['biochem_keys'].get('pwd', version=database_id, default=None)
        if not database_id or not password:
            return

        self.get_batch_choices()


def get_table_soup(title, html_id, headers, swap_oob=True):
    soup = BeautifulSoup('', 'html.parser')

    soup.append(div := soup.new_tag('div'))
    div.attrs['class'] = 'mt-2 border border-dark'
    div.attrs['id'] = html_id

    div.append(div_title := soup.new_tag('div'))
    div_title.attrs['class'] = 'ms-2 h4'
    div_title.string = title

    div_title.append(div_spinner := soup.new_tag('div'))
    div_spinner.attrs['id'] = f'{html_id}_spinner'
    div_spinner.attrs['role'] = 'status'

    div.append(div_table := soup.new_tag('div'))
    div_table.attrs['class'] = 'tscroll horizontal-scrollbar vertical-scrollbar-sm'

    if swap_oob:
        div.attrs['hx-swap-oob'] = "true"

    div_table.append(table := soup.new_tag('table'))
    table.attrs['class'] = 'dataframe table table-striped table-sm'

    table.append(table_head := soup.new_tag('thead'))
    table_head.attrs['id'] = f'{html_id}_thead'

    table_head.append(tr_header := soup.new_tag('tr'))
    for header in headers:
        tr_header.append(th := soup.new_tag('th'))
        th.string = header

    table.append(table_body := soup.new_tag('tbody'))
    table_body.attrs['id'] = f'{html_id}_tbody'
    return soup


def generic_table_paging(request, batch_id, page, table_id, table_page_func):
    soup = BeautifulSoup('', 'html.parser')
    spinner = soup.new_tag('div')

    spinner.attrs['id'] = f'{table_id}_spinner'
    spinner.attrs['role'] = 'status'
    spinner.attrs['hx-swap-oob'] = "true"

    if 'done' in request.GET:
        spinner.attrs['class'] = ''
    elif 'next' not in request.GET:
        url = request.path + '?next=true'
        spinner.attrs['class'] = 'spinner-border spinner-border-sm ms-2'
        spinner.attrs['hx-get'] = url
        spinner.attrs['hx-trigger'] = 'load'
        spinner.attrs['hx-target'] = f'#{table_id}_tbody'
        spinner.attrs['hx-swap'] = 'beforeend'
    else:
        url = request.path + '?done=true'
        table_soup = table_page_func(batch_id, page)
        first_tr = table_soup.find('tbody').find('tr')
        first_tr.attrs['hx-get'] = url
        first_tr.attrs['hx-trigger'] = 'load'
        first_tr.attrs['hx-swap'] = 'none'
        return HttpResponse(table_soup.find('tbody').findAll('tr', recursive=False))

    soup.append(spinner)
    return HttpResponse(soup)
