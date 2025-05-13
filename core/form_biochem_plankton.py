import logging

from datetime import datetime
from bs4 import BeautifulSoup
from crispy_forms.utils import render_crispy_form

from django.db import connections
from django.http import HttpResponse
from django.urls import path, reverse_lazy
from django.utils.translation import gettext as _

from core import forms as core_forms
from core import models as core_models
from core import form_biochem_database
from core import form_biochem_batch

from biochem import upload
from biochem import models as biochem_models
from biochem import MergeTables

logger = logging.getLogger('dart')
user_logger = logger.getChild('user')

_page_limit = 50


class BiochemPlanktonBatchForm(form_biochem_batch.BiochemBatchForm):
    mission_id = None

    def get_biochem_batch_url(self):
        return reverse_lazy('core:form_biochem_plankton_update_selected_batch', args=(self.mission_id,))

    def get_biochem_batch_clear_url(self):
        return reverse_lazy('core:form_biochem_plankton_get_batch', args=(self.mission_id, self.batch_id,))

    def get_batch_choices(self):
        mission = core_models.Mission.objects.get(pk=self.mission_id)
        table_model = upload.get_model(form_biochem_database.get_bcs_p_table(), biochem_models.BcsP)

        batch_ids = table_model.objects.using('biochem').all().values_list('batch', flat=True).distinct()

        # get batches that exist in the "edit" tables
        edit_batches = biochem_models.Bcbatches.objects.using('biochem').filter(
            name=mission.mission_descriptor,
            activity_edits__data_pointer_code__iexact='PL'
            # batch_seq__in=batch_ids
        ).distinct().order_by('-batch_seq')

        self.fields['selected_batch'].choices += [(db.batch_seq, f"{db.batch_seq}: {db.name}") for db in edit_batches]

        # get batches that exist in the BCS/BCD tables, excluding batches in the edit tables
        batches = biochem_models.Bcbatches.objects.using('biochem').filter(
            plankton_station_edits__mission_descriptor__iexact=mission.mission_descriptor
        ).exclude(pk__in=edit_batches).distinct().order_by('-batch_seq')

        self.fields['selected_batch'].choices += [(db.batch_seq, f"{db.batch_seq}: {db.name}") for db in batches]


def get_batches_form(request, mission_id, batch_id=0):
    batches_form_crispy = BiochemPlanktonBatchForm(mission_id=mission_id, batch_id=batch_id)
    form_url = reverse_lazy('core:form_biochem_plankton_refresh', args=(mission_id, batch_id,))
    return form_biochem_batch.get_batches_form(request, batches_form_crispy, form_url)


def refresh_batches_form(request, mission_id, batch_id):
    return HttpResponse(get_batches_form(request, mission_id, batch_id))


def delete_plankton_proc(batch_id):
    bcd_p = upload.get_model(form_biochem_database.get_bcd_p_table(), biochem_models.BcdP)
    bcs_p = upload.get_model(form_biochem_database.get_bcs_p_table(), biochem_models.BcsP)

    form_biochem_batch.delete_batch(batch_id, 'PLANKTON', bcd_p, bcs_p)


def run_biochem_delete_procedure(request, mission_id, batch_id):
    crispy_form = BiochemPlanktonBatchForm(mission_id=mission_id)
    return form_biochem_batch.run_biochem_delete_procedure(request, crispy_form, batch_id, delete_plankton_proc)


def checkout_existing_mission(mission: biochem_models.Bcmissionedits) -> biochem_models.Bcmissions | None:
    return_status = ''
    return_value = ''

    # if the mission doesn't have discrete headers, then it doesn't belong here in form_biochem_discrete
    headers = biochem_models.Bcplanktnhedrs.objects.using('biochem').filter(
        event__mission__descriptor__iexact=mission.descriptor)

    if headers.exists():
        bc_mission = headers.first().event.mission
        mission_seq = bc_mission.mission_seq

        # Check if the mission with the mission_seq is already checked out to the users edit tables
        user_missions = biochem_models.Bcmissionedits.objects.using('biochem').filter(mission=bc_mission)
        if not user_missions.exists():
            # If not checked out, check if the mission with mission_seq is in the BCLockedMissions table
            # If in the locked missions table and not in the users table we shouldn't be deleting or overriding
            if hasattr(bc_mission, 'locked_missions'):
                msg = f"'{bc_mission.locked_missions.downloaded_by}' " + _("already has this mission checked out. "
                        "Mission needs to be released from BCLockedMissions before it can be modified.")
                raise PermissionError(msg)

            # Todo: There's also a case where there could be multiple versions of a mission in the Archive.
            #       In this case I only retrieve the first mission that matches the mission.mission_descriptor,
            #       but I don't think this is the right thing to do, I'll need to ask.
            # check it out to the edit tables.
            with connections['biochem'].cursor() as cur:
                user_logger.info(f"Archiving existing mission with matching descriptor {mission_seq}")
                return_value = cur.callproc("Download_Plankton_Mission", [mission_seq, return_status])

            if return_value[1] is None:
                biochem_models.Bclockedmissions.objects.using('biochem').create(
                    mission = bc_mission,
                    mission_name = bc_mission.name,
                    descriptor = bc_mission.descriptor,
                    data_pointer_code = "PL",  # reference to BCDataPointers table - "DH" for discrete, "PL" for plankton
                    downloaded_by = form_biochem_database.get_uploader(),
                    downloaded_date = datetime.now()).save(using='biochem')
                return bc_mission
        else:
            return user_missions.first().mission

    return None


def checkin_batch_proc(batch_id: int):
    return_status = ''
    return_value = ''

    # check for existing mission matching this batch and check it out to the user edit tables if it exists
    # This is to create a backup which the user can then recover from if something goes wrong.
    batch = biochem_models.Bcbatches.objects.using('biochem').get(batch_seq=batch_id)
    batch_mission_edit = batch.mission_edits.first()

    bc_mission: biochem_models.Bcmissions = checkout_existing_mission(batch_mission_edit)

    validation2_proc(batch_id)

    # check in new mission
    with connections['biochem'].cursor() as cur:
        user_logger.info(f"Uploading new mission with batch id {batch_id}")
        return_value = cur.callproc("ARCHIVE_BATCH.ARCHIVE_PLANKTON_BATCH", [batch_id, return_status])

    # if the checkin fails release the old mission and delete it from the edit tables
    # if successful delete the new mission from the edit tables, but keep the old one.
    if return_value[1] is not None:
        user_logger.error(f"Issues with archiving mission: {return_value[1]}")
        raise ValueError(return_value[1])

    # if the mission exists in the lock tables and there was no problem archiving it,
    # then remove it from the locked table
    if bc_mission and bc_mission.locked_missions:
        bc_mission.locked_missions.delete()

    delete_plankton_proc(batch_id)


# return the batch id of the mission_edits the selected batch was merged into if the merge was completed successfully,
# None if now merge occurred or there was an error
def merge_batch_proc(batch_id: int) -> int | None:
    batch = biochem_models.Bcbatches.objects.using('biochem').get(batch_seq=batch_id)
    batch_mission_edit = batch.mission_edits.first()

    # check out an existing mission if one exists
    bc_mission: biochem_models.Bcmissions = checkout_existing_mission(batch_mission_edit)
    bc_mission_edit = bc_mission.mission_edits if hasattr(bc_mission, 'mission_edits') else None

    if bc_mission_edit and bc_mission != batch_mission_edit:
        table_merge = MergeTables.MergeMissions(bc_mission_edit, batch_mission_edit)
        table_merge.add_status_listener(form_biochem_batch.status_update)
        table_merge.merge_missions()

        # Todo: assume the merged completed successfully for now. Exception handling later
        #       but if the merge completes successfully, then we'll want to swap the batch the user is looking at over
        #       to the checked out mission that we just merged our new data into
        return bc_mission_edit.batch.batch_seq

    return False


def validation_proc(batch_id):
    with connections['biochem'].cursor() as cur:
        user_logger.info(f"validating station data")
        stn_pass_var = cur.callfunc("VALIDATE_PLANKTON_STATN_DATA.VALIDATE_PLANKTON_STATION", str, [batch_id])

        user_logger.info(f"validating plankton data")
        data_pass_var = cur.callfunc("VALIDATE_PLANKTON_STATN_DATA.VALIDATE_PLANKTON_DATA", str, [batch_id])

        if stn_pass_var == 'T' and data_pass_var == 'T':
            user_logger.info(f"Moving BCS/BCD data to workbench")
            cur.callfunc("POPULATE_PLANKTON_EDITS_PKG.POPULATE_PLANKTON_EDITS", str, [batch_id])
        else:
            user_logger.info(f"Errors in BCS/BCD data. Stand by for a damage report.")

        cur.execute('commit')
        cur.close()


def biochem_validation1_procedure(request, batch_id):
    return form_biochem_batch.biochem_validation1_procedure(request, batch_id, validation_proc)


def validation2_proc(batch_id):
    user = form_biochem_database.get_uploader()
    with connections['biochem'].cursor() as cur:
        user_logger.info(f"validating mission data")
        cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_MISSION_ERRORS", str, [batch_id, user])

        user_logger.info(f"validating event data")
        cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_EVENT_ERRORS", str, [batch_id, user])

        user_logger.info(f"validating plankton header data")
        cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_PLANK_HEDR_ERRORS", str, [batch_id, user])

        user_logger.info(f"validating plankton general data")
        cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_PLANK_GENERL_ERRS", str, [batch_id, user])

        user_logger.info(f"validating plankton details data")
        cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_PLANK_DTAIL_ERRS", str, [batch_id, user])

        user_logger.info(f"validating plankton details data")
        cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_PLANK_FREQ_ERRS", str, [batch_id, user])

        user_logger.info(f"validating plankton replicate data")
        cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_PLANK_INDIV_ERRS", str, [batch_id, user])


def biochem_validation2_procedure(request, batch_id):
    return form_biochem_batch.biochem_validation2_procedure(request, batch_id, validation2_proc)


def biochem_checkin_procedure(request, batch_id):
    return form_biochem_batch.biochem_checkin_procedure(request, batch_id, checkin_batch_proc)


def biochem_merge_procedure(request, mission_id, batch_id):
    crispy_form = BiochemPlanktonBatchForm(mission_id=mission_id, batch_id=batch_id)
    return form_biochem_batch.biochem_merge_procedure(request, crispy_form, batch_id, merge_batch_proc)


def get_batch_info(request, mission_id, batch_id):
    upload_url = "core:form_biochem_plankton_upload_batch"
    return form_biochem_batch.get_batch_info(request, mission_id, batch_id, upload_url, add_tables_to_soup)


def stage1_valid_proc(batch_id):
    mission_valid = biochem_models.Bcmissionedits.objects.using('biochem').filter(
        batch=batch_id,  process_flag='ENR').exists()
    event_valid = biochem_models.Bceventedits.objects.using('biochem').filter(
        batch=batch_id, process_flag='ENR').exists()

    plkhedr_valid = biochem_models.Bcplanktnhedredits.objects.using('biochem').filter(
        batch=batch_id, process_flag='ENR').exists()
    plkdtai_valid = biochem_models.Bcplanktndtailedits.objects.using('biochem').filter(
        batch=batch_id, process_flag='ENR').exists()
    plkfreq_valid = biochem_models.Bcplanktnfreqedits.objects.using('biochem').filter(
        batch=batch_id, process_flag='ENR').exists()
    plkgen_valid = biochem_models.Bcplanktngenerledits.objects.using('biochem').filter(
        batch=batch_id, process_flag='ENR').exists()
    plkindi_valid = biochem_models.Bcplanktnindivdledits.objects.using('biochem').filter(
        batch=batch_id, process_flag='ENR').exists()

    return not mission_valid and not event_valid and not plkhedr_valid and not plkdtai_valid and not plkfreq_valid and not plkgen_valid and not plkindi_valid


def get_batch(request, mission_id):
    bcd_model = upload.get_model(form_biochem_database.get_bcd_p_table(), biochem_models.BcdP)

    attrs = {
        'request': request,
        'mission_id': mission_id,
        'bcd_model': bcd_model,
        'stage1_valid_proc': stage1_valid_proc,
        'upload_url': 'core:form_biochem_plankton_upload_batch',
        'validate1_url': 'core:form_biochem_plankton_validation1',
        'validate2_url': 'core:form_biochem_plankton_validation2',
        'checkin_url': 'core:form_biochem_plankton_checkin',
        'merge_url': 'core:form_biochem_plankton_merge',
        'delete_url': 'core:form_biochem_plankton_delete',
        'add_tables_to_soup_proc': add_tables_to_soup
    }

    return form_biochem_batch.get_batch(**attrs)


def page_data_station_errors(request, batch_id, page):
    table_id = 'table_id_biochem_batch_errors'
    return form_biochem_batch.generic_table_paging(request, batch_id, page, table_id, get_station_errors_table)


def get_station_errors_table(batch_id, page=0, swap_oob=True):
    page_url = 'core:form_biochem_plankton_page_station_errors'
    return form_biochem_batch.get_station_errors_table(batch_id, page, swap_oob, page_url)


def page_data_errors(request, batch_id, page):
    table_id = 'table_id_biochem_batch_data_errors'
    return form_biochem_batch.generic_table_paging(request, batch_id, page, table_id, get_data_errors_table)


def get_data_errors_table(batch_id, page=0, swap_oob=True):
    page_start = _page_limit * page
    table_id = 'table_id_biochem_batch_data_errors'

    headers = ['Table', 'ID', 'Missing Lookup Value', 'Error']

    soup = form_biochem_batch.get_table_soup('Data Errors', table_id, headers, swap_oob)
    if batch_id == 0:
        return soup

    table = soup.find('tbody')

    validation_errors = {}
    errors = biochem_models.Bcerrors.objects.using('biochem').filter(
        batch=batch_id)[page_start:(page_start + _page_limit)]

    if errors.count() > 0:
        table_scroll = soup.find('div', {'id': f'div_id_{table_id}_scroll'})
        table_scroll.attrs['class'] = 'tscroll horizontal-scrollbar vertical-scrollbar'

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
                pl_headr_edt_seq=plankton.pl_header_edit.pk)
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

    soup = form_biochem_batch.get_table_soup('Data Error Summary',
                                             'table_id_biochem_batch_data_error_summary', headers, swap_oob)
    if batch_id == 0:
        return soup

    table = soup.find('tbody')

    validation_errors = {}
    # get all of the BCDisReplicateEdits rows that contain errors and distill them down to only unique datatypes
    error_codes = biochem_models.Bcerrors.objects.using('biochem').filter(
        batch=batch_id).values_list('error_code', flat=True).distinct()

    for code in error_codes:
        if code not in validation_errors.keys():
            validation_errors[code] = biochem_models.Bcerrorcodes.objects.using('biochem').get(error_code=code)

        err = biochem_models.Bcerrors.objects.using('biochem').filter(batch=batch_id, error_code=code)

        table.append(tr_header := soup.new_tag('tr'))

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(err.count())

        tr_header.append(td := soup.new_tag('td'))
        td.string = str(validation_errors[code].long_desc)

    return soup


def page_bcs(request, batch_id, page):
    table_id = 'table_id_biochem_batch_bcs'
    return form_biochem_batch.generic_table_paging(request, batch_id, page, table_id, get_bcs_table)


def get_bcs_table(batch_id, page=0, swap_oob=True):
    page_start = _page_limit * page
    table_id = "table_id_biochem_batch_bcs"

    headers = ['ID', 'Sample ID', 'Process Flag']
    soup = form_biochem_batch.get_table_soup("BCS - BcPlanktonStatnEdits", table_id, headers, swap_oob)

    if batch_id == 0:
        return soup
    table = soup.find('tbody')

    table_model = upload.get_model(form_biochem_database.get_bcs_p_table(), biochem_models.BcsP)

    rows = table_model.objects.using('biochem').filter(
        batch=batch_id
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
    return form_biochem_batch.generic_table_paging(request, batch_id, page, table_id, get_bcd_table)


def get_bcd_table(batch_id, page=0, swap_oob=True):
    page_start = _page_limit * page
    table_id = "table_id_biochem_batch_bcd"

    headers = ['Record', 'ID', 'Process Flag']
    soup = form_biochem_batch.get_table_soup("BCD - BcPlanktonDataEdits", table_id, headers, swap_oob)

    if batch_id == 0:
        return soup
    table = soup.find('tbody')

    table_model = upload.get_model(form_biochem_database.get_bcd_p_table(), biochem_models.BcdP)

    rows = table_model.objects.using('biochem').filter(
        batch=batch_id
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


def sample_data_upload( mission: core_models.Mission, uploader: str, batch: biochem_models.Bcbatches):
    # clear previous errors if there were any from the last upload attempt
    mission.errors.filter(type=core_models.ErrorType.biochem_plankton).delete()
    core_models.Error.objects.filter(mission=mission,
                                                     type=core_models.ErrorType.biochem_plankton).delete()

    # send_user_notification_queue('biochem', _("Validating Sensor/Sample Datatypes"))
    user_logger.info(_("Validating Plankton Data"))

    # errors = validation.validate_plankton_for_biochem(mission=mission)

    # create and upload the BCS data if it doesn't already exist
    form_biochem_database.upload_bcs_p_data(mission, uploader, batch)
    form_biochem_database.upload_bcd_p_data(mission, uploader, batch)


def upload_batch(request, mission_id):
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

    connected_database = form_biochem_database.get_connected_database()

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

        batch_id = form_biochem_batch.get_mission_batch_id()
        batch = biochem_models.Bcbatches.objects.using('biochem').get_or_create(name=mission.mission_descriptor,
                                                                        username=uploader,
                                                                        batch_seq=batch_id)[0]

        sample_data_upload(mission, uploader, batch)
        attrs = {
            'component_id': 'div_id_upload_biochem',
            'alert_type': 'success',
            'message': _("Thank you for uploading"),
        }
        form = BiochemPlanktonBatchForm(mission_id=mission_id, batch_id=batch_id)
        html = render_crispy_form(form)
        batch_form_soup = BeautifulSoup(html, 'html.parser')

        select = batch_form_soup.find('select', attrs={'id': "control_id_database_select_biochem_batch_details"})
        select.attrs['hx-swap-oob'] = 'true'
        select.attrs['hx-trigger'] = 'load, change, reload_batch from:body'

        soup.append(select)
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
    return response


prefix = 'biochem/plankton'
db_prefix = f'<str:database>/<int:mission_id>/{prefix}'
database_urls = [
    path(f'<int:mission_id>/{prefix}/upload/', upload_batch, name="form_biochem_plankton_upload_batch"),
    path(f'<int:mission_id>/{prefix}/batch/', get_batch, name="form_biochem_plankton_update_selected_batch"),
    path(f'<int:mission_id>/{prefix}/batch/<int:batch_id>/', get_batch_info, name="form_biochem_plankton_get_batch"),
    path(f'<int:mission_id>/{prefix}/delete/<int:batch_id>/', run_biochem_delete_procedure, name="form_biochem_plankton_delete"),
    path(f'<int:mission_id>/{prefix}/form/<int:batch_id>/', refresh_batches_form, name="form_biochem_plankton_refresh"),

    path(f'{prefix}/validate1/<int:batch_id>/', biochem_validation1_procedure, name="form_biochem_plankton_validation1"),
    path(f'{prefix}/validate2/<int:batch_id>/', biochem_validation2_procedure, name="form_biochem_plankton_validation2"),
    path(f'{prefix}/checkin/<int:batch_id>/', biochem_checkin_procedure,
         name="form_biochem_plankton_checkin"),
    path(f'<int:mission_id>/{prefix}/merge/<int:batch_id>/', biochem_merge_procedure, name="form_biochem_plankton_merge"),
    path(f'{prefix}/page/bcd/<int:batch_id>/<int:page>/', page_bcd, name="form_biochem_plankton_page_bcd"),
    path(f'{prefix}/page/bcs/<int:batch_id>/<int:page>/', page_bcs, name="form_biochem_plankton_page_bcs"),
    path(f'{prefix}/page/station_errors/<int:batch_id>/<int:page>/', page_data_station_errors,
         name="form_biochem_plankton_page_station_errors"),
    path(f'{prefix}/page/data_errors/<int:batch_id>/<int:page>/', page_data_errors,
         name="form_biochem_plankton_page_errors"),

]
