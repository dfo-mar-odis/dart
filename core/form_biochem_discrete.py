import logging

from bs4 import BeautifulSoup
from crispy_forms.utils import render_crispy_form
from django.core.cache import caches

from django.db import connections
from django.http import HttpResponse
from django.urls import path, reverse_lazy
from django.utils.translation import gettext as _

from settingsdb import models as settingsdb_models

from core import validation
from core import forms as core_forms
from core import models as core_models
from core import form_biochem_database
from core import form_biochem_batch

from biochem import upload
from biochem import models as biochem_models


logger = logging.getLogger('dart')
user_logger = logger.getChild('user')

_page_limit = 50


class BiochemDiscreteBatchForm(form_biochem_batch.BiochemBatchForm):
    database = None
    mission_id = None

    def get_biochem_batch_url(self):
        return reverse_lazy('core:form_biochem_discrete_update_selected_batch', args=(self.database, self.mission_id))

    def get_biochem_batch_clear_url(self):
        return reverse_lazy('core:form_biochem_discrete_get_batch',
                            args=(self.database, self.mission_id, self.batch_id))

    def get_batch_choices(self):
        mission = core_models.Mission.objects.get(pk=self.mission_id)
        table_model = upload.get_model(form_biochem_database.get_bcs_d_table(), biochem_models.BcsD)

        batch_ids = table_model.objects.using('biochem').all().values_list('batch_seq', flat=True).distinct()

        batches = biochem_models.Bcbatches.objects.using('biochem').filter(
            name=mission.mission_descriptor,
            batch_seq__in=batch_ids
        ).order_by('-batch_seq')
        self.fields['selected_batch'].choices += [(db.batch_seq, f"{db.batch_seq}: {db.name}") for db in batches]


def get_batches_form(request, database, mission_id, batch_id=0):
    batches_form_crispy = BiochemDiscreteBatchForm(database=database, mission_id=mission_id, batch_id=batch_id)
    form_url = reverse_lazy('core:form_biochem_discrete_refresh', args=(database, mission_id, batch_id))
    return form_biochem_batch.get_batches_form(request, batches_form_crispy, form_url)


def refresh_batches_form(request, database, mission_id, batch_id):
    return HttpResponse(get_batches_form(request, database, mission_id, batch_id))


def delete_discrete_proc(batch_id):
    bcd_d = upload.get_model(form_biochem_database.get_bcd_d_table(), biochem_models.BcdD)
    bcs_d = upload.get_model(form_biochem_database.get_bcs_d_table(), biochem_models.BcsD)

    form_biochem_batch.delete_batch(batch_id, 'DISCRETE', bcd_d, bcs_d)


def run_biochem_delete_procedure(request, database, mission_id, batch_id):
    crispy_form = BiochemDiscreteBatchForm(database=database, mission_id=mission_id)
    return form_biochem_batch.run_biochem_delete_procedure(request, crispy_form, batch_id, delete_discrete_proc)


def validation_proc(batch_id):
    with connections['biochem'].cursor() as cur:
        user_logger.info(f"validating station data")
        stn_pass_var = cur.callfunc("VALIDATE_DISCRETE_STATN_DATA.VALIDATE_DISCRETE_STATION", str, [batch_id])

        user_logger.info(f"validating discrete data")
        data_pass_var = cur.callfunc("VALIDATE_DISCRETE_STATN_DATA.VALIDATE_DISCRETE_DATA", str, [batch_id])

        if stn_pass_var == 'T' and data_pass_var == 'T':
            user_logger.info(f"Moving BCS/BCD data to workbench")
            cur.callfunc("POPULATE_DISCRETE_EDITS_PKG.POPULATE_DISCRETE_EDITS", str, [batch_id])
        else:
            user_logger.info(f"Errors in BCS/BCD data. Stand by for a damage report.")

        cur.execute('commit')
        cur.close()


def biochem_validation1_procedure(request, batch_id):
    return form_biochem_batch.biochem_validation1_procedure(request, batch_id, validation_proc)


def validation2_proc(batch_id, user):
    with connections['biochem'].cursor() as cur:
        user_logger.info(f"validating mission data")
        cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_MISSION_ERRORS", str, [batch_id, user])

        user_logger.info(f"validating event data")
        cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_EVENT_ERRORS", str, [batch_id, user])

        user_logger.info(f"validating discrete header data")
        cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_DISHEDR_ERRORS", str, [batch_id, user])

        user_logger.info(f"validating discrete detail data")
        cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_DISDETAIL_ERRORS", str, [batch_id, user])

        user_logger.info(f"validating discrete replicate data")
        cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_DISREPLIC_ERRORS", str, [batch_id, user])


def biochem_validation2_procedure(request, batch_id):
    return form_biochem_batch.biochem_validation2_procedure(request, batch_id, validation2_proc)


def get_batch_info(request, database, mission_id, batch_id):
    upload_url = "core:form_biochem_discrete_upload_batch"
    return form_biochem_batch.get_batch_info(request, database, mission_id, batch_id, upload_url, add_tables_to_soup)


def stage1_valid_proc(batch_id):
    mission_valid = biochem_models.Bcmissionedits.objects.using('biochem').filter(
        batch_seq=batch_id, process_flag='ENR').exists()
    event_valid = biochem_models.Bceventedits.objects.using('biochem').filter(
        batch_seq=batch_id, process_flag='ENR').exists()

    dishedr_valid = biochem_models.Bcdiscretehedredits.objects.using('biochem').filter(
        batch_seq=batch_id, process_flag='ENR').exists()
    disdtai_valid = biochem_models.Bcdiscretedtailedits.objects.using('biochem').filter(
        batch_seq=batch_id, process_flag='ENR').exists()
    disrepl_valid = biochem_models.Bcdisreplicatedits.objects.using('biochem').filter(
        batch_seq=batch_id, process_flag='ENR').exists()

    return not mission_valid and not event_valid and not dishedr_valid and not disdtai_valid and not disrepl_valid


def get_batch(request, database, mission_id):
    bcd_model = upload.get_model(form_biochem_database.get_bcd_d_table(), biochem_models.BcdD)

    attrs = {
        'request': request,
        'database': database,
        'mission_id': mission_id,
        'bcd_model': bcd_model,
        'stage1_valid_proc': stage1_valid_proc,
        'upload_url': 'core:form_biochem_discrete_upload_batch',
        'validate1_url': 'core:form_biochem_discrete_validation1',
        'validate2_url': 'core:form_biochem_discrete_validation2',
        'delete_url': 'core:form_biochem_discrete_delete',
        'add_tables_to_soup_proc': add_tables_to_soup
    }

    return form_biochem_batch.get_batch(**attrs)


def page_data_station_errors(request, batch_id, page):
    table_id = 'table_id_biochem_batch_errors'
    return form_biochem_batch.generic_table_paging(request, batch_id, page, table_id, get_station_errors_table)


def get_station_errors_table(batch_id, page=0, swap_oob=True):
    page_url = 'core:form_biochem_discrete_page_station_errors'
    return form_biochem_batch.get_station_errors_table(batch_id, page, swap_oob, page_url)


def page_data_errors(request, batch_id, page):
    table_id = 'table_id_biochem_batch_data_errors'
    return form_biochem_batch.generic_table_paging(request, batch_id, page, table_id, get_data_errors_table)


def get_data_errors_table(batch_id, page=0, swap_oob=True):
    page_start = _page_limit * page
    table_id = 'table_id_biochem_batch_data_errors'

    headers = ['Table', 'Record', 'Sample ID', 'Datatype', 'Method', 'Error']

    soup = form_biochem_batch.get_table_soup('Data Errors', table_id, headers, swap_oob)
    if batch_id == 0:
        return soup

    table = soup.find('tbody')

    validation_errors = {}
    errors = biochem_models.Bcerrors.objects.using('biochem').filter(
        batch_seq=batch_id)[page_start:(page_start + _page_limit)]

    if errors.count() > 0:
        table_scroll = soup.find('div', {'id': f'div_id_{table_id}_scroll'})
        table_scroll.attrs['class'] = 'tscroll horizontal-scrollbar vertical-scrollbar'

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


def add_errors_to_table(soup, errors, table_name, table_key):
    validation_errors = {}
    table = soup.find('tbody')

    for code in errors.values_list('data_type_seq', flat=True).distinct():
        data_type_errors = errors.filter(
            data_type_seq=code,
        )

        key = data_type_errors.first()
        error = biochem_models.Bcerrors.objects.using('biochem').get(record_num_seq=getattr(key, table_key))
        datatype = biochem_models.Bcdatatypes.objects.using('biochem').get(data_type_seq=key.data_type_seq)

        table.append(tr_header := soup.new_tag('tr'))

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(data_type_errors.count())

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(datatype.data_type_seq)

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(table_name)

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(datatype.method)

        tr_header.append(td := soup.new_tag('td'))

        if error.error_code not in validation_errors.keys():
            err = biochem_models.Bcerrorcodes.objects.using('biochem').get(error_code=error.error_code)
            validation_errors[error.error_code] = err

        td.string = str(validation_errors[error.error_code].long_desc)

    return validation_errors


def get_data_error_summary_table(batch_id, swap_oob=True):
    headers = ['Error Count', 'Datatype', 'Table', 'Description', 'Error']

    table_id = 'table_id_biochem_batch_data_error_summary'
    soup = form_biochem_batch.get_table_soup('Data Error Summary', table_id, headers, swap_oob)
    if batch_id == 0:
        return soup

    validation_errors = {}
    # get all of the BCDisReplicateEdits rows that contain errors and distill them down to only unique datatypes
    errors = biochem_models.Bcdisreplicatedits.objects.using('biochem').filter(
        batch_seq=batch_id,
        process_flag__iexact='err'
    )

    validation_errors.update(add_errors_to_table(soup, errors, 'BCDISREPLICATEDITS', 'dis_repl_edt_seq'))

    errors = biochem_models.Bcdiscretedtailedits.objects.using('biochem').filter(
        batch_seq=batch_id,
        process_flag__iexact='err'
    )

    validation_errors.update(add_errors_to_table(soup, errors, 'BCDISCRETEDTAILEDITS', 'dis_detail_edt_seq'))

    if len(soup.find("tbody").findAll('tr')) > 0:
        table_scroll = soup.find('div', {'id': f'div_id_{table_id}_scroll'})
        table_scroll.attrs['class'] = 'tscroll horizontal-scrollbar vertical-scrollbar'

    return soup


def page_bcs(request, batch_id, page):
    table_id = 'table_id_biochem_batch_bcs'
    return form_biochem_batch.generic_table_paging(request, batch_id, page, table_id, get_bcs_table)


def get_bcs_table(batch_id, page=0, swap_oob=True):
    page_start = _page_limit * page
    table_id = "table_id_biochem_batch_bcs"

    headers = ['ID', 'Process Flag']
    soup = form_biochem_batch.get_table_soup("BCS - BcDiscreteStatnEdits", table_id, headers, swap_oob)

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
    return form_biochem_batch.generic_table_paging(request, batch_id, page, table_id, get_bcd_table)


def get_bcd_table(batch_id, page=0, swap_oob=True):
    page_start = _page_limit * page
    table_id = "table_id_biochem_batch_bcd"

    headers = ['ID', 'Record', 'Sample ID', 'Data Type', 'Data Method', 'Process Flag']
    soup = form_biochem_batch.get_table_soup("BCD - BcDiscreteDataEdits", table_id, headers, swap_oob)

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

        tr_header.append(td_sample_ke := soup.new_tag('td'))
        td_sample_ke.string = str(row.dis_sample_key_value)

        tr_header.append(td_record := soup.new_tag('td'))
        td_record.string = str(row.dis_data_num)

        tr_header.append(td_sample_id := soup.new_tag('td'))
        td_sample_id.string = str(row.dis_detail_collector_samp_id)

        tr_header.append(td_detail_data_type := soup.new_tag('td'))
        td_detail_data_type.string = str(row.dis_detail_data_type_seq)

        tr_header.append(td_data_type := soup.new_tag('td'))
        td_data_type.string = str(row.data_type_method)

        tr_header.append(td_process := soup.new_tag('td'))
        td_process.string = str(row.process_flag)

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
    core_models.Error.objects.filter(mission=mission, type=core_models.ErrorType.biochem).delete()

    # send_user_notification_queue('biochem', _("Validating Sensor/Sample Datatypes"))
    user_logger.info(_("Validating Sensor/Sample Datatypes"))
    samples_types_for_upload = [bcupload.type for bcupload in
                                core_models.BioChemUpload.objects.filter(type__mission=mission)]

    # Todo: I'm running the standard DART based event/data validation here, but we probably should be running the
    #  BioChem Validation from core.form_validation_biochem.run_biochem_validation()
    errors = validation.validate_samples_for_biochem(mission=mission, sample_types=samples_types_for_upload)

    if errors:
        # send_user_notification_queue('biochem', _("Datatypes missing see errors"))
        user_logger.info(_("Datatypes missing see errors"))
        core_models.Error.objects.bulk_create(errors)

    # create and upload the BCS data if it doesn't already exist
    form_biochem_database.upload_bcs_d_data(mission, uploader, batch_id)
    form_biochem_database.upload_bcd_d_data(mission, uploader, batch_id)

    return batch_id


def upload_batch(request, database, mission_id):
    mission = core_models.Mission.objects.get(pk=mission_id)

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

        form = BiochemDiscreteBatchForm(database=database, mission_id=mission_id, batch_id=batch_id)
        html = render_crispy_form(form)
        batch_form_soup = BeautifulSoup(html, 'html.parser')

        select = batch_form_soup.find('select', attrs={'id': "control_id_database_select_biochem_batch_details"})
        select.attrs['hx-swap-oob'] = 'true'
        select.attrs['hx-trigger'] = 'load, change, reload_batch from:body'

        soup.append(select)

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
    response['HX-Trigger'] = 'update_samples'
    return response


prefix = 'biochem/discrete'
db_prefix = f'<str:database>/<int:mission_id>/{prefix}'
database_urls = [
    path(f'{db_prefix}/upload/', upload_batch, name="form_biochem_discrete_upload_batch"),
    path(f'{db_prefix}/batch/', get_batch, name="form_biochem_discrete_update_selected_batch"),
    path(f'{db_prefix}/batch/<int:batch_id>/', get_batch_info, name="form_biochem_discrete_get_batch"),
    path(f'{db_prefix}/delete/<int:batch_id>/', run_biochem_delete_procedure, name="form_biochem_discrete_delete"),
    path(f'{db_prefix}/form/<int:batch_id>/', refresh_batches_form, name="form_biochem_discrete_refresh"),

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
