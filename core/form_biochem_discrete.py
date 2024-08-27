import os
import logging

from bs4 import BeautifulSoup
from crispy_forms.utils import render_crispy_form
from django.core.cache import caches

from django.db import connections
from django.http import HttpResponse
from django.template.context_processors import csrf
from django.urls import path, reverse_lazy
from django.utils.translation import gettext as _

from settingsdb import models as settingsdb_models

from core import validation
from core import forms as core_forms
from core import models as core_models
from core import form_biochem_database
from core.form_biochem_batch import BiochemBatchForm, get_table_soup, generic_table_paging

from biochem import upload
from biochem import models as biochem_models

from dart.utils import load_svg

logger = logging.getLogger('dart')
user_logger = logger.getChild('user')

_page_limit = 50


class BiochemDiscreteBatchForm(BiochemBatchForm):
    database = None
    mission_id = None

    def get_biochem_batch_upload_url(self):
        return reverse_lazy('core:form_biochem_discrete_upload_batch', args=(self.database, self.mission_id))

    def get_biochem_batch_url(self):
        return reverse_lazy('core:form_biochem_discrete_update_selected_batch', args=(self.database, self.mission_id))

    def get_biochem_batch_clear_url(self):
        return reverse_lazy('core:form_biochem_discrete_get_batch', args=(0,))


def get_batches_form(request, database, mission_id):
    batches_form_crispy = BiochemDiscreteBatchForm(database=database, mission_id=mission_id)

    context = {}
    context.update(csrf(request))
    database_form_html = render_crispy_form(batches_form_crispy, context=context)
    database_form_soup = BeautifulSoup(database_form_html, 'html.parser')

    form_soup = BeautifulSoup(f'<form id="form_id_db_batches"></form>', 'html.parser')
    form = form_soup.find('form')
    form.append(database_form_soup)

    return form_soup


def run_biochem_delete_procedure(request, database, mission_id, batch_id):
    soup = BeautifulSoup('', 'html.parser')
    soup.append(div := soup.new_tag('div'))
    div.attrs['id'] = BiochemDiscreteBatchForm.get_batch_alert_area_id()
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

    bcd_d = upload.get_model(form_biochem_database.get_bcd_d_table(), biochem_models.BcdD)
    bcd_d.objects.using('biochem').filter(batch_seq=batch_id).delete()

    bcs_d = upload.get_model(form_biochem_database.get_bcs_d_table(), biochem_models.BcsD)
    bcs_d.objects.using('biochem').filter(batch_seq=batch_id).delete()

    biochem_models.Bcstatndataerrors.objects.using('biochem').filter(batch_seq=batch_id).delete()
    biochem_models.Bcerrors.objects.using('biochem').filter(batch_seq=batch_id).delete()

    attrs = {'component_id': 'div_id_biochem_batch_alert'}
    attrs['message'] = _("Deletion Complete")
    attrs['alert_type'] = 'success'
    alert = core_forms.blank_alert(**attrs)
    div.append(alert)

    crispy_form = BiochemDiscreteBatchForm(database=database, mission_id=mission_id)
    html = render_crispy_form(crispy_form)
    form_soup = BeautifulSoup(html, 'html.parser')
    batch_select = form_soup.find('div', {"id": "div_id_selected_batch"})
    batch_select.attrs['hx-swap-oob'] = "true"
    soup.append(batch_select)

    response = HttpResponse(soup)
    response['Hx-Trigger'] = 'clear_batch'
    return response


def biochem_validation2_procedure(request, batch_id):
    soup = BeautifulSoup('', 'html.parser')
    soup.append(div := soup.new_tag('div'))
    div.attrs['id'] = BiochemDiscreteBatchForm.get_batch_alert_area_id()
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

    with connections['biochem'].cursor() as cur:
        user_logger.info(f"validating mission data")
        mission_pass_var = cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_MISSION_ERRORS", str, [batch_id, 'UPSONP'])

        user_logger.info(f"validating event data")
        event_pass_var = cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_EVENT_ERRORS", str, [batch_id, 'UPSONP'])

        user_logger.info(f"validating discrete header data")
        dis_hdr_pass_var = cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_DISHEDR_ERRORS", str, [batch_id, 'UPSONP'])

        user_logger.info(f"validating discrete detail data")
        dis_detail_pass_var = cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_DISDETAIL_ERRORS", str,
                                           [batch_id, 'UPSONP'])

        user_logger.info(f"validating discrete replicate data")
        dis_rep_pass_var = cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_DISREPLIC_ERRORS", str, [batch_id, 'UPSONP'])

    attrs = {'component_id': 'div_id_biochem_batch'}
    attrs['message'] = _("Validation Complete")
    attrs['alert_type'] = 'success'

    if (errors := biochem_models.Bcerrors.objects.using('biochem').filter(batch_seq=batch_id)).exists():
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


def biochem_validation1_procedure(request, batch_id):
    soup = BeautifulSoup('', 'html.parser')
    soup.append(div := soup.new_tag('div'))
    div.attrs['id'] = BiochemDiscreteBatchForm.get_batch_alert_area_id()
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


def get_stage1_button(soup):
    icon = BeautifulSoup(load_svg('1-square'), 'html.parser').svg
    validate1_button = soup.new_tag('button')
    validate1_button.append(icon)
    validate1_button.attrs['id'] = BiochemDiscreteBatchForm.get_validate_stage1_button_id()
    validate1_button.attrs['class'] = 'btn btn-sm btn-primary'
    validate1_button.attrs['title'] = _("Validate Stage 1")
    validate1_button.attrs['hx-swap'] = 'none'
    validate1_button.attrs['hx-swap-oob'] = 'true'

    return validate1_button


def get_stage2_button(soup):
    icon = BeautifulSoup(load_svg('2-square'), 'html.parser').svg
    validate2_button = soup.new_tag('button')
    validate2_button.append(icon)
    validate2_button.attrs['id'] = BiochemDiscreteBatchForm.get_validate_stage2_button_id()
    validate2_button.attrs['class'] = 'btn btn-sm btn-primary'
    validate2_button.attrs['title'] = _("Validate Stage 2")
    validate2_button.attrs['hx-swap'] = 'none'
    validate2_button.attrs['hx-swap-oob'] = 'true'

    return validate2_button


def get_delete_button(soup):
    icon = BeautifulSoup(load_svg('dash-square'), 'html.parser').svg
    delete_button = soup.new_tag('button')
    delete_button.append(icon)
    delete_button.attrs['id'] = BiochemDiscreteBatchForm.get_delete_batch_button_id()
    delete_button.attrs['class'] = 'btn btn-sm btn-danger'
    delete_button.attrs['title'] = _("Delete Batch")
    delete_button.attrs['hx-swap'] = 'none'
    delete_button.attrs['hx-swap-oob'] = 'true'
    delete_button.attrs['hx-confirm'] = _("Are you sure?")

    return delete_button


def get_batch_info(request, batch_id):
    soup = BeautifulSoup('', 'html.parser')
    soup.append(validate1_button := get_stage1_button(soup))
    soup.append(validate2_button := get_stage2_button(soup))
    soup.append(delete_button := get_delete_button(soup))

    if not batch_id or (batch_id and batch_id == 0):
        validate1_button.attrs['disabled'] = 'disabled'
        validate2_button.attrs['disabled'] = 'disabled'
        delete_button.attrs['disabled'] = 'disabled'

        soup.append(div := soup.new_tag('div'))
        div.attrs['id'] = BiochemDiscreteBatchForm.get_batch_alert_area_id()
        div.attrs['hx-swap-oob'] = 'true'

    add_tables_to_soup(soup, batch_id, False)
    return HttpResponse(soup)


def get_batch(request, database, mission_id):
    soup = BeautifulSoup('', 'html.parser')
    soup.append(div_alert_area := soup.new_tag('div'))
    div_alert_area.attrs['id'] = BiochemDiscreteBatchForm.get_batch_alert_area_id()
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

    soup.append(validate1_button := get_stage1_button(soup))
    soup.append(validate2_button := get_stage2_button(soup))
    soup.append(delete_button := get_delete_button(soup))

    if not batch_id:
        validate1_button.attrs['disabled'] = 'disabled'
        validate2_button.attrs['disabled'] = 'disabled'
        delete_button.attrs['disabled'] = 'disabled'
        response = HttpResponse(soup)
        response['Hx-Trigger'] = 'clear_batch'
        return response

    bcd_model = upload.get_model(form_biochem_database.get_bcd_d_table(), biochem_models.BcdD)
    unvalidated = bcd_model.objects.using('biochem').filter(batch_seq=batch_id, process_flag='NR').exists()
    if not unvalidated:
        icon = BeautifulSoup(load_svg('1-square-fill'), 'html.parser').svg
        validate1_button.find('svg').decompose()
        validate1_button.append(icon)
        validate1_button.attrs['class'] = 'btn btn-sm btn-success'
        if biochem_models.Bcstatndataerrors.objects.using('biochem').filter(batch_seq=batch_id).exists():
            validate1_button.attrs['class'] = 'btn btn-sm btn-danger'
            validate2_button.attrs['disabled'] = 'disabled'
        else:
            mission_valid = biochem_models.Bcmissionedits.objects.using('biochem').filter(batch_seq=batch_id,
                                                                                          process_flag='ENR').exists()
            event_valid = biochem_models.Bceventedits.objects.using('biochem').filter(batch_seq=batch_id,
                                                                                      process_flag='ENR').exists()
            dishedr_valid = biochem_models.Bcdiscretehedredits.objects.using('biochem').filter(batch_seq=batch_id,
                                                                                               process_flag='ENR').exists()
            disdtai_valid = biochem_models.Bcdiscretedtailedits.objects.using('biochem').filter(batch_seq=batch_id,
                                                                                                process_flag='ENR').exists()
            disrepl_valid = biochem_models.Bcdisreplicatedits.objects.using('biochem').filter(batch_seq=batch_id,
                                                                                              process_flag='ENR').exists()

            if not mission_valid and not event_valid and not dishedr_valid and not disdtai_valid and not disrepl_valid:
                icon = BeautifulSoup(load_svg('2-square-fill'), 'html.parser').svg
                validate2_button.find('svg').decompose()
                validate2_button.append(icon)
                validate2_button.attrs['class'] = 'btn btn-sm btn-success'
                if biochem_models.Bcerrors.objects.using('biochem').filter(batch_seq=batch_id).exists():
                    validate2_button.attrs['class'] = 'btn btn-sm btn-danger'

    validate1_button.attrs['hx-get'] = reverse_lazy('core:form_biochem_discrete_validation1', args=(batch_id,))
    validate2_button.attrs['hx-get'] = reverse_lazy('core:form_biochem_discrete_validation2', args=(batch_id,))

    delete_button.attrs['hx-get'] = reverse_lazy('core:form_biochem_discrete_delete',
                                                 args=(database, mission_id, batch_id))

    add_tables_to_soup(soup, batch_id)
    response = HttpResponse(soup)
    return response


def page_data_station_errors(request, batch_id, page):
    table_id = 'table_id_biochem_batch_errors'
    return generic_table_paging(request, batch_id, page, table_id, get_station_errors_table)


def get_station_errors_table(batch_id, page=0, swap_oob=True):
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
        url = reverse_lazy('core:form_biochem_discrete_page_station_errors', args=(batch_id, (page + 1),))
        tr_header.attrs['hx-target'] = f'#{table_id}_tbody'
        tr_header.attrs['hx-trigger'] = 'intersect once'
        tr_header.attrs['hx-get'] = url
        tr_header.attrs['hx-swap'] = "none"

    return soup


def page_data_errors(request, batch_id, page):
    table_id = 'table_id_biochem_batch_data_errors'
    return generic_table_paging(request, batch_id, page, table_id, get_data_errors_table)


def get_data_errors_table(batch_id, page=0, swap_oob=True):
    page_start = _page_limit * page
    table_id = 'table_id_biochem_batch_data_errors'

    headers = ['Table', 'Record', 'Sample ID', 'Datatype', 'Method', 'Error']

    soup = get_table_soup('Data Errors', table_id, headers, swap_oob)
    if batch_id == 0:
        return soup

    table = soup.find('tbody')

    validation_errors = {}
    errors = biochem_models.Bcerrors.objects.using('biochem').filter(
        batch_seq=batch_id)[page_start:(page_start + _page_limit)]

    tr_header = None
    for error in errors:

        table.append(tr_header := soup.new_tag('tr'))

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(error.edit_table_name)

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(error.record_num_seq)

        replicate = None
        if error.edit_table_name.upper() == 'BCDISREPLICATEDITS':
            replicate = biochem_models.Bcdisreplicatedits.objects.using('biochem').get(
                dis_repl_edt_seq=error.record_num_seq,
            )
        elif error.edit_table_name.upper() == 'BCDISCRETEDTAILEDITS':
            replicate = biochem_models.Bcdiscretedtailedits.objects.using('biochem').get(
                dis_detail_edt_seq=error.record_num_seq,
            )

        tr_header.append(td_sample_id := soup.new_tag('td'))
        td_sample_id.string = "---"

        tr_header.append(td_sample_type := soup.new_tag('td'))
        td_sample_type.string = "---"

        tr_header.append(td_sample_type_method := soup.new_tag('td'))
        td_sample_type_method.string = "---"
        if replicate:
            td_sample_id.string = str(replicate.collector_sample_id)
            td_sample_type.string = str(replicate.data_type_seq)

            datatype = biochem_models.Bcdatatypes.objects.using('biochem').get(data_type_seq=replicate.data_type_seq)
            td_sample_type_method.string = str(datatype.method)

        tr_header.append(td := soup.new_tag('td'))
        if error.error_code not in validation_errors.keys():
            err = biochem_models.Bcerrorcodes.objects.using('biochem').get(error_code=error.error_code)
            validation_errors[error.error_code] = err

        td.string = str(validation_errors[error.error_code].long_desc)

    if tr_header:
        url = reverse_lazy('core:form_biochem_discrete_page_errors', args=(batch_id, (page + 1),))
        tr_header.attrs['hx-target'] = f'#{table_id}_tbody'
        tr_header.attrs['hx-trigger'] = 'intersect once'
        tr_header.attrs['hx-get'] = url
        tr_header.attrs['hx-swap'] = "none"

    return soup


def get_data_error_summary_table(batch_id, swap_oob=True):
    headers = ['Error Count', 'Datatype', 'Description', 'Error']

    soup = get_table_soup('Data Error Summary', 'table_id_biochem_batch_data_error_summary', headers, swap_oob)
    if batch_id == 0:
        return soup

    table = soup.find('tbody')

    validation_errors = {}
    # get all of the BCDisReplicateEdits rows that contain errors and distill them down to only unique datatypes
    datatype_codes = biochem_models.Bcdisreplicatedits.objects.using('biochem').filter(
        batch_seq=batch_id,
        process_flag__iexact='err'
    )

    for code in datatype_codes.values_list('data_type_seq', flat=True).distinct():
        errors = datatype_codes.filter(
            data_type_seq=code,
        )

        key = errors.first()
        error = biochem_models.Bcerrors.objects.using('biochem').get(record_num_seq=key.dis_repl_edt_seq)
        datatype = biochem_models.Bcdatatypes.objects.using('biochem').get(data_type_seq=key.data_type_seq)

        table.append(tr_header := soup.new_tag('tr'))

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(errors.count())

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(datatype.data_type_seq)

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(datatype.method)

        tr_header.append(td := soup.new_tag('td'))

        if error.error_code not in validation_errors.keys():
            err = biochem_models.Bcerrorcodes.objects.using('biochem').get(error_code=error.error_code)
            validation_errors[error.error_code] = err

        td.string = str(validation_errors[error.error_code].long_desc)

    return soup


def page_bcs(request, batch_id, page):
    table_id = 'table_id_biochem_batch_bcs'
    return generic_table_paging(request, batch_id, page, table_id, get_bcs_table)


def get_bcs_table(batch_id, page=0, swap_oob=True):
    page_start = _page_limit * page
    table_id = "table_id_biochem_batch_bcs"

    headers = ['ID', 'Process Flag']
    soup = get_table_soup("BCS - BcDiscreteStatnEdits", table_id, headers, swap_oob)

    if batch_id == 0:
        return soup
    table = soup.find('tbody')

    table_model = upload.get_model(form_biochem_database.get_bcs_d_table(), biochem_models.BcsD)

    rows = table_model.objects.using('biochem').filter(
        batch_seq=batch_id
    ).order_by('-dis_sample_key_value')[page_start:(page_start + _page_limit)]

    tr_header = None
    for row in rows:
        table.append(tr_header := soup.new_tag('tr'))

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(row.dis_sample_key_value)

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(row.process_flag)

    if tr_header:
        url = reverse_lazy('core:form_biochem_discrete_page_bcs', args=(batch_id, (page + 1),))
        tr_header.attrs['hx-target'] = f'#{table_id}_tbody'
        tr_header.attrs['hx-trigger'] = 'intersect once'
        tr_header.attrs['hx-get'] = url
        tr_header.attrs['hx-swap'] = "none"

    return soup


def page_bcd(request, batch_id, page):
    table_id = 'table_id_biochem_batch_bcd'
    return generic_table_paging(request, batch_id, page, table_id, get_bcd_table)


def get_bcd_table(batch_id, page=0, swap_oob=True):
    page_start = _page_limit * page
    table_id = "table_id_biochem_batch_bcd"

    headers = ['ID', 'Record', 'Sample ID', 'Data Type', 'Data Method', 'Process Flag']
    soup = get_table_soup("BCD - BcDiscreteDataEdits", table_id, headers, swap_oob)

    if batch_id == 0:
        return soup
    table = soup.find('tbody')

    table_model = upload.get_model(form_biochem_database.get_bcd_d_table(), biochem_models.BcdD)

    rows = table_model.objects.using('biochem').filter(
        batch_seq=batch_id
    ).order_by('-dis_sample_key_value')[page_start:(page_start + _page_limit)]

    tr_header = None
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

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(row.process_flag)

    if tr_header:
        url = reverse_lazy('core:form_biochem_discrete_page_bcd', args=(batch_id, (page + 1),))
        tr_header.attrs['hx-target'] = f'#{table_id}_tbody'
        tr_header.attrs['hx-trigger'] = 'intersect once'
        tr_header.attrs['hx-get'] = url
        tr_header.attrs['hx-swap'] = "none"

    return soup


def add_tables_to_soup(soup, batch_id, swap_oob=True):
    soup.append(get_bcs_table(batch_id, swap_oob=swap_oob).find('div'))
    soup.append(get_bcd_table(batch_id, swap_oob=swap_oob).find('div'))
    soup.append(get_station_errors_table(batch_id, swap_oob=swap_oob).find('div'))

    soup.append(tab := soup.new_tag('div'))
    tab.append(ul_list := soup.new_tag('ul'))
    ul_list.attrs['class'] = 'nav nav-tabs mt-2'
    ul_list.attrs['role'] = 'tablist'

    ul_list.append(li_summary := soup.new_tag('li'))
    li_summary.attrs['class'] = 'nav-item active'
    li_summary.attrs['role'] = 'presentation'

    li_summary.append(summary_link := soup.new_tag('button'))
    summary_link.attrs['id'] = 'li_id_data_error_summary'
    summary_link.attrs['role'] = 'tab'
    summary_link.attrs['aria-controls'] = 'div_id_data_error_summary'
    summary_link.attrs['aria-selected'] = 'true'
    summary_link.attrs['data-bs-toggle'] = 'tab'
    summary_link.attrs['data-bs-target'] = "#div_id_data_error_summary"
    summary_link.attrs['type'] = 'button'
    summary_link.attrs['class'] = 'nav-link active'
    summary_link.string = _("Data Error Summary")

    ul_list.append(li_summary := soup.new_tag('li'))
    li_summary.attrs['class'] = 'nav-item'
    li_summary.attrs['role'] = 'presentation'

    li_summary.append(summary_link := soup.new_tag('button'))
    summary_link.attrs['id'] = 'li_id_data_error_details'
    summary_link.attrs['role'] = 'tab'
    summary_link.attrs['tabindex'] = '-1'
    summary_link.attrs['aria-controls'] = 'div_id_data_error_details'
    summary_link.attrs['aria-selected'] = 'false'
    summary_link.attrs['data-bs-toggle'] = 'tab'
    summary_link.attrs['data-bs-target'] = "#div_id_data_error_details"
    summary_link.attrs['type'] = 'button'
    summary_link.attrs['class'] = 'nav-link'
    summary_link.string = _("Data Error Details")

    soup.append(tab := soup.new_tag('div'))
    tab.attrs['class'] = 'tab-content'

    tab.append(data_error_summary := soup.new_tag('div'))
    data_error_summary.attrs['id'] = 'div_id_data_error_summary'
    data_error_summary.attrs['class'] = 'tab-pane show active'
    data_error_summary.append(get_data_error_summary_table(batch_id, swap_oob=swap_oob).find('div'))

    tab.append(data_error_details := soup.new_tag('div'))
    data_error_details.attrs['id'] = 'div_id_data_error_details'
    data_error_details.attrs['class'] = 'tab-pane'
    data_error_details.append(get_data_errors_table(batch_id, swap_oob=swap_oob).find('div'))


def sample_data_upload(database, mission: core_models.Mission, uploader: str, batch_id: int):
    # clear previous errors if there were any from the last upload attempt
    mission.errors.filter(type=core_models.ErrorType.biochem).delete()
    core_models.Error.objects.using(database).filter(mission=mission, type=core_models.ErrorType.biochem).delete()

    # send_user_notification_queue('biochem', _("Validating Sensor/Sample Datatypes"))
    user_logger.info(_("Validating Sensor/Sample Datatypes"))
    samples_types_for_upload = [bcupload.type for bcupload in
                                core_models.BioChemUpload.objects.using(database).filter(type__mission=mission)]

    # Todo: I'm running the standard DART based event/data validation here, but we probably should be running the
    #  BioChem Validation from core.form_validation_biochem.run_biochem_validation()
    errors = validation.validate_samples_for_biochem(mission=mission, sample_types=samples_types_for_upload)

    if errors:
        # send_user_notification_queue('biochem', _("Datatypes missing see errors"))
        user_logger.info(_("Datatypes missing see errors"))
        core_models.Error.objects.using(database).bulk_create(errors)

    # create and upload the BCS data if it doesn't already exist
    form_biochem_database.upload_bcs_d_data(mission, uploader, batch_id)
    form_biochem_database.upload_bcd_d_data(mission, uploader, batch_id)

    return batch_id


def upload_batch(request, database, mission_id):
    mission = core_models.Mission.objects.using(database).get(pk=mission_id)

    soup = BeautifulSoup('', 'html.parser')
    soup.append(div := soup.new_tag('div'))
    div.attrs['id'] = "div_id_biochem_batch_alert_area"
    div.attrs['hx-swap-oob'] = 'true'

    # are we connected?
    if not form_biochem_database.is_connected():
        alert_soup = core_forms.blank_alert("div_id_biochem_alert", _("Not Connected"), alert_type="danger")
        div.append(alert_soup)
        return HttpResponse(soup)

    db_id = caches['biochem_keys'].get('database_id')
    connected_database = settingsdb_models.BcDatabaseConnection.objects.get(pk=db_id)

    # do we have an uploader?
    uploader = connected_database.uploader if connected_database.uploader else connected_database.account_name

    if not uploader:
        alert_soup = form_biochem_database.confirm_uploader(request)
        if alert_soup:
            div.append(alert_soup)
            return HttpResponse(soup)

    alert_soup = form_biochem_database.confirm_descriptor(request, mission)
    if alert_soup:
        div.append(alert_soup)
        return HttpResponse(soup)

    try:
        uploader = request.POST['uploader2'] if 'uploader2' in request.POST else \
            request.POST['uploader'] if 'uploader' in request.POST else "N/A"

        batch_id = form_biochem_database.get_mission_batch_id()
        biochem_models.Bcbatches.objects.using('biochem').get_or_create(name=mission.mission_descriptor,
                                                                        username=uploader,
                                                                        batch_seq=batch_id)

        bc_statn_data_errors = []
        # user_logger.info(_("Running Biochem validation on Batch") + f" : {batch_id}")
        # bc_statn_data_errors = run_biochem_validation_procedure(batch_id, mission.mission_descriptor)

        sample_data_upload(database, mission, uploader, batch_id)

        attrs = {
            'component_id': 'div_id_upload_biochem',
            'alert_type': 'success',
            'message': _("Thank you for uploading"),
        }
        if bc_statn_data_errors:
            bcd_rows = upload.get_model(form_biochem_database.get_bcd_d_table(), biochem_models.BcdD)
            attrs['alert_type'] = 'warning'
            attrs['message'] = _("Errors Present in Biochem Validation for batch") + f" : {batch_id}"
            for error in bc_statn_data_errors:
                err = biochem_models.Bcerrorcodes.objects.using('biochem').get(error_code=error[3])
                data = bcd_rows.objects.using('biochem').get(dis_data_num=error[1])
                attrs['message'] += f"\n{err.long_desc}\n- {data}"

    except Exception as e:
        logger.exception(e)
        attrs = {
            'component_id': 'div_id_upload_biochem',
            'alert_type': 'danger',
            'message': str(e),
        }

    alert_soup = core_forms.blank_alert(**attrs)
    div.append(alert_soup)
    response = HttpResponse(soup)
    response['HX-Trigger'] = 'update_samples, biochem_db_connect'
    return response


prefix = 'biochem/batch'
db_prefix = f'<str:database>/<int:mission_id>/{prefix}'
database_urls = [
    path(f'{db_prefix}/upload/', upload_batch, name="form_biochem_discrete_upload_batch"),
    path(f'{db_prefix}/', get_batch, name="form_biochem_discrete_update_selected_batch"),
    path(f'{db_prefix}/delete/<int:batch_id>/', run_biochem_delete_procedure, name="form_biochem_discrete_delete"),

    path(f'{prefix}/<int:batch_id>/', get_batch_info, name="form_biochem_discrete_get_batch"),
    path(f'{prefix}/validate1/<int:batch_id>/', biochem_validation1_procedure, name="form_biochem_discrete_validation1"),
    path(f'{prefix}/validate2/<int:batch_id>/', biochem_validation2_procedure, name="form_biochem_discrete_validation2"),
    path(f'{prefix}/page/bcd/<int:batch_id>/<int:page>/', page_bcd, name="form_biochem_discrete_page_bcd"),
    path(f'{prefix}/page/bcs/<int:batch_id>/<int:page>/', page_bcs, name="form_biochem_discrete_page_bcs"),
    path(f'{prefix}/page/station_errors/<int:batch_id>/<int:page>/', page_data_station_errors,
         name="form_biochem_discrete_page_station_errors"
    ),
    path(f'{prefix}/page/data_errors/<int:batch_id>/<int:page>/', page_data_errors,
         name="form_biochem_discrete_page_errors"
    ),

]
