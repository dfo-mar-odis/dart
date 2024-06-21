import csv
import io
import time
from pathlib import Path

import numpy as np
import os

import bs4
import pandas as pd
from bs4 import BeautifulSoup

from crispy_forms.utils import render_crispy_form
from django.conf import settings

from django.db.models import Max, QuerySet
from django.http import HttpResponse, Http404
from django.template.loader import render_to_string
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _
from django_pandas.io import read_frame

import biochem.upload
from biochem import models as biochem_models

from core import forms, form_biochem_database, validation
from core import models
from core import views
from core.form_sample_type_config import process_file
from core.parsers import SampleParser

from settingsdb import models as settings_models

from dart.utils import load_svg

from dart.views import GenericDetailView

import logging

logger = logging.getLogger('dart')
user_logger = logger.getChild('user')


def get_sensor_table_button(soup: BeautifulSoup, database, mission: models.Mission, sampletype_id: int):
    sampletype = mission.mission_sample_types.get(pk=sampletype_id)

    sensor: QuerySet[models.BioChemUpload] = sampletype.uploads.all()

    dc_samples = models.DiscreteSampleValue.objects.using(database).filter(
        sample__bottle__event__mission_id=mission.pk, sample__type_id=sampletype_id)

    row_datatype = dc_samples.values_list("datatype", flat=True).distinct().first()
    datatype = sampletype.datatype if sampletype.datatype else None

    # if no datatype is applied
    button_colour = 'btn-danger'

    title = sampletype.long_name if sampletype.long_name else sampletype.name
    if datatype:
        # if the datatype is applied at the 'standard'
        button_colour = 'btn-secondary'
        title += f': {datatype}'
    elif row_datatype:
        # if the datatype is applied at the mission level or row level
        button_colour = 'btn-warning'
    else:
        title += f': ' + _('Missing Biochem datatype')

    if sensor.exists():
        uploaded = sensor.first().upload_date
        modified = sensor.first().modified_date

        if uploaded:
            if modified < uploaded:
                # if the sensor was uploaded
                button_colour = 'btn-success'
            else:
                button_colour = 'btn-primary'

    button = soup.new_tag("a")
    button.string = f'{sampletype.name}'
    button.attrs['id'] = f'button_id_sample_type_details_{sampletype.pk}'
    button.attrs['class'] = 'btn btn-sm ' + button_colour
    button.attrs['style'] = 'width: 100%'
    button.attrs['href'] = reverse_lazy('core:mission_sample_type_details', args=(database, sampletype.pk,))
    button.attrs['title'] = title

    return button


def get_sensor_table_upload_checkbox(soup: BeautifulSoup, database,
                                     mission: models.Mission,
                                     sample_type_id):

    sample_type = mission.mission_sample_types.get(pk=sample_type_id)
    enabled = False
    if sample_type.datatype:
        # a sample must have either a Standard level or Mision level data type to be uploadable.
        enabled = True

    check = soup.new_tag('input')
    check.attrs['id'] = f'input_id_sample_type_{sample_type.pk}'
    check.attrs['type'] = 'checkbox'
    check.attrs['value'] = sample_type.pk
    check.attrs['hx-swap'] = 'outerHTML'
    check.attrs['hx-target'] = f"#{check.attrs['id']}"
    check.attrs['hx-post'] = reverse_lazy('core:mission_samples_add_sensor_to_upload',
                                          args=(database, mission.pk, sample_type.pk,))

    if enabled:
        if sample_type.uploads.exists() and sample_type.uploads.first().status != models.BioChemUploadStatus.delete:
            check.attrs['name'] = 'remove_sensor'
            check.attrs['checked'] = 'checked'
        else:
            check.attrs['name'] = 'add_sensor'
    else:
        check.attrs['disabled'] = 'true'
        check.attrs['title'] = _("Requires a Standard or Mission level Biochem Datatype")

    return check


class SampleDetails(GenericDetailView):
    model = models.Mission
    page_title = _("Mission Samples")
    template_name = "core/mission_samples.html"

    def get_page_title(self):
        return _("Mission Samples") + " : " + self.object.name

    def get_settings_url(self):
        return reverse_lazy("core:mission_edit", args=(self.object.pk,))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        database = context['database']
        context['reports'] = {key: reverse_lazy(views.reports[key], args=(database, self.object.pk,)) for key in
                              views.reports.keys()}

        context['mission'] = self.object
        return context


def get_file_error_card(request, database, mission_id):
    soup = BeautifulSoup("", "html.parser")

    mission = models.Mission.objects.using(database).get(pk=mission_id)
    errors = mission.file_errors.filter(file_name=request.GET['file_name'])
    if errors.exists():
        attrs = {
            'card_name': "file_warnings",
            'card_title': _("File Warnings"),
            'card_class': "text-bg-warning"
        }
        error_card_form = forms.CollapsableCardForm(**attrs)
        error_card_html = render_crispy_form(error_card_form)
        error_card = BeautifulSoup(error_card_html, 'html.parser')

        card_div = error_card.find("div")

        card_body = card_div.find(id=error_card_form.get_card_body_id())
        card_body['class'] = card_body.get('class', []) + ['vertical-scrollbar-sm']

        ul = soup.new_tag("ul", attrs={'class': 'list-group'})

        card_body.append(ul)
        for error in errors:
            li_id = f'error_{error.pk}'
            li = soup.new_tag('li', attrs={'class': 'list-group-item', 'id': li_id})
            div = soup.new_tag('div', attrs={'class': 'col'})
            div.string = error.message

            url = reverse_lazy('core:mission_samples_delete_file_error', args=(database, error.pk))
            btn_attrs = {
                'class': 'btn btn-danger btn-sm col-auto',
                'hx-delete': url,
                'hx-confirm': _("Are you sure?"),
                'hx-target': f"#{li_id}",
                'hx-swap': 'outerHTML'
            }
            button = soup.new_tag('button', attrs=btn_attrs)
            button.append(BeautifulSoup(load_svg('x-square'), 'html.parser').svg)

            div_row = soup.new_tag('div', attrs={'class': 'row'})
            div_row.append(div)
            div_row.append(button)
            li.append(div_row)
            ul.append(li)

        soup.append(card_div)
    return HttpResponse(soup)


def load_samples(request, database):
    # Either delete a file configuration or load the samples from the sample file

    if request.method == "GET":

        soup = BeautifulSoup(f'', 'html.parser')

        url = reverse_lazy("core:mission_samples_load_samples", args=(database,))
        attrs = {
            'alert_area_id': f'div_id_sample_type_holder',
            'message': _("Loading"),
            'logger': SampleParser.logger_notifications.name,
            'alert_type': 'info',
            'hx-post': url,
            'hx-trigger': "load",
        }
        alert = forms.websocket_post_request_alert(**attrs)
        soup.append(alert)

        return HttpResponse(soup)

    elif request.method == "POST":
        time.sleep(2)  # give the websocket a couple seconds to connect
        context = {}
        if 'sample_file' not in request.FILES:
            context['message'] = _("File is required before adding sample")
            html = render_to_string("core/partials/form_sample_type.html", context=context)
            return HttpResponse(html)

        config_ids = request.POST.getlist('sample_config')
        file = request.FILES['sample_file']
        file_name, file_type, data = process_file(file)

        config_count = len(config_ids)
        for index, config_id in enumerate(config_ids):
            SampleParser.logger_notifications.info(_("Loading file") + f" : {file_name} : %d/%d",
                                                   index, config_count)

            sample_config = settings_models.SampleTypeConfig.objects.get(pk=config_id)
            mission = models.Mission.objects.using(database).get(pk=request.POST['mission_id'])

            if file_type == 'csv' or file_type == 'dat':
                io_stream = io.BytesIO(data)
                dataframe = pd.read_csv(filepath_or_buffer=io_stream, header=sample_config.skip)
            else:
                dataframe = SampleParser.get_excel_dataframe(stream=data, sheet_number=sample_config.tab,
                                                             header_row=sample_config.skip)

            try:
                # Remove any row that is *all* nan values
                dataframe.dropna(axis=0, how='all', inplace=True)

                SampleParser.parse_data_frame(mission, sample_config, file_name=file_name, dataframe=dataframe)

                # if the datatypes are valid, then before we upload we should copy any
                # 'standard' level biochem data types to the mission level
                user_logger.info(_("Copying Mission Datatypes"))

                # once loaded apply the default sample type as a mission sample type so that if the default type is ever
                # changed it won't affect the data type for this mission
                sample_type = sample_config.sample_type
                if sample_type.datatype and not mission.mission_sample_types.filter(
                        name=sample_type.short_name).exists():
                    mst = models.MissionSampleType(mission=mission,
                                                   name=sample_type.short_name,
                                                   long_name=sample_type.long_name,
                                                   priority=sample_type.priority,
                                                   is_sensor=sample_type.is_sensor,
                                                   datatype=sample_type.datatype)
                    mst.save(using=database)

            except Exception as ex:
                logger.error(f"Failed to load file {file_name}")
                logger.exception(ex)

        soup = BeautifulSoup("", "html.parser")
        response = HttpResponse(soup)

        # This will trigger the Sample table on the 'core/mission_samples.html' template to update
        response['HX-Trigger'] = 'update_samples, file_errors_updated, reload_sample_file'
        return response


def soup_split_column(soup: BeautifulSoup, column: bs4.Tag) -> bs4.Tag:
    # if the th colspan is > 1 it's because there are replicates, the column should be split up
    # return the last column
    if 'colspan' in column.attrs and int(column.attrs['colspan']) > 1:
        label = column.string
        col_count = int(column.attrs['colspan'])
        column.attrs['colspan'] = "1"
        column.string = f'{label}-1'
        for i in range(1, col_count):
            new_th = soup.new_tag('th')
            new_th.attrs = column.attrs
            new_th.string = f'{label}-{str(i + 1)}'
            column.insert_after(new_th)
            column = new_th

    return column


def list_samples(request, database, mission_id):
    page = int(request.GET.get('page', 0) or 0)
    page_limit = 50
    page_start = page_limit * page

    table_soup = BeautifulSoup('', 'html.parser')

    mission = models.Mission.objects.using(database).get(pk=mission_id)
    bottle_limit = models.Bottle.objects.using(database).filter(event__mission=mission).order_by('bottle_id')[
                   page_start:(page_start + page_limit)]

    if not bottle_limit.exists():
        # if there are no more bottles then we stop loading, otherwise weird things happen
        return HttpResponse()

    queryset = models.Sample.objects.using(database).filter(bottle__in=bottle_limit)
    queryset = queryset.order_by('bottle__bottle_id')
    queryset = queryset.values(
        'bottle__bottle_id',
        'bottle__pressure',
        'type__id',
        'discrete_values__replicate',
        'discrete_values__value',
    )
    df = read_frame(queryset)
    df.columns = ["Sample", "Pressure", "Sensor", "Replicate", "Value"]

    try:
        sensors = mission.mission_sample_types.all()
        df = pd.pivot_table(df, values='Value', index=['Sample', 'Pressure'], columns=['Sensor', 'Replicate'])
        # we want a column for every sensor and then a column for every replicate for every sensor
        # for all sensors in the mission
        for sensor in sensors:
            # compute the maximum number of columns this sensor will require by figuring out th maximum number
            # of replicate the sensor/sample has
            replicate_count = sensor.samples.aggregate(replicates=Max('discrete_values__replicate'))
            if replicate_count['replicates']:
                for i in range(0, replicate_count['replicates']):
                    replicate = i + 1
                    if not df.columns.isin([(sensor.pk, replicate)]).any():
                        # if the replicate column doesn't currently have any values, insert a nan as a placeholder
                        df[(sensor.pk, replicate)] = df.apply(lambda _: np.nan, axis=1)

        available_sensors = [c[0] for c in df.columns.values]
        sensor_order = sensors.order_by('is_sensor', 'priority', 'pk')
        df = df.reindex(axis=1).loc[:, [sensor.pk for sensor in sensor_order if sensor.pk in available_sensors]]
        table_soup = format_all_sensor_table(df, database, mission)
    except Exception as ex:
        logger.exception(ex)

    # add styles to the table so it's consistent with the rest of the application
    table = table_soup.find('table')
    table.attrs['id'] = "table_id_sample_table"
    table.attrs['class'] = 'dataframe table table-striped table-sm tscroll horizontal-scrollbar'

    # now we'll attach an HTMX call to the last queried table row so when the user scrolls to it the next batch
    # of samples will be loaded into the table.
    # table_head = table.find('thead')

    table_body = table.find('tbody')
    table_body.attrs['id'] = "tbody_id_sample_table"

    url = reverse_lazy('core:mission_samples_sample_list', args=(database, mission.pk,))
    last_tr = table_body.find_all('tr')[0]
    last_tr.attrs['hx-target'] = '#tbody_id_sample_table'
    last_tr.attrs['hx-trigger'] = 'intersect once'
    last_tr.attrs['hx-get'] = url + f"?page={page + 1}"
    last_tr.attrs['hx-swap'] = "beforeend"

    # finally, align all text in each column to the center of the cell
    tds = table_soup.find('table').find_all('td')
    for td in tds:
        td['class'] = 'text-center text-nowrap'

    if page > 0:
        response = HttpResponse(table_soup.find('tbody').findAll('tr', recursive=False))
    else:
        table = table_soup.find("table", recursive=False)
        table.attrs['id'] = "table_id_sample_table"
        table.attrs['hx-swap-oob'] = 'true'
        response = HttpResponse(table_soup)

    return response


def format_all_sensor_table(df: pd.DataFrame, database, mission: models.Mission) -> BeautifulSoup:
    # start by replacing nan values with '---'
    df.fillna('---', inplace=True)

    # Pandas has the ability to render dataframes as HTML and it's super fast, but the default table looks awful.
    # Use BeautifulSoup for html manipulation to post process the HTML table Pandas created
    soup = BeautifulSoup(df.to_html(), 'html.parser')

    # The next few rows will be the 'Sensor' row with labels like C0SM, T090C, and oxy
    # followed by the 'replicate' row that describes if this is a single, double, triple, etc. column sample.

    # We're going to flatten the headers down to one row then remove the other thead rows.
    # this is the row containing the sensor/sample short names
    sensor_headers = soup.find("thead").find("tr")

    # this is the replicate row, but we aren't doing anything with this row so get rid of it
    replicate_headers = sensor_headers.findNext("tr")
    replicate_headers.decompose()

    # we now have two header rows. The first contains all the sensor/sample names. The second contains the "Sample"
    # and "Pressure" labels with a bunch of empty columns afterward. I want to copy the first two columns
    # from the second header to the sensor_header row (because the labels might be translated)
    # then delete the second row
    index_headers = sensor_headers.findNext('tr')

    # copy the 'Sample' label
    index_column = index_headers.find('th')
    sensor_column = sensor_headers.find('th')
    sensor_column.string = index_column.string

    # copy the 'Pressure' label
    index_column = index_column.findNext('th')
    sensor_column = sensor_column.findNext('th')
    sensor_column.string = index_column.string

    # remove the now unneeded index_header row
    index_headers.decompose()

    # Now add a row to the table header that will contain checkbox inputs for the user to select
    # a sensor or sample to upload to biochem
    upload_row = soup.new_tag('tr')
    soup.find("thead").insert(0, upload_row)

    # the first column of the table will have the 'Sample' and 'Pressure' lables under it so it spans two columns
    upload_row_title = soup.new_tag('th')
    upload_row_title.attrs['colspan'] = "2"
    upload_row_title.string = _("Biochem upload")
    upload_row.append(upload_row_title)

    # Now we're going to convert all of the sensor/sample column labels, which are actually the
    # core.models.SampleType ids, into buttons the user can press to open up a specific sensor to set
    # data types at a row level
    column = sensor_column.findNext('th')  # Sensor column
    while column:
        column['class'] = 'text-center text-nowrap'

        sampletype_id = int(column.string)

        button = get_sensor_table_button(soup, database, mission, sampletype_id)

        # clear the column string and add the button instead
        column.string = ''
        column.append(button)

        # add the upload checkbox to the upload_row we created above, copy the attributes of the button column
        upload = soup.new_tag('th')
        upload.attrs = column.attrs

        check = get_sensor_table_upload_checkbox(soup, database, mission, sampletype_id)
        upload.append(check)
        upload_row.append(upload)

        # we're done with this column, get the next column and start again
        column = column.find_next_sibling('th')

    return soup


def add_sensor_to_upload(request, database, mission_id, sensor_id, **kwargs):
    soup = BeautifulSoup('', 'html.parser')
    mission = models.Mission.objects.using(database).get(pk=mission_id)
    if request.method == 'POST':
        button = get_sensor_table_button(soup, database, mission, sensor_id)
        button.attrs['hx-swap-oob'] = 'true'

        upload_sensors: QuerySet[models.BioChemUpload] = \
            models.BioChemUpload.objects.using(database).filter(type_id=sensor_id)

        if 'add_sensor' in request.POST:
            add_sensor = upload_sensors.get_or_create(type_id=sensor_id)[0]
            add_sensor.status = models.BioChemUploadStatus.upload
            add_sensor.save(using=database)
        else:
            if upload_sensors.filter(type_id=sensor_id).exists():
                sensor = upload_sensors.get(type_id=sensor_id)
                if sensor.status == models.BioChemUploadStatus.uploaded or sensor.upload_date:
                    sensor.status = models.BioChemUploadStatus.delete
                    sensor.save(using=database)
                else:
                    sensor.delete()

        check = get_sensor_table_upload_checkbox(soup, database, mission, sensor_id)
        soup.append(check)
        soup.append(button)

        return HttpResponse(soup)

    logger.error("user has entered an unmanageable state")
    logger.error(kwargs)
    logger.error(request.method)
    logger.error(request.GET)
    logger.error(request.POST)

    return Http404("You shouldn't be here")


def biochem_upload_card(request, database, mission_id):
    # upload_url = reverse_lazy("core:mission_samples_upload_bio_chem", args=(database, mission_id,))
    # download_url = reverse_lazy("core:mission_samples_download_bio_chem", args=(database, mission_id,))

    button_url = reverse_lazy('core:mission_samples_update_bio_chem_buttons', args=(database, mission_id))

    soup = BeautifulSoup('', 'html.parser')
    soup.append(biochem_card_wrapper := soup.new_tag('div', id="div_id_biochem_card_wrapper"))
    biochem_card_wrapper.attrs['class'] = "mb-2"
    biochem_card_wrapper.attrs['hx-get'] = button_url
    biochem_card_wrapper.attrs['hx-trigger'] = 'load, biochem_db_update from:body'
    # the method to update the upload/download buttons on the biochem form will be hx-swap-oob
    biochem_card_wrapper.attrs['hx-swap'] = 'none'

    form_soup = form_biochem_database.get_database_connection_form(request, database, mission_id)
    biochem_card_wrapper.append(form_soup)

    return HttpResponse(soup)


def sample_data_upload(database, mission: models.Mission, uploader: str):
    # clear previous errors if there were any from the last upload attempt
    mission.errors.filter(type=models.ErrorType.biochem).delete()
    models.Error.objects.using(database).filter(mission=mission, type=models.ErrorType.biochem).delete()

    # send_user_notification_queue('biochem', _("Validating Sensor/Sample Datatypes"))
    user_logger.info(_("Validating Sensor/Sample Datatypes"))
    samples_types_for_upload = [bcupload.type for bcupload in
                                models.BioChemUpload.objects.using(database).filter(type__mission=mission)]
    errors = validation.validate_samples_for_biochem(mission=mission, sample_types=samples_types_for_upload)

    if errors:
        # send_user_notification_queue('biochem', _("Datatypes missing see errors"))
        user_logger.info(_("Datatypes missing see errors"))
        models.Error.objects.using(database).bulk_create(errors)

    # create and upload the BCS data if it doesn't already exist
    form_biochem_database.upload_bcs_d_data(mission, uploader)
    form_biochem_database.upload_bcd_d_data(mission, uploader)


def upload_samples(request, database, mission_id):
    soup = BeautifulSoup('', 'html.parser')
    soup.append(div := soup.new_tag('div'))
    div.attrs['id'] = "div_id_biochem_alert_biochem_db_details"
    div.attrs['hx-swap-oob'] = 'true'

    # are we connected?
    if not form_biochem_database.is_connected():
        alert_soup = forms.blank_alert("div_id_biochem_alert", _("Not Connected"), alert_type="danger")
        div.append(alert_soup)
        return HttpResponse(soup)

    # do we have an uploader?
    alert_soup = form_biochem_database.confirm_uploader(request)
    if alert_soup:
        div.append(alert_soup)
        return HttpResponse(soup)

    try:
        uploader = request.POST['uploader2'] if 'uploader2' in request.POST else \
            request.POST['uploader'] if 'uploader' in request.POST else "N/A"

        mission = models.Mission.objects.using(database).get(pk=mission_id)
        sample_data_upload(database, mission, uploader)
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

    alert_soup = forms.blank_alert(**attrs)
    div.append(alert_soup)
    response = HttpResponse(soup)
    response['HX-Trigger'] = 'update_samples'
    return response


def download_samples(request, database, mission_id):
    soup = BeautifulSoup('', 'html.parser')
    div = soup.new_tag('div')
    div.attrs = {
        'id': "div_id_biochem_alert_biochem_db_details",
        'hx-swap-oob': 'true'
    }
    soup.append(div)

    alert_soup = form_biochem_database.confirm_uploader(request)
    if alert_soup:
        div.append(alert_soup)
        return HttpResponse(soup)

    uploader = request.POST['uploader2'] if 'uploader2' in request.POST else \
        request.POST['uploader'] if 'uploader' in request.POST else "N/A"

    mission = models.Mission.objects.using(database).get(pk=mission_id)
    events = mission.events.filter(instrument__type=models.InstrumentType.ctd)
    bottles = models.Bottle.objects.using(database).filter(event__in=events)
    # because we're not passing in a link to a database for the bcs_d_model there will be no updated rows or fields
    # only the objects being created will be returned.
    create, update, fields = biochem.upload.get_bcs_d_rows(uploader=uploader, bottles=bottles,
                                                           batch_name=mission.get_batch_name)

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
    except PermissionError:
        attrs = {
            'component_id': 'div_id_upload_biochem',
            'alert_type': 'danger',
            'message': _("Could not save report, the file may be opened and/or locked"),
        }
        alert_soup = forms.blank_alert(**attrs)
        div.append(alert_soup)

        return HttpResponse(soup)

    data_types = models.BioChemUpload.objects.using(database).filter(
        type__mission=mission).values_list('type', flat=True).distinct()

    discrete_samples = models.DiscreteSampleValue.objects.using(database).filter(
        sample__bottle__event__mission=mission)
    discrete_samples = discrete_samples.filter(sample__type_id__in=data_types)

    # because we're not passing in a link to a database for the bcd_d_model there will be no updated rows or fields
    # only the objects being created will be returned.
    create, update, fields = biochem.upload.get_bcd_d_rows(database=database, uploader=uploader,
                                                           samples=discrete_samples,
                                                           batch_name=mission.get_batch_name)

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
    except PermissionError:
        attrs = {
            'component_id': 'div_id_upload_biochem',
            'alert_type': 'danger',
            'message': _("Could not save report, the file may be opened and/or locked"),
        }
        alert_soup = forms.blank_alert(**attrs)
        div.append(alert_soup)

        return HttpResponse(soup)

    attrs = {
        'component_id': 'div_id_upload_biochem',
        'alert_type': 'success',
        'message': _("Success - Reports saved at : ") + f'{report_path}',
    }
    alert_soup = forms.blank_alert(**attrs)

    div.append(alert_soup)

    return HttpResponse(soup)


def get_biochem_buttons(request, database, mission_id):
    soup = BeautifulSoup('', 'html.parser')
    soup.append(button_area := soup.new_tag('div'))
    button_area.attrs['id'] = form_biochem_database.get_biochem_additional_button_id()
    button_area.attrs['class'] = 'col-auto align-self-center'
    button_area.attrs['hx-swap-oob'] = 'true'

    icon = BeautifulSoup(load_svg('arrow-down-square'), 'html.parser').svg
    button_area.append(download_button := soup.new_tag('button'))
    download_button.append(icon)
    download_button.attrs['class'] = 'btn btn-sm btn-primary'
    download_button.attrs['title'] = _("Build BCS/BCD Staging table CSV file")
    download_button.attrs['hx-get'] = reverse_lazy("core:mission_samples_download_bio_chem",
                                                   args=(database, mission_id))
    download_button.attrs['hx-swap'] = 'none'

    icon = BeautifulSoup(load_svg('database-add'), 'html.parser').svg
    button_area.append(download_button := soup.new_tag('button'))
    download_button.append(icon)
    download_button.attrs['class'] = 'btn btn-sm btn-primary ms-2'
    download_button.attrs['title'] = _("Upload selected Sensors/Samples to Database")
    download_button.attrs['hx-get'] = reverse_lazy("core:mission_samples_upload_bio_chem",
                                                   args=(database, mission_id))
    download_button.attrs['hx-swap'] = 'none'

    return HttpResponse(soup)


def delete_file_error(request, database, error_id):
    models.FileError.objects.using(database).filter(id=error_id).delete()

    return HttpResponse()


# ###### Mission Sample ###### #
url_prefix = "<str:database>/sample"
mission_sample_urls = [
    path(f'{url_prefix}/<int:pk>/', SampleDetails.as_view(), name="mission_samples_sample_details"),

    # used to reload elements on the sample form if a GET htmx request
    path(f'{url_prefix}/sample/file_errors/<int:mission_id>/', get_file_error_card,
         name="mission_samples_get_file_errors"),

    # load samples using a given sample type configuration file configuration
    path(f'{url_prefix}/sample/load/', load_samples, name="mission_samples_load_samples"),

    # ###### sample details ###### #

    path('<str:database>/sample/list/<int:mission_id>/', list_samples, name="mission_samples_sample_list"),

    path('<str:database>/sample/upload/sensor/<int:mission_id>/<int:sensor_id>/', add_sensor_to_upload,
         name="mission_samples_add_sensor_to_upload"),
    path('<str:database>/sample/upload/sensor/<int:mission_id>/', biochem_upload_card,
         name="mission_samples_biochem_upload_card"),
    path('<str:database>/sample/upload/biochem/<int:mission_id>/', upload_samples,
         name="mission_samples_upload_bio_chem"),
    path('<str:database>/sample/download/biochem/<int:mission_id>/', download_samples,
         name="mission_samples_download_bio_chem"),

    path(f'{url_prefix}/sample/error/<int:error_id>/', delete_file_error,
         name="mission_samples_delete_file_error"),

    path(f'{url_prefix}/sample/biochem/<int:mission_id>/', get_biochem_buttons,
         name="mission_samples_update_bio_chem_buttons"),

]
