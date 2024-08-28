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
from django.urls import reverse_lazy
from django.utils.translation import gettext as _

import core.models
from core import forms as core_forms
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
            'hx-swap': 'none',
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
    def __init__(self, *args, database, mission_id, batch_id=None, **kwargs):
        self.database = database
        self.mission_id = mission_id
        self.batch_id = batch_id if batch_id else 0
        super().__init__(*args, **kwargs, card_name="biochem_batch_details", card_title=_("Biochem Batches"))

        if batch_id:
            self.initial['selected_batch'] = batch_id

        self.fields['selected_batch'].label = False
        self.fields['selected_batch'].choices = [(None, '--- NEW ---')]

        database_id = caches['biochem_keys'].get('database_id', default=None)
        password = caches['biochem_keys'].get('pwd', version=database_id, default=None)
        if not database_id or not password:
            return

        self.get_batch_choices()


def get_delete_button(soup):
    icon = BeautifulSoup(load_svg('dash-square'), 'html.parser').svg
    button = soup.new_tag('button')
    button.append(icon)
    button.attrs['id'] = BiochemBatchForm.get_delete_batch_button_id()
    button.attrs['class'] = 'btn btn-sm btn-danger'
    button.attrs['title'] = _("Delete Batch")
    button.attrs['hx-swap'] = 'none'
    button.attrs['hx-swap-oob'] = 'true'
    button.attrs['hx-confirm'] = _("Are you sure?")

    return button


def get_upload_button(soup):
    icon = BeautifulSoup(load_svg('arrow-up-square'), 'html.parser').svg
    button = soup.new_tag('button')
    button.append(icon)
    button.attrs['id'] = BiochemBatchForm.get_upload_button_id()
    button.attrs['class'] = 'btn btn-sm btn-primary'
    button.attrs['title'] = _('Create and Upload New Batch')
    button.attrs['hx-swap'] = 'none'
    button.attrs['hx-swap-oob'] = 'true'

    return button


def get_stage1_button(soup):
    icon = BeautifulSoup(load_svg('1-square'), 'html.parser').svg
    button = soup.new_tag('button')
    button.append(icon)
    button.attrs['id'] = BiochemBatchForm.get_validate_stage1_button_id()
    button.attrs['class'] = 'btn btn-sm btn-primary'
    button.attrs['title'] = _("Validate Stage 1")
    button.attrs['hx-swap'] = 'none'
    button.attrs['hx-swap-oob'] = 'true'

    return button


def get_stage2_button(soup):
    icon = BeautifulSoup(load_svg('2-square'), 'html.parser').svg
    button = soup.new_tag('button')
    button.append(icon)
    button.attrs['id'] = BiochemBatchForm.get_validate_stage2_button_id()
    button.attrs['class'] = 'btn btn-sm btn-primary'
    button.attrs['title'] = _("Validate Stage 2")
    button.attrs['hx-swap'] = 'none'
    button.attrs['hx-swap-oob'] = 'true'

    return button


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


def get_batches_form(request, batches_form_crispy, form_url):
    context = {}
    context.update(csrf(request))
    database_form_html = render_crispy_form(batches_form_crispy, context=context)
    database_form_soup = BeautifulSoup(database_form_html, 'html.parser')

    form_soup = BeautifulSoup(f'<form id="form_id_db_batches"></form>', 'html.parser')

    form = form_soup.find('form')
    form.attrs['hx-trigger'] = 'refresh_form from:body'
    form.attrs['hx-swap'] = 'outerHTML'
    form.attrs['hx-get'] = form_url

    form.append(database_form_soup)

    return form_soup


def delete_batch(batch_id, label, bcd_model, bcs_model):
    with connections['biochem'].cursor() as cur:
        user_logger.info(f"Deleteing Batch {batch_id}")
        cur.callproc("ARCHIVE_BATCH.DELETE_BATCH", [batch_id, label])

    bcd_model.objects.using('biochem').filter(batch_seq=batch_id).delete()
    bcs_model.objects.using('biochem').filter(batch_seq=batch_id).delete()


def run_biochem_delete_procedure(request, crispy_form, batch_id, delete_proc):
    soup = BeautifulSoup('', 'html.parser')
    soup.append(div := soup.new_tag('div'))
    div.attrs['id'] = BiochemBatchForm.get_batch_alert_area_id()
    div.attrs['hx-swap-oob'] = 'true'

    if request.method == 'GET':
        attrs = {
            'alert_area_id': 'div_id_biochem_batch',
            'message': _("Deleting Batch"),
            'logger': user_logger.name,
            'alert_type': 'info',
            'hx-post': request.path,
            'hx-trigger': "load",
        }
        alert = core_forms.websocket_post_request_alert(**attrs)
        div.append(alert)

        return HttpResponse(soup)

    delete_proc(batch_id)

    biochem_models.Bcstatndataerrors.objects.using('biochem').filter(batch_seq=batch_id).delete()
    biochem_models.Bcerrors.objects.using('biochem').filter(batch_seq=batch_id).delete()

    attrs = {
        'component_id': 'div_id_biochem_batch_alert',
        'message': _("Deletion Complete"),
        'alert_type': 'success'
    }
    alert = core_forms.blank_alert(**attrs)
    div.append(alert)

    html = render_crispy_form(crispy_form)
    form_soup = BeautifulSoup(html, 'html.parser')
    batch_select = form_soup.find('div', {"id": "div_id_selected_batch"})
    batch_select.attrs['hx-swap-oob'] = "true"
    soup.append(batch_select)

    response = HttpResponse(soup)
    response['Hx-Trigger'] = 'refresh_form'
    return response


def biochem_validation1_procedure(request, batch_id, validation_proc):
    soup = BeautifulSoup('', 'html.parser')
    soup.append(div := soup.new_tag('div'))
    div.attrs['id'] = BiochemBatchForm.get_batch_alert_area_id()
    div.attrs['hx-swap-oob'] = 'true'

    if request.method == 'GET':
        attrs = {
            'alert_area_id': 'div_id_biochem_batch',
            'message': _("Running Oracle Stage 1 Validation"),
            'logger': user_logger.name,
            'alert_type': 'info',
            'hx-post': request.path,
            'hx-trigger': "load",
        }
        alert = core_forms.websocket_post_request_alert(**attrs)
        div.append(alert)

        return HttpResponse(soup)

    validation_proc(batch_id)

    alert = get_error_alert(batch_id, _("Validation Complete with station errors"))
    div.append(alert)

    response = HttpResponse(soup)
    response['Hx-Trigger'] = 'reload_batch'
    return response


def biochem_validation2_procedure(request, batch_id, validation2_proc):
    soup = BeautifulSoup('', 'html.parser')
    soup.append(div := soup.new_tag('div'))
    div.attrs['id'] = BiochemBatchForm.get_batch_alert_area_id()
    div.attrs['hx-swap-oob'] = 'true'

    if request.method == 'GET':
        attrs = {
            'alert_area_id': 'div_id_biochem_batch',
            'message': _("Running Oracle Stage 2 Validation"),
            'logger': user_logger.name,
            'alert_type': 'info',
            'hx-post': request.path,
            'hx-trigger': "load",
        }
        alert = core_forms.websocket_post_request_alert(**attrs)
        div.append(alert)

        return HttpResponse(soup)

    validation2_proc(batch_id, 'UPSONP')

    alert = get_error_alert(batch_id, _("Validation Complete with data errors"))
    div.append(alert)

    response = HttpResponse(soup)
    response['Hx-Trigger'] = 'reload_batch'
    return response


def get_error_alert(batch_id, message):
    attrs = {
        'component_id': 'div_id_biochem_batch',
        'message': _("Validation Complete"),
        'alert_type': 'success'
    }

    if (errors := biochem_models.Bcerrors.objects.using('biochem').filter(batch_seq=batch_id)).exists():
        # for error in errors:
        #     user_logger.error(error)
        attrs['message'] = f"{message} : {errors.count()}"
        attrs['alert_type'] = 'warning'
        attrs['hx-get'] = reverse_lazy('core:form_biochem_database_get_batch_errors', args=(batch_id,))
        attrs['hx-trigger'] = 'load, update_batch from:body'
        attrs['hx-swap'] = 'none'

    return core_forms.blank_alert(**attrs)


def get_batch(request, database, mission_id, bcd_model, stage1_valid_proc,
              upload_url, validate1_url, validate2_url, delete_url, add_tables_to_soup_proc):
    soup = BeautifulSoup('', 'html.parser')
    soup.append(div_alert_area := soup.new_tag('div'))
    div_alert_area.attrs['id'] = BiochemBatchForm.get_batch_alert_area_id()
    div_alert_area.attrs['hx-swap-oob'] = 'true'

    if request.method == 'GET':
        attrs = {
            'alert_area_id': 'div_id_biochem_batch',
            'message': _("Loading Batch"),
            'logger': user_logger.name,
            'alert_type': 'info',
            'hx-post': request.path,
            'hx-trigger': "load",
        }
        alert = core_forms.websocket_post_request_alert(**attrs)
        div_alert_area.append(alert)

        return HttpResponse(soup)

    batch_id = request.POST.get('selected_batch', None)

    div_alert_area.attrs['hx-swap'] = 'innerHTML'

    soup.append(upload_button := get_upload_button(soup))
    soup.append(validate1_button := get_stage1_button(soup))
    soup.append(validate2_button := get_stage2_button(soup))
    soup.append(delete_button := get_delete_button(soup))

    upload_button.attrs['hx-get'] = reverse_lazy(upload_url, args=(database, mission_id,))

    validate1_button.attrs['disabled'] = 'disabled'
    validate2_button.attrs['disabled'] = 'disabled'
    delete_button.attrs['disabled'] = 'disabled'

    if not batch_id:
        response = HttpResponse(soup)
        response['Hx-Trigger'] = 'clear_batch'
        return response

    upload_button.attrs['disabled'] = 'disabled'
    validate1_button.attrs.pop('disabled')
    delete_button.attrs.pop('disabled')

    unvalidated = bcd_model.objects.using('biochem').filter(batch_seq=batch_id, process_flag='NR').exists()
    if not unvalidated:
        icon = BeautifulSoup(load_svg('1-square-fill'), 'html.parser').svg
        validate1_button.find('svg').decompose()
        validate1_button.append(icon)
        validate1_button.attrs['class'] = 'btn btn-sm btn-success'
        if biochem_models.Bcstatndataerrors.objects.using('biochem').filter(batch_seq=batch_id).exists():
            validate1_button.attrs['class'] = 'btn btn-sm btn-danger'
        else:
            validate2_button.attrs.pop('disabled')

            stage1_valid = stage1_valid_proc(batch_id)
            if stage1_valid:
                icon = BeautifulSoup(load_svg('2-square-fill'), 'html.parser').svg
                validate2_button.find('svg').decompose()
                validate2_button.append(icon)
                validate2_button.attrs['class'] = 'btn btn-sm btn-success'
                if biochem_models.Bcerrors.objects.using('biochem').filter(batch_seq=batch_id).exists():
                    validate2_button.attrs['class'] = 'btn btn-sm btn-danger'

    validate1_button.attrs['hx-get'] = reverse_lazy(validate1_url, args=(batch_id,))
    validate2_button.attrs['hx-get'] = reverse_lazy(validate2_url, args=(batch_id,))
    delete_button.attrs['hx-get'] = reverse_lazy(delete_url, args=(database, mission_id, batch_id,))

    add_tables_to_soup_proc(soup, batch_id)
    response = HttpResponse(soup)
    return response


def get_batch_info(request, database, mission_id, batch_id, upload_url, add_tables_to_soup_proc):
    soup = BeautifulSoup('', 'html.parser')

    soup.append(upload_button := get_upload_button(soup))
    soup.append(validate1_button := get_stage1_button(soup))
    soup.append(validate2_button := get_stage2_button(soup))
    soup.append(delete_button := get_delete_button(soup))

    upload_button.attrs['hx-get'] = reverse_lazy(upload_url, args=(database, mission_id))

    if not batch_id:
        validate1_button.attrs['disabled'] = 'disabled'
        validate2_button.attrs['disabled'] = 'disabled'
        delete_button.attrs['disabled'] = 'disabled'

        soup.append(div := soup.new_tag('div'))
        div.attrs['id'] = BiochemBatchForm.get_batch_alert_area_id()
        div.attrs['hx-swap-oob'] = 'true'

    add_tables_to_soup_proc(soup, batch_id, False)
    return HttpResponse(soup)


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


def get_station_errors_table(batch_id, page, swap_oob, page_url):
    page_start = _page_limit * page
    table_id = 'table_id_biochem_batch_errors'

    headers = ['Table', 'Record', 'Sample ID', 'Error']

    soup = get_table_soup('Station/Data Errors', table_id, headers, swap_oob)
    if batch_id == 0:
        return soup

    table = soup.find('tbody')

    validation_errors = {}
    errors = biochem_models.Bcstatndataerrors.objects.using('biochem').filter(
        batch_seq=batch_id
    ).order_by('-batch_seq')[page_start:(page_start + _page_limit)]

    tr_header = None
    for error in errors:
        table.append(tr_header := soup.new_tag('tr'))
        tr_header.append(td := soup.new_tag('td'))
        td.string = str(error.statn_data_table_name)

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(error.record_sequence_value)

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(error.collector_sample_id)

        tr_header.append(td := soup.new_tag('td'))
        if error.error_code not in validation_errors.keys():
            err = biochem_models.Bcerrorcodes.objects.using('biochem').get(error_code=error.error_code)
            validation_errors[error.error_code] = err

        td.string = str(validation_errors[error.error_code].long_desc)

    if tr_header:
        url = reverse_lazy(page_url, args=(batch_id, (page + 1),))
        tr_header.attrs['hx-target'] = f'#{table_id}_tbody'
        tr_header.attrs['hx-trigger'] = 'intersect once'
        tr_header.attrs['hx-get'] = url
        tr_header.attrs['hx-swap'] = "none"

    return soup
