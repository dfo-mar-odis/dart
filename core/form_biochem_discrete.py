import csv
import logging
import os
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup
from django.conf import settings

from django.db import connections
from django.http import HttpResponse
from django.urls import path, reverse_lazy
from django.utils.translation import gettext as _

from core import validation
from core import forms as core_forms
from core import models as core_models
from core import form_biochem_database, form_biochem_batch

from biochem import upload, MergeTables
from biochem import models as biochem_models


logger = logging.getLogger('dart')
user_logger = logger.getChild('user')

_page_limit = 50


class BiochemDiscreteBatchForm(form_biochem_batch.BiochemBatchForm):
    mission_id = None

    def get_download_button(self, url=None):
        url = url if url else reverse_lazy('core:form_biochem_discrete_download_batch', args=(self.mission_id,))
        return super().get_download_button(url)

    def get_upload_button(self, url=None):
        url = url if url else reverse_lazy('core:form_biochem_discrete_upload_batch', args=(self.mission_id,))
        return super().get_upload_button(url)

    def get_validate_stage1_button(self, url=None):
        url = url if url else reverse_lazy('core:form_biochem_discrete_validation1', args=(self.batch_id,))
        return super().get_validate_stage1_button(url)

    def get_validate_stage2_button(self, url=None):
        url = url if url else reverse_lazy('core:form_biochem_discrete_validation2', args=(self.batch_id,))
        return super().get_validate_stage2_button(url)

    def get_merge_button(self, url=None):
        url = url if url else reverse_lazy('core:form_biochem_discrete_merge', args=(self.mission_id, self.batch_id,))
        return super().get_merge_button(url)

    def get_checkin_button(self, url=None):
        url = url if url else reverse_lazy('core:form_biochem_discrete_checkin', args=(self.batch_id,))
        return super().get_checkin_button(url)

    def get_delete_button(self, url=None):
        url = url if url else reverse_lazy('core:form_biochem_discrete_delete', args=(self.mission_id, self.batch_id,))
        return super().get_delete_button(url)

    def get_biochem_batch_clear_url(self):
        return reverse_lazy('core:form_biochem_discrete_get_batch', args=(self.mission_id, self.batch_id,))

    def get_batch_select(self, url=None):
        url = reverse_lazy('core:form_biochem_discrete_update_selected_batch', args=(self.mission_id,))
        return super().get_batch_select(url)

    def get_batch_choices(self):
        mission = core_models.Mission.objects.get(pk=self.mission_id)
        # table_model = upload.get_model(form_biochem_database.get_bcs_d_table(), biochem_models.BcsD)

        # batch_ids = table_model.objects.using('biochem').all().values_list('batch', flat=True).distinct()

        edit_batches = biochem_models.Bcbatches.objects.using('biochem').filter(
            name=mission.mission_descriptor,
            activity_edits__data_pointer_code__iexact='DH'
            # batch_seq__in=batch_ids
        ).distinct().order_by('-batch_seq')
        self.fields['selected_batch'].choices += [(db.batch_seq, f"{db.batch_seq}: {db.name}") for db in edit_batches]

        # get batches that exist in the BCS/BCD tables, excluding batches in the edit tables
        batches = biochem_models.Bcbatches.objects.using('biochem').filter(
            discrete_station_edits__mission_descriptor__iexact=mission.mission_descriptor
        ).exclude(pk__in=edit_batches).distinct().order_by('-batch_seq')

        self.fields['selected_batch'].choices += [(db.batch_seq, f"{db.batch_seq}: {db.name}") for db in batches]


def get_batches_form(request, mission_id, batch_id=0):
    batches_form_crispy = BiochemDiscreteBatchForm(mission_id=mission_id, batch_id=batch_id)
    form_url = reverse_lazy('core:form_biochem_discrete_refresh', args=(mission_id, batch_id,))
    return form_biochem_batch.get_batches_form(request, batches_form_crispy, form_url)


def refresh_batches_form(request, mission_id, batch_id):
    return HttpResponse(get_batches_form(request, mission_id, batch_id))


def delete_discrete_proc(batch_id):
    bcd_d = upload.get_model(form_biochem_database.get_bcd_d_table(), biochem_models.BcdD)
    bcs_d = upload.get_model(form_biochem_database.get_bcs_d_table(), biochem_models.BcsD)

    form_biochem_batch.delete_batch(batch_id, 'DISCRETE', bcd_d, bcs_d)


def run_biochem_delete_procedure(request, mission_id, batch_id):

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
            'hx-swap': 'none'
        }
        div_alert_area.append(core_forms.websocket_post_request_alert(**attrs))

        return HttpResponse(soup)

    delete_discrete_proc(batch_id)

    response = HttpResponse(soup)
    response['Hx-Trigger'] = 'refresh_form'
    return response


def checkout_existing_mission(mission: biochem_models.Bcmissionedits) -> biochem_models.Bcmissions | None:
    return_status = ''
    return_value = ''

    # if the mission doesn't have discrete headers, then it doesn't belong here in form_biochem_discrete
    headers = biochem_models.Bcdiscretehedrs.objects.using('biochem').filter(
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
                return_value = cur.callproc("Download_Discrete_Mission", [mission_seq, return_status])

            if return_value[1] is None:
                biochem_models.Bclockedmissions.objects.using('biochem').create(
                    mission = bc_mission,
                    mission_name = bc_mission.name,
                    descriptor = bc_mission.descriptor,
                    data_pointer_code = "DH",  # reference to BCDataPointers table - "DH" for discrete, "PL" for plankton
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
        return_value = cur.callproc("ARCHIVE_BATCH.ARCHIVE_DISCRETE_BATCH", [batch_id, return_status])

    # if the checkin fails release the old mission and delete it from the edit tables
    # if successful delete the new mission from the edit tables, but keep the old one.
    if return_value[1] is not None:
        user_logger.error(f"Issues with archiving mission: {return_value[1]}")
        raise ValueError(return_value[1])

    # if the mission exists in the lock tables and there was no problem archiving it,
    # then remove it from the locked table
    if bc_mission and bc_mission.locked_missions:
        bc_mission.locked_missions.delete()

    delete_discrete_proc(batch_id)


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


def validation2_proc(batch_id):
    user = form_biochem_database.get_uploader()
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


def biochem_checkin_procedure(request, batch_id):
    return form_biochem_batch.biochem_checkin_procedure(request, batch_id, checkin_batch_proc)


def biochem_merge_procedure(request, mission_id, batch_id):
    crispy_form = BiochemDiscreteBatchForm(mission_id=mission_id, batch_id=batch_id)
    return form_biochem_batch.biochem_merge_procedure(request, crispy_form, batch_id, merge_batch_proc)


def get_batch_info(request, mission_id, batch_id):
    batch_from = BiochemDiscreteBatchForm(mission_id=mission_id, batch_id=batch_id, swap_oob=True)

    soup = form_biochem_batch.get_batch_info(batch_from)
    add_tables_to_soup(soup, batch_id, False)

    return HttpResponse(soup)


def stage1_valid_proc(batch_id):
    mission_valid = biochem_models.Bcmissionedits.objects.using('biochem').filter(
        batch=batch_id, process_flag='ENR').exists()
    event_valid = biochem_models.Bceventedits.objects.using('biochem').filter(
        batch=batch_id, process_flag='ENR').exists()

    dishedr_valid = biochem_models.Bcdiscretehedredits.objects.using('biochem').filter(
        batch=batch_id, process_flag='ENR').exists()
    disdtai_valid = biochem_models.Bcdiscretedtailedits.objects.using('biochem').filter(
        batch=batch_id, process_flag='ENR').exists()
    disrepl_valid = biochem_models.Bcdisreplicatedits.objects.using('biochem').filter(
        batch=batch_id, process_flag='ENR').exists()

    return not mission_valid and not event_valid and not dishedr_valid and not disdtai_valid and not disrepl_valid


def get_batch(request, mission_id):

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
            'hx-swap': 'none'
        }
        div_alert_area.append(core_forms.websocket_post_request_alert(**attrs))

        return HttpResponse(soup)

    div_alert_area.attrs['hx-swap'] = 'innerHTML'

    batch_id = request.POST.get('selected_batch', None)
    batch_form = BiochemDiscreteBatchForm(mission_id=mission_id, batch_id=batch_id, swap_oob=True)

    bcd_model = upload.get_model(form_biochem_database.get_bcd_d_table(), biochem_models.BcdD)

    soup = form_biochem_batch.get_batch(soup, batch_form, bcd_model, stage1_valid_proc)

    add_tables_to_soup(soup, batch_form.batch_id)

    return HttpResponse(soup)


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
        batch=batch_id)[page_start:(page_start + _page_limit)]

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
            td_sample_type.string = str(replicate.data_type)

            datatype = biochem_models.Bcdatatypes.objects.using('biochem').get(data_type_seq=replicate.data_type.pk)
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

    for code in errors.values_list('data_type', flat=True).distinct():
        data_type_errors = errors.filter(
            data_type=code,
        )

        key = data_type_errors.first()
        error = biochem_models.Bcerrors.objects.using('biochem').get(record_num_seq=getattr(key, table_key))
        datatype = biochem_models.Bcdatatypes.objects.using('biochem').get(data_type_seq=key.data_type.pk)

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
        batch=batch_id,
        process_flag__iexact='err'
    )

    validation_errors.update(add_errors_to_table(soup, errors, 'BCDISREPLICATEDITS', 'dis_repl_edt_seq'))

    errors = biochem_models.Bcdiscretedtailedits.objects.using('biochem').filter(
        batch=batch_id,
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
        batch__batch_seq=batch_id
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
        batch__batch_seq=batch_id
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


def sample_data_upload(mission: core_models.Mission, batch: biochem_models.Bcbatches):
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
    form_biochem_database.upload_bcs_d_data(mission, batch)
    form_biochem_database.upload_bcd_d_data(mission, batch)


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

    # do we have an uploader?
    uploader = form_biochem_database.get_uploader()

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

        bc_statn_data_errors = []
        # user_logger.info(_("Running Biochem validation on Batch") + f" : {batch_id}")
        # bc_statn_data_errors = run_biochem_validation_procedure(batch_id, mission.mission_descriptor)

        sample_data_upload(mission, batch)

        attrs = {
            'component_id': 'div_id_upload_biochem',
            'alert_type': 'success',
            'message': _("Thank you for uploading"),
        }

        discrete_batch_form = BiochemDiscreteBatchForm(mission_id=mission_id, batch_id=batch_id)
        select = form_biochem_batch.set_selected_batch(discrete_batch_form)
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


def download_batch(request, mission_id):
    soup = BeautifulSoup('', 'html.parser')
    div = soup.new_tag('div')
    div.attrs = {
        'id': BiochemDiscreteBatchForm.get_batch_alert_area_id(),
        'hx-swap-oob': 'true'
    }
    soup.append(div)

    mission = core_models.Mission.objects.get(pk=mission_id)
    events = mission.events.filter(instrument__type=core_models.InstrumentType.ctd)
    bottles = core_models.Bottle.objects.filter(event__in=events)

    alert_soup = form_biochem_database.confirm_uploader(request)
    if alert_soup:
        div.append(alert_soup)
        return HttpResponse(soup)

    alert_soup = form_biochem_database.confirm_descriptor(request, mission)
    if alert_soup:
        div.append(alert_soup)
        return HttpResponse(soup)

    logger.info("Creating BCS/BCD files")
    uploader = request.POST['uploader2'] if 'uploader2' in request.POST else \
        request.POST['uploader'] if 'uploader' in request.POST else "N/A"

    logger.info(f"Using uploader: {uploader}")

    # because we're not passing in a link to a database for the bcs_d_model there will be no updated rows or fields
    # only the objects being created will be returned.
    create = upload.get_bcs_d_rows(uploader=uploader, bottles=bottles)

    logger.info(f"Created {len(create)} BCD rows")

    bcs_headers = [field.name for field in biochem_models.BcsDReportModel._meta.fields]

    file_name = f'{mission.name}_BCS_D.csv'
    report_path = os.path.join(settings.BASE_DIR, "reports")
    Path(report_path).mkdir(parents=True, exist_ok=True)

    try:
        with open(os.path.join(report_path, file_name), 'w', newline='', encoding="UTF8") as f:

            writer = csv.writer(f)
            writer.writerow(bcs_headers)

            for bcs_row in create:
                row = [getattr(bcs_row, header, '') for header in bcs_headers]
                writer.writerow(row)
    except PermissionError as e:
        attrs = {
            'component_id': 'div_id_upload_biochem',
            'alert_type': 'danger',
            'message': _("Could not save report, the file may be opened and/or locked"),
        }
        alert_soup = core_forms.blank_alert(**attrs)
        div.append(alert_soup)
        logger.exception(e)
        return HttpResponse(soup)

    data_types = core_models.BioChemUpload.objects.filter(
        type__mission=mission).values_list('type', flat=True).distinct()

    discrete_samples = core_models.DiscreteSampleValue.objects.filter(
        sample__bottle__event__mission=mission)
    discrete_samples = discrete_samples.filter(sample__type_id__in=data_types)

    # because we're not passing in a link to a database for the bcd_d_model there will be no updated rows or fields
    # only the objects being created will be returned.
    create = upload.get_bcd_d_rows(uploader=uploader, samples=discrete_samples)

    bcd_headers = [field.name for field in biochem_models.BcdDReportModel._meta.fields]

    file_name = f'{mission.name}_BCD_D.csv'
    report_path = os.path.join(settings.BASE_DIR, "reports")
    Path(report_path).mkdir(parents=True, exist_ok=True)

    try:
        with open(os.path.join(report_path, file_name), 'w', newline='', encoding="UTF8") as f:

            writer = csv.writer(f)
            writer.writerow(bcd_headers)

            for idx, bcs_row in enumerate(create):
                row = [str(idx + 1) if header == 'dis_data_num' else getattr(bcs_row, header, '') for
                       header in bcd_headers]
                writer.writerow(row)
    except PermissionError as e:
        attrs = {
            'component_id': 'div_id_upload_biochem',
            'alert_type': 'danger',
            'message': _("Could not save report, the file may be opened and/or locked"),
        }
        alert_soup = core_forms.blank_alert(**attrs)
        div.append(alert_soup)
        logger.exception(e)
        return HttpResponse(soup)

    attrs = {
        'component_id': 'div_id_upload_biochem',
        'alert_type': 'success',
        'message': _("Success - Reports saved at : ") + f'{report_path}',
    }
    alert_soup = core_forms.blank_alert(**attrs)

    div.append(alert_soup)

    return HttpResponse(soup)


prefix = 'biochem/discrete'
url_patterns = [
    path(f'<int:mission_id>/{prefix}/upload/', upload_batch, name="form_biochem_discrete_upload_batch"),
    path(f'<int:mission_id>/{prefix}/download/', download_batch, name="form_biochem_discrete_download_batch"),
    path(f'<int:mission_id>/{prefix}/batch/', get_batch, name="form_biochem_discrete_update_selected_batch"),
    path(f'<int:mission_id>/{prefix}/batch/<int:batch_id>/', get_batch_info, name="form_biochem_discrete_get_batch"),
    path(f'<int:mission_id>/{prefix}/delete/<int:batch_id>/', run_biochem_delete_procedure, name="form_biochem_discrete_delete"),
    path(f'<int:mission_id>/{prefix}/form/<int:batch_id>/', refresh_batches_form, name="form_biochem_discrete_refresh"),

    path(f'{prefix}/validate1/<int:batch_id>/', biochem_validation1_procedure, name="form_biochem_discrete_validation1"),
    path(f'{prefix}/validate2/<int:batch_id>/', biochem_validation2_procedure, name="form_biochem_discrete_validation2"),
    path(f'{prefix}/checkin/<int:batch_id>/', biochem_checkin_procedure, name="form_biochem_discrete_checkin"),
    path(f'<int:mission_id>/{prefix}/merge/<int:batch_id>/', biochem_merge_procedure, name="form_biochem_discrete_merge"),
    path(f'{prefix}/page/bcd/<int:batch_id>/<int:page>/', page_bcd, name="form_biochem_discrete_page_bcd"),
    path(f'{prefix}/page/bcs/<int:batch_id>/<int:page>/', page_bcs, name="form_biochem_discrete_page_bcs"),
    path(f'{prefix}/page/station_errors/<int:batch_id>/<int:page>/', page_data_station_errors,
         name="form_biochem_discrete_page_station_errors"
    ),
    path(f'{prefix}/page/data_errors/<int:batch_id>/<int:page>/', page_data_errors,
         name="form_biochem_discrete_page_errors"
    ),
]
