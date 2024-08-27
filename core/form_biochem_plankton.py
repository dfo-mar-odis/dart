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


class BiochemPlanktonBatchForm(BiochemBatchForm):

    def get_biochem_batch_upload_url(self):
        return reverse_lazy('core:form_biochem_plankton_upload_batch', args=(self.database, self.mission_id))

    def get_biochem_batch_url(self):
        return reverse_lazy('core:form_biochem_plankton_update_selected_batch', args=(self.database, self.mission_id))

    def get_biochem_batch_clear_url(self):
        return reverse_lazy('core:form_biochem_plankton_get_batch', args=(0,))

    def get_batch_choices(self):
        mission = core_models.Mission.objects.using(self.database).get(pk=self.mission_id)
        table_model = upload.get_model(form_biochem_database.get_bcs_p_table(), biochem_models.BcsP)

        batch_ids = table_model.objects.using('biochem').all().values_list('batch_seq', flat=True).distinct()

        batches = biochem_models.Bcbatches.objects.using('biochem').filter(
            name=mission.mission_descriptor,
            batch_seq__in=batch_ids
        ).order_by('-batch_seq')
        self.fields['selected_batch'].choices += [(db.batch_seq, f"{db.batch_seq}: {db.name}") for db in batches]


def get_batches_form(request, database, mission_id):
    batches_form_crispy = BiochemPlanktonBatchForm(database=database, mission_id=mission_id)

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
    div.attrs['id'] = BiochemPlanktonBatchForm.get_batch_alert_area_id()
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
        delete_pass_var = cur.callproc("ARCHIVE_BATCH.DELETE_BATCH", [batch_id, 'PLANKTON'])

    bcd_d = upload.get_model(form_biochem_database.get_bcd_p_table(), biochem_models.BcdP)
    bcd_d.objects.using('biochem').filter(batch_seq=batch_id).delete()

    bcs_d = upload.get_model(form_biochem_database.get_bcs_p_table(), biochem_models.BcsP)
    bcs_d.objects.using('biochem').filter(batch_seq=batch_id).delete()

    biochem_models.Bcstatndataerrors.objects.using('biochem').filter(batch_seq=batch_id).delete()
    biochem_models.Bcerrors.objects.using('biochem').filter(batch_seq=batch_id).delete()

    attrs = {'component_id': 'div_id_biochem_batch_alert'}
    attrs['message'] = _("Deletion Complete")
    attrs['alert_type'] = 'success'
    alert = core_forms.blank_alert(**attrs)
    div.append(alert)

    crispy_form = BiochemPlanktonBatchForm(database=database, mission_id=mission_id)
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
    div.attrs['id'] = BiochemPlanktonBatchForm.get_batch_alert_area_id()
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

        user_logger.info(f"validating plankton header data")
        plk_hdr_pass_var = cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_PLANK_HEDR_ERRORS", str, [batch_id, 'UPSONP'])

        user_logger.info(f"validating plankton general data")
        plk_generl_pass_var = cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_PLANK_GENERL_ERRS", str,
                                           [batch_id, 'UPSONP'])

        user_logger.info(f"validating plankton details data")
        plk_dtail_pass_var = cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_PLANK_DTAIL_ERRS", str,
                                          [batch_id, 'UPSONP'])

        user_logger.info(f"validating plankton details data")
        plk_freq_pass_var = cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_PLANK_FREQ_ERRS", str, [batch_id, 'UPSONP'])

        user_logger.info(f"validating plankton replicate data")
        plk_indiv_pass_var = cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_PLANK_INDIV_ERRS", str,
                                          [batch_id, 'UPSONP'])

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
    div.attrs['id'] = BiochemPlanktonBatchForm.get_batch_alert_area_id()
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
        stn_pass_var = cur.callfunc("VALIDATE_PLANKTON_STATN_DATA.VALIDATE_PLANKTON_STATION", str, [batch_id])

        user_logger.info(f"validating plankton data")
        data_pass_var = cur.callfunc("VALIDATE_PLANKTON_STATN_DATA.VALIDATE_PLANKTON_DATA", str, [batch_id])

        if stn_pass_var == 'T' and data_pass_var == 'T':
            user_logger.info(f"Moving BCS/BCD data to workbench")
            populate_pass_var = cur.callfunc("POPULATE_PLANKTON_EDITS_PKG.POPULATE_PLANKTON_EDITS", str, [batch_id])
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
    validate1_button.attrs['id'] = BiochemPlanktonBatchForm.get_validate_stage1_button_id()
    validate1_button.attrs['class'] = 'btn btn-sm btn-primary'
    validate1_button.attrs['title'] = _("Validate Stage 1")
    validate1_button.attrs['hx-swap'] = 'none'
    validate1_button.attrs['hx-swap-oob'] = 'true'

    return validate1_button


def get_stage2_button(soup):
    icon = BeautifulSoup(load_svg('2-square'), 'html.parser').svg
    validate2_button = soup.new_tag('button')
    validate2_button.append(icon)
    validate2_button.attrs['id'] = BiochemPlanktonBatchForm.get_validate_stage2_button_id()
    validate2_button.attrs['class'] = 'btn btn-sm btn-primary'
    validate2_button.attrs['title'] = _("Validate Stage 2")
    validate2_button.attrs['hx-swap'] = 'none'
    validate2_button.attrs['hx-swap-oob'] = 'true'

    return validate2_button


def get_delete_button(soup):
    icon = BeautifulSoup(load_svg('dash-square'), 'html.parser').svg
    delete_button = soup.new_tag('button')
    delete_button.append(icon)
    delete_button.attrs['id'] = BiochemPlanktonBatchForm.get_delete_batch_button_id()
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
        div.attrs['id'] = BiochemPlanktonBatchForm.get_batch_alert_area_id()
        div.attrs['hx-swap-oob'] = 'true'

    add_tables_to_soup(soup, batch_id, False)
    return HttpResponse(soup)


def get_batch(request, database, mission_id):
    soup = BeautifulSoup('', 'html.parser')
    soup.append(div_alert_area := soup.new_tag('div'))
    div_alert_area.attrs['id'] = BiochemPlanktonBatchForm.get_batch_alert_area_id()
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

    bcd_model = upload.get_model(form_biochem_database.get_bcd_p_table(), biochem_models.BcdP)
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

            plkhedr_valid = biochem_models.Bcplanktnhedredits.objects.using('biochem').filter(batch_seq=batch_id,
                                                                                              process_flag='ENR').exists()
            plkdtai_valid = biochem_models.Bcplanktndtailedits.objects.using('biochem').filter(batch_seq=batch_id,
                                                                                               process_flag='ENR').exists()
            plkfreq_valid = biochem_models.Bcplanktnfreqedits.objects.using('biochem').filter(batch_seq=batch_id,
                                                                                              process_flag='ENR').exists()
            plkgen_valid = biochem_models.Bcplanktngenerledits.objects.using('biochem').filter(batch_seq=batch_id,
                                                                                               process_flag='ENR').exists()
            plkindi_valid = biochem_models.Bcplanktnindivdledits.objects.using('biochem').filter(batch_seq=batch_id,
                                                                                                 process_flag='ENR').exists()

            if not mission_valid and not event_valid and not plkhedr_valid and not plkdtai_valid and not plkfreq_valid and not plkgen_valid and not plkindi_valid:
                icon = BeautifulSoup(load_svg('2-square-fill'), 'html.parser').svg
                validate2_button.find('svg').decompose()
                validate2_button.append(icon)
                validate2_button.attrs['class'] = 'btn btn-sm btn-success'
                if biochem_models.Bcerrors.objects.using('biochem').filter(batch_seq=batch_id).exists():
                    validate2_button.attrs['class'] = 'btn btn-sm btn-danger'

    validate1_button.attrs['hx-get'] = reverse_lazy('core:form_biochem_plankton_validation1', args=(batch_id,))
    validate2_button.attrs['hx-get'] = reverse_lazy('core:form_biochem_plankton_validation2', args=(batch_id,))
    delete_button.attrs['hx-get'] = reverse_lazy('core:form_biochem_plankton_delete',
                                                 args=(database, mission_id, batch_id,))

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
        url = reverse_lazy('core:form_biochem_plankton_page_station_errors', args=(batch_id, (page + 1),))
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

    headers = ['Table', 'ID', 'Missing Lookup Value', 'Error']

    soup = get_table_soup('Data Errors', table_id, headers, swap_oob)
    if batch_id == 0:
        return soup

    table = soup.find('tbody')

    validation_errors = {}
    errors = biochem_models.Bcerrors.objects.using('biochem').filter(
        batch_seq=batch_id)[page_start:(page_start + _page_limit)]

    tr_header = None
    for error in errors:

        if error.error_code not in validation_errors.keys():
            err = biochem_models.Bcerrorcodes.objects.using('biochem').get(error_code=error.error_code)
            validation_errors[error.error_code] = err

        table.append(tr_header := soup.new_tag('tr'))

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(error.edit_table_name)

        plankton = None
        if error.edit_table_name.upper() == 'BCPLANKTNGENERLEDITS':
            plankton = biochem_models.Bcplanktngenerledits.objects.using('biochem').get(
                pl_general_edt_seq=error.record_num_seq,
            )

        tr_header.append(td_sample_id := soup.new_tag('td'))
        td_sample_id.string = "---"

        tr_header.append(td_taxa_name := soup.new_tag('td'))
        td_taxa_name.string = "---"
        if plankton:
            plankton_hdr = biochem_models.Bcplanktnhedredits.objects.using('biochem').get(
                pl_headr_edt_seq=plankton.pl_headr_edt_seq)
            td_sample_id.string = str(plankton_hdr.collector_sample_id)

            val = "---"
            if hasattr(biochem_models, error.edit_table_name.title()):
                model = getattr(biochem_models, error.edit_table_name.title())
                if hasattr(model, error.column_name.lower()):
                    row = model.objects.using('biochem').get(pk=error.record_num_seq)
                    val = getattr(row, error.column_name.lower())

            td_taxa_name.string = str(val)

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(validation_errors[error.error_code].long_desc)

    if tr_header:
        url = reverse_lazy('core:form_biochem_plankton_page_errors', args=(batch_id, (page + 1),))
        tr_header.attrs['hx-target'] = f'#{table_id}_tbody'
        tr_header.attrs['hx-trigger'] = 'intersect once'
        tr_header.attrs['hx-get'] = url
        tr_header.attrs['hx-swap'] = "none"

    return soup


def get_data_error_summary_table(batch_id, swap_oob=True):
    headers = ['Error Count', 'Description']

    soup = get_table_soup('Data Error Summary', 'table_id_biochem_batch_data_error_summary', headers, swap_oob)
    if batch_id == 0:
        return soup

    table = soup.find('tbody')

    validation_errors = {}
    # get all of the BCDisReplicateEdits rows that contain errors and distill them down to only unique datatypes
    error_codes = biochem_models.Bcerrors.objects.using('biochem').filter(
        batch_seq=batch_id).values_list('error_code', flat=True).distinct()

    for code in error_codes:
        if code not in validation_errors.keys():
            validation_errors[code] = biochem_models.Bcerrorcodes.objects.using('biochem').get(error_code=code)

        err = biochem_models.Bcerrors.objects.using('biochem').filter(batch_seq=batch_id, error_code=code)

        table.append(tr_header := soup.new_tag('tr'))

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(err.count())

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(validation_errors[code].long_desc)

    return soup


def page_bcs(request, batch_id, page):
    table_id = 'table_id_biochem_batch_bcs'
    return generic_table_paging(request, batch_id, page, table_id, get_bcs_table)


def get_bcs_table(batch_id, page=0, swap_oob=True):
    page_start = _page_limit * page
    table_id = "table_id_biochem_batch_bcs"

    headers = ['ID', 'Sample ID', 'Process Flag']
    soup = get_table_soup("BCS - BcPlanktonStatnEdits", table_id, headers, swap_oob)

    if batch_id == 0:
        return soup
    table = soup.find('tbody')

    table_model = upload.get_model(form_biochem_database.get_bcs_p_table(), biochem_models.BcsP)

    rows = table_model.objects.using('biochem').filter(
        batch_seq=batch_id
    ).order_by('-plank_sample_key_value')[page_start:(page_start + _page_limit)]

    tr_header = None
    for row in rows:
        table.append(tr_header := soup.new_tag('tr'))

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(row.plank_sample_key_value)

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(row.pl_headr_collector_sample_id)

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(row.process_flag)

    if tr_header:
        url = reverse_lazy('core:form_biochem_plankton_page_bcs', args=(batch_id, (page + 1),))
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

    headers = ['Record', 'ID', 'Process Flag']
    soup = get_table_soup("BCD - BcPlanktonDataEdits", table_id, headers, swap_oob)

    if batch_id == 0:
        return soup
    table = soup.find('tbody')

    table_model = upload.get_model(form_biochem_database.get_bcd_p_table(), biochem_models.BcdP)

    rows = table_model.objects.using('biochem').filter(
        batch_seq=batch_id
    ).order_by('-plank_sample_key_value')[page_start:(page_start + _page_limit)]

    tr_header = None
    for row in rows:
        table.append(tr_header := soup.new_tag('tr'))

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(row.plank_data_num)

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(row.plank_sample_key_value)

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(row.process_flag)

    if tr_header:
        url = reverse_lazy('core:form_biochem_plankton_page_bcd', args=(batch_id, (page + 1),))
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
    mission.errors.filter(type=core_models.ErrorType.biochem_plankton).delete()
    core_models.Error.objects.using(database).filter(mission=mission,
                                                     type=core_models.ErrorType.biochem_plankton).delete()

    # send_user_notification_queue('biochem', _("Validating Sensor/Sample Datatypes"))
    user_logger.info(_("Validating Plankton Data"))

    # errors = validation.validate_plankton_for_biochem(mission=mission)

    # create and upload the BCS data if it doesn't already exist
    form_biochem_database.upload_bcs_p_data(mission, uploader, batch_id)
    form_biochem_database.upload_bcd_p_data(mission, uploader, batch_id)


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

        sample_data_upload(database, mission, uploader, batch_id)
        attrs = {
            'component_id': 'div_id_upload_biochem',
            'alert_type': 'success',
            'message': _("Thank you for uploading"),
        }
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
    response['HX-Trigger'] = 'biochem_db_connect'
    return response


prefix = 'biochem/plankton'
db_prefix = f'<str:database>/<int:mission_id>/{prefix}'
database_urls = [
    path(f'{db_prefix}/upload/', upload_batch, name="form_biochem_plankton_upload_batch"),
    path(f'{db_prefix}', get_batch, name="form_biochem_plankton_update_selected_batch"),
    path(f'{db_prefix}/delete/<int:batch_id>/', run_biochem_delete_procedure, name="form_biochem_plankton_delete"),

    path(f'{prefix}/batch/<int:batch_id>/', get_batch_info, name="form_biochem_plankton_get_batch"),
    path(f'{prefix}/validate1/<int:batch_id>/', biochem_validation1_procedure, name="form_biochem_plankton_validation1"),
    path(f'{prefix}/validate2/<int:batch_id>/', biochem_validation2_procedure, name="form_biochem_plankton_validation2"),

    path(f'{prefix}/page/bcd/<int:batch_id>/<int:page>/', page_bcd, name="form_biochem_plankton_page_bcd"),
    path(f'{prefix}/page/bcs/<int:batch_id>/<int:page>/', page_bcs, name="form_biochem_plankton_page_bcs"),
    path(f'{prefix}/page/station_errors/<int:batch_id>/<int:page>/', page_data_station_errors,
         name="form_biochem_plankton_page_station_errors"),
    path(f'{prefix}/page/data_errors/<int:batch_id>/<int:page>/', page_data_errors,
         name="form_biochem_plankton_page_errors"),

]
