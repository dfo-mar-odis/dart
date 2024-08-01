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

from core import forms as core_forms
from biochem import upload
from biochem import models as biochem_models

from dart.utils import load_svg

logger = logging.getLogger('dart')
user_logger = logger.getChild('user')


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

    def get_batch_select(self):
        url = reverse_lazy('core:form_biochem_batch_update_selected_batch')

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
    def get_validate_button_id():
        return 'btn_id_batch_validate'

    def get_validate_button(self):
        validate_attrs = {
            'id': self.get_validate_button_id(),
            'title': _('Run Batch Validation'),
            'name': 'validate_batch',
            'disabled': 'disabled',
            'hx-swap': 'none'
        }

        icon = load_svg('1-square')
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
        btn_col.fields.append(self.get_validate_button())
        btn_col.fields.append(self.get_delete_button())

        header.fields.append(self.get_alert_area())
        return header

    def get_card_body(self):
        body = super().get_card_body()

        attrs = {
            'hx_get': reverse_lazy('core:form_biochem_batch_get_batch', args=(0,)),
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
        batches = biochem_models.Bcbatches.objects.using('biochem').all().order_by('-batch_seq')
        self.fields['selected_batch'].choices += [(db.batch_seq, f"{db.batch_seq}: {db.name}") for db in batches]

    # at a minimum a mission_id and what happens when the upload button are pressed must be supplied in
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, card_name="biochem_batch_details", card_title=_("Biochem Batches"))

        self.fields['selected_batch'].label = False
        self.fields['selected_batch'].choices = [(None, '------')]

        database_id = caches['biochem_keys'].get('database_id', default=None)
        password = caches['biochem_keys'].get('pwd', version=database_id, default=None)
        if not database_id or not password:
            return

        self.get_batch_choices()


def get_batches_form(request):
    batches_form_crispy = BiochemBatchForm()

    context = {}
    context.update(csrf(request))
    database_form_html = render_crispy_form(batches_form_crispy, context=context)
    database_form_soup = BeautifulSoup(database_form_html, 'html.parser')

    form_soup = BeautifulSoup(f'<form id="form_id_db_batches"></form>', 'html.parser')
    form = form_soup.find('form')
    form.append(database_form_soup)

    return form_soup


def run_biochem_delete_procedure(request, batch_id):
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

    with connections['biochem'].cursor() as cur:
        user_logger.info(f"Deleteing Batch {batch_id}")
        delete_pass_var = cur.callproc("ARCHIVE_BATCH.DELETE_BATCH", [batch_id, 'DISCRETE'])

    bcd_d = upload.get_model('bcdiscretedataedits', biochem_models.BcdD)
    bcd_d.objects.using('biochem').filter(batch_seq=batch_id).delete()

    bcs_d = upload.get_model('bcdiscretestatnedits', biochem_models.BcsD)
    bcs_d.objects.using('biochem').filter(batch_seq=batch_id).delete()

    biochem_models.Bcstatndataerrors.objects.using('biochem').filter(batch_seq=batch_id).delete()

    attrs = {'component_id': 'div_id_biochem_batch_alert'}
    attrs['message'] = _("Deletion Complete")
    attrs['alert_type'] = 'success'
    alert = core_forms.blank_alert(**attrs)
    div.append(alert)

    crispy_form = BiochemBatchForm()
    html = render_crispy_form(crispy_form)
    form_soup = BeautifulSoup(html, 'html.parser')
    batch_select = form_soup.find('div', {"id": "div_id_selected_batch"})
    batch_select.attrs['hx-swap-oob'] = "true"
    soup.append(batch_select)

    response = HttpResponse(soup)
    response['Hx-Trigger'] = 'clear_batch'
    return response


def run_biochem_validation_procedure(request, batch_id):

    soup = BeautifulSoup('', 'html.parser')
    soup.append(div := soup.new_tag('div'))
    div.attrs['id'] = BiochemBatchForm.get_batch_alert_area_id()
    div.attrs['hx-swap-oob'] = 'true'

    if request.method == 'GET':
        attrs = {
            'alert_area_id': 'div_id_biochem_batch',
            'message': _("Running Oracle Validation"),
            'logger': user_logger.name,
            'alert_type': 'info',
            'hx-post': request.path,
            'hx-trigger': "load",
        }
        alert = core_forms.websocket_post_request_alert(**attrs)
        div.append(alert)

        return HttpResponse(soup)

    errors = None

    with connections['biochem'].cursor() as cur:
        user_logger.info(f"validating station data")
        stn_pass_var = cur.callfunc("VALIDATE_DISCRETE_STATN_DATA.VALIDATE_DISCRETE_STATION", str, [batch_id])

        user_logger.info(f"validating discrete data")
        data_pass_var = cur.callfunc("VALIDATE_DISCRETE_STATN_DATA.VALIDATE_DISCRETE_DATA", str, [batch_id])

        if stn_pass_var == 'T' and data_pass_var == 'T':
            user_logger.info(f"Moving BCS/BCD data to workbench")
            populate_pass_var = cur.callfunc("POPULATE_DISCRETE_EDITS_PKG.POPULATE_DISCRETE_EDITS", str, [batch_id])
        else:
            user_logger.info(f"Errors in BCS/BCD data. Stand by for a damage report.")

        cur.execute('commit')
        cur.close()

    attrs = {'component_id': 'div_id_biochem_batch'}
    attrs['message'] = _("Validation Complete")
    attrs['alert_type'] = 'success'

    if (errors := biochem_models.Bcstatndataerrors.objects.using('biochem').filter(batch_seq=batch_id)).exists():
        # for error in errors:
        #     user_logger.error(error)
        attrs['message'] = _("Validation Complete with station errors") + f" : {errors.count()}"
        attrs['alert_type'] = 'warning'
        attrs['hx-get'] = reverse_lazy('core:form_biochem_database_get_batch_errors', args=(batch_id,))
        attrs['hx-trigger'] = 'load, update_batch from:body'
        attrs['hx-swap'] = 'none'

    alert = core_forms.blank_alert(**attrs)
    div.append(alert)

    response = HttpResponse(soup)
    response['Hx-Trigger'] = 'reload_batch'
    return response


def get_batch_info(request, batch_id):
    soup = BeautifulSoup('', 'html.parser')

    icon = BeautifulSoup(load_svg('1-square'), 'html.parser').svg
    soup.append(validate_button := soup.new_tag('button'))
    validate_button.append(icon)

    validate_button.attrs['id'] = BiochemBatchForm.get_validate_button_id()
    validate_button.attrs['class'] = 'btn btn-sm btn-primary'
    validate_button.attrs['title'] = _("Validate Biochem Upload")
    validate_button.attrs['hx-swap'] = 'none'
    validate_button.attrs['hx-swap-oob'] = 'true'

    icon = BeautifulSoup(load_svg('dash-square'), 'html.parser').svg
    soup.append(delete_button := soup.new_tag('button'))
    delete_button.append(icon)

    delete_button.attrs['id'] = BiochemBatchForm.get_delete_batch_button_id()
    delete_button.attrs['class'] = 'btn btn-sm btn-danger'
    delete_button.attrs['title'] = _("Delete Batch")
    delete_button.attrs['hx-swap'] = 'none'
    delete_button.attrs['hx-swap-oob'] = 'true'
    delete_button.attrs['hx-confirm'] = _("Are you sure?")

    if not batch_id or (batch_id and batch_id == 0):
        validate_button.attrs['disabled'] = 'disabled'
        delete_button.attrs['disabled'] = 'disabled'

        soup.append(div := soup.new_tag('div'))
        div.attrs['id'] = BiochemBatchForm.get_batch_alert_area_id()
        div.attrs['hx-swap-oob'] = 'true'

    soup.append(get_bcs_table(batch_id, False).find('div'))
    soup.append(get_bcd_table(batch_id, False).find('div'))
    soup.append(get_station_errors_table(batch_id, False).find('div'))
    return HttpResponse(soup)


def get_batch(request):
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

    icon = BeautifulSoup(load_svg('1-square'), 'html.parser').svg
    soup.append(validate_button := soup.new_tag('button'))
    validate_button.append(icon)

    validate_button.attrs['id'] = BiochemBatchForm.get_validate_button_id()
    validate_button.attrs['class'] = 'btn btn-sm btn-primary'
    validate_button.attrs['title'] = _("Validate Biochem Upload")
    validate_button.attrs['hx-swap'] = 'none'
    validate_button.attrs['hx-swap-oob'] = 'true'

    icon = BeautifulSoup(load_svg('dash-square'), 'html.parser').svg
    soup.append(delete_button := soup.new_tag('button'))
    delete_button.append(icon)

    delete_button.attrs['id'] = BiochemBatchForm.get_delete_batch_button_id()
    delete_button.attrs['class'] = 'btn btn-sm btn-danger'
    delete_button.attrs['title'] = _("Delete Batch")
    delete_button.attrs['hx-swap'] = 'none'
    delete_button.attrs['hx-swap-oob'] = 'true'
    delete_button.attrs['hx-confirm'] = _("Are you sure?")

    if not batch_id:
        validate_button.attrs['disabled'] = 'disabled'
        delete_button.attrs['disabled'] = 'disabled'
        response = HttpResponse(soup)
        response['Hx-Trigger'] = 'clear_batch'
        return response

    bcd_model = upload.get_model('bcdiscretedataedits', biochem_models.BcdD)
    unvalidated = bcd_model.objects.using('biochem').filter(batch_seq=batch_id, process_flag='NR').exists()
    if not unvalidated:
        icon = BeautifulSoup(load_svg('1-square-fill'), 'html.parser').svg
        validate_button.find('svg').decompose()
        validate_button.append(icon)
        validate_button.attrs['class'] = 'btn btn-sm btn-success'
        if biochem_models.Bcstatndataerrors.objects.using('biochem').filter(batch_seq=batch_id).exists():
            validate_button.attrs['class'] = 'btn btn-sm btn-danger'

    validate_button.attrs['hx-get'] = reverse_lazy('core:form_biochem_batch_validation', args=(batch_id,))
    delete_button.attrs['hx-get'] = reverse_lazy('core:form_biochem_batch_delete', args=(batch_id,))

    soup.append(get_bcs_table(batch_id).find('div'))
    soup.append(get_bcd_table(batch_id).find('div'))
    soup.append(get_station_errors_table(batch_id).find('div'))
    response = HttpResponse(soup)
    return response


def get_table_soup(title, html_id, headers, swap_oob=True):
    soup = BeautifulSoup('', 'html.parser')

    soup.append(div := soup.new_tag('div'))
    div.attrs['class'] = 'mt-2 border border-dark'
    div.attrs['id'] = html_id

    div.append(div_title := soup.new_tag('div'))
    div_title.attrs['class'] = 'ms-2 h4'
    div_title.string = title

    div.append(div_table := soup.new_tag('div'))
    div_table.attrs['class'] = 'vertical-scrollbar-sm '

    if swap_oob:
        div.attrs['hx-swap-oob'] = "true"

    div_table.append(table := soup.new_tag('table'))
    table.attrs['class'] = 'table table-striped table-bordered table-sm '

    table.append(tr_header := soup.new_tag('tr'))
    for header in headers:
        tr_header.append(th := soup.new_tag('th'))
        th.string = header

    return soup


def get_station_errors_table(batch_id, swap_oob=True):
    headers = ['Sample ID', 'Table', 'Record', 'Error']

    soup = get_table_soup('Station/Data Errors', 'table_id_biochem_batch_errors', headers, swap_oob)
    if batch_id == 0:
        return soup

    table = soup.find('table')

    validation_errors = {}
    errors = biochem_models.Bcstatndataerrors.objects.using('biochem').filter(batch_seq=batch_id).order_by('-batch_seq')
    for error in errors:
        table.append(tr_header := soup.new_tag('tr'))
        tr_header.append(td := soup.new_tag('td'))
        td.string = error.collector_sample_id

        tr_header.append(td := soup.new_tag('td'))
        td.string = error.statn_data_table_name

        tr_header.append(td := soup.new_tag('td'))
        td.string = error.record_sequence_value

        tr_header.append(td := soup.new_tag('td'))
        if error.error_code not in validation_errors.keys():
            err = biochem_models.Bcerrorcodes.objects.using('biochem').get(error_code=error.error_code)
            validation_errors[error.error_code] = err

        td.string = str(validation_errors[error.error_code].long_desc)

    return soup


def get_bcs_table(batch_id, swap_oob=True):
    headers = ['ID']
    soup = get_table_soup("BCS - BcDiscreteStatnEdits", 'table_id_biochem_batch_bcs', headers, swap_oob)

    if batch_id == 0:
        return soup
    table = soup.find('table')

    table_model = upload.get_model('bcdiscretestatnedits', biochem_models.BcsD)

    rows = table_model.objects.using('biochem').filter(batch_seq=batch_id).order_by('-dis_sample_key_value')
    for row in rows:
        table.append(tr_header := soup.new_tag('tr'))

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(row.dis_sample_key_value)

    return soup


def get_bcd_table(batch_id, swap_oob=True):
    headers = ['ID', 'Record', 'Sample ID', 'Data Type', 'Data Method']
    soup = get_table_soup("BCD - BcDiscreteDataEdits", 'table_id_biochem_batch_bcd', headers, swap_oob)

    if batch_id == 0:
        return soup
    table = soup.find('table')

    table_model = upload.get_model('bcdiscretedataedits', biochem_models.BcdD)

    rows = table_model.objects.using('biochem').filter(batch_seq=batch_id).order_by('-dis_sample_key_value')
    for row in rows:
        table.append(tr_header := soup.new_tag('tr'))

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(row.dis_sample_key_value)

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(row.dis_data_num)

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(row.dis_detail_collector_samp_id)

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(row.dis_detail_data_type_seq)

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(row.data_type_method)

    return soup


prefix = 'biochem/batch/'
database_urls = [
    path(f'{prefix}', get_batch, name="form_biochem_batch_update_selected_batch"),

    path(f'{prefix}<int:batch_id>/', get_batch_info, name="form_biochem_batch_get_batch"),
    path(f'{prefix}validate/<int:batch_id>/', run_biochem_validation_procedure, name="form_biochem_batch_validation"),
    path(f'{prefix}delete/<int:batch_id>/', run_biochem_delete_procedure, name="form_biochem_batch_delete"),
]
