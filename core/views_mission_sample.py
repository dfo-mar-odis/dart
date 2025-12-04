import io
import time

import numpy as np

import bs4
import pandas as pd
from bs4 import BeautifulSoup

from crispy_forms.utils import render_crispy_form

from django.db.models import Max, QuerySet
from django.http import HttpResponse, Http404
from django.template.loader import render_to_string
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _
from django_pandas.io import read_frame
from django.conf import settings

from core import forms, form_biochem_discrete, form_btl_load

from core import models
from core import views
from core.form_sample_type_config import process_file
from core.parsers import SampleParser

from settingsdb import models as settings_models

from config.utils import load_svg

from config.views import GenericDetailView

import logging

logger = logging.getLogger('dart')
user_logger = logger.getChild('user')


def get_sensor_table_button(soup: BeautifulSoup, mission: models.Mission, sampletype_id: int):
    sampletype = mission.mission_sample_types.get(pk=sampletype_id)

    sensor: QuerySet[models.BioChemUpload] = sampletype.uploads.all()

    dc_samples = models.DiscreteSampleValue.objects.filter(
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

    database = settings.DATABASES[mission._state.db]['LOADED'] if 'LOADED' in settings.DATABASES[mission._state.db] else 'default'
    button = soup.new_tag("a")
    button.string = f'{sampletype.name}'
    button.attrs['id'] = f'button_id_sample_type_details_{sampletype.pk}'
    button.attrs['class'] = 'btn btn-sm ' + button_colour
    button.attrs['style'] = 'width: 100%'
    button.attrs['href'] = reverse_lazy('core:mission_sample_type_details', args=(database, sampletype.pk,))
    button.attrs['title'] = title

    return button


def get_sensor_table_upload_checkbox(soup: BeautifulSoup,
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
                                          args=(mission.pk, sample_type.pk,))

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
    help_text = _(
        "The mission samples page allows bulk loading of sensor and sample data, provides utilities for setting gear "
        "information, modifying sample details, runing pre-validation to identify and correct issues, and finally "
        "upload discrete details to the BioChem database."
    )

    def get_page_title(self):
        return _("Mission Samples") + " : " + self.object.name

    def get_settings_url(self):
        return reverse_lazy("core:mission_edit", args=(self.object.pk,))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        database = context['database']
        context['reports'] = {key: reverse_lazy(views.reports[key], args=(self.object.pk,)) for key in
                              views.reports.keys()}

        context['mission'] = self.object
        context['bulk_load_form'] = form_btl_load.BottleLoadForm(mission=self.object)
        return context


def get_file_error_card(request, mission_id):
    soup = BeautifulSoup("", "html.parser")

    mission = models.Mission.objects.get(pk=mission_id)
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

        ul = soup.new_tag("ul", attrs={'class': 'list-group'})

        card_body.append(ul)
        for error in errors:
            li_id = f'error_{error.pk}'
            li = soup.new_tag('li', attrs={'class': 'list-group-item', 'id': li_id})
            div = soup.new_tag('div', attrs={'class': 'col'})
            msgs = error.message.split("\n")
            for msg in msgs:
                if msg.strip() != "":
                    continue

                div.append(msg_div := soup.new_tag('div'))
                if error.line:
                    msg_div.string = _("Line") + f" {error.line} : {msg}"
                else:
                    msg_div.string = msg

            url = reverse_lazy('core:mission_samples_delete_file_error', args=(error.pk,))
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


def load_samples(request):
    # Either delete a file configuration or load the samples from the sample file

    if request.method == "GET":

        soup = BeautifulSoup(f'', 'html.parser')

        url = reverse_lazy("core:mission_samples_load_samples")
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
            mission = models.Mission.objects.get(pk=request.POST['mission_id'])

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
                    mst.save()

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


def list_samples(request, mission_id):
    page = int(request.GET.get('page', 0) or 0)
    page_limit = 100
    page_start = page_limit * page

    table_soup = BeautifulSoup('', 'html.parser')

    mission = models.Mission.objects.get(pk=mission_id)
    bottle_limit = models.Bottle.objects.filter(event__mission=mission)
    if not bottle_limit.exists():
        # there is no data loaded yet
        table_soup.append(table := table_soup.new_tag('div', attrs={'class': 'alert alert-warning'}))
        table.attrs['id'] = "table_id_sample_table"
        table.attrs['hx-swap-oob'] = 'true'
        table.string = _("No Data")
        response = HttpResponse(table_soup)
        return response

    bottle_limit = bottle_limit.order_by('bottle_id')[page_start:(page_start + page_limit)]

    if not bottle_limit.exists():
        # if there are no more bottles then we stop loading, otherwise weird things happen
        return HttpResponse()

    queryset = models.Sample.objects.filter(bottle__in=bottle_limit)
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
        # Precompute all required (sensor, replicate) column pairs
        required_columns = []
        for sensor in sensors:
            replicate_count = sensor.samples.aggregate(replicates=Max('discrete_values__replicate'))['replicates']
            if replicate_count:
                required_columns.extend([(sensor.pk, i + 1) for i in range(replicate_count)])

        df = pd.pivot_table(df, values='Value', index=['Sample', 'Pressure'], columns=['Sensor', 'Replicate'])
        # Add missing columns in one go, filling with np.nan
        for col in required_columns:
            if col not in df.columns:
                df[col] = np.nan

        available_sensors = [c[0] for c in df.columns.values]
        sensor_order = sensors.order_by('is_sensor', 'priority', 'pk')
        df = df.reindex(axis=1).loc[:, [sensor.pk for sensor in sensor_order if sensor.pk in available_sensors]]
    except Exception as ex:
        logger.exception(ex)

    # start by replacing nan values with '---'
    df.fillna('---', inplace=True)

    # Pandas has the ability to render dataframes as HTML and it's super fast, but the default table looks awful.
    # Use BeautifulSoup for html manipulation to post process the HTML table Pandas created
    df_soup = BeautifulSoup(df.to_html(), 'html.parser')

    table = df_soup.find('table')

    # now we'll attach an HTMX call to the last queried table row so when the user scrolls to it the next batch
    # of samples will be loaded into the table.
    # table_head = table.find('thead')
    table_body = table.find('tbody')
    table_body.attrs['id'] = "tbody_id_sample_table"

    #add sticky columns to all the tbody frist two th elements
    for tr in table_body.find_all('tr'):
        th1 = tr.find('th')
        th1.attrs['class'] = "sticky-column"
        th1.attrs['style'] = "left: -1px;"

        th2 = th1.find_next_sibling('th')
        th2.attrs['class'] = "sticky-column"
        th2.attrs['style'] = "left: 89px;"

    # 9 rows are visible on screen so let's put the trigger on line 8, which is sure to be in the table
    # and will trigger the reload before the user hits the bottlm
    page_trigger = 8
    if len(last_tr:=table_body.find_all('tr')) > page_trigger:
        url = reverse_lazy('core:mission_samples_sample_list', args=(mission.pk,))
        last_tr = table_body.find_all('tr')[-page_trigger]
        last_tr.attrs['hx-target'] = '#tbody_id_sample_table'
        last_tr.attrs['hx-trigger'] = 'intersect once'
        last_tr.attrs['hx-get'] = url + f"?page={page + 1}"
        last_tr.attrs['hx-swap'] = "beforeend"

    # finally, align all text in each column to the center of the cell
    for tr in df_soup.find('table').find_all('tr'):
        tr['class'] = 'text-center text-nowrap'

    if page > 0:
        return HttpResponse(df_soup.find('tbody').findAll('tr', recursive=False))

    # we only have to format the table header on the first call to the list function. After that we don't need it.
    format_all_sensor_table(df_soup, mission)


    table = df_soup.find("table", recursive=False)
    table.attrs['id'] = "table_id_sample_table"
    table.attrs['class'] = 'table table-striped table-sm'
    table.attrs['hx-swap-oob'] = 'true'

    return HttpResponse(df_soup)


def format_all_sensor_table(df_soup: BeautifulSoup, mission: models.Mission):

    # The next few rows will be the 'Sensor' row with labels like C0SM, T090C, and oxy
    # followed by the 'replicate' row that describes if this is a single, double, triple, etc. column sample.

    # We're going to flatten the headers down to one row then remove the other thead rows.
    # this is the row containing the sensor/sample short names
    table_header = df_soup.find("thead")
    table_header.attrs['class'] = "sticky-top bg-white"

    sensor_headers = table_header.find("tr")

    # this is the replicate row, but we aren't doing anything with this row so get rid of it
    if(replicate_headers := sensor_headers.findNext("tr")):
        replicate_headers.decompose()

    # we now have two header rows. The first contains all the sensor/sample names. The second contains the "Sample"
    # and "Pressure" labels with a bunch of empty columns afterward. I want to copy the first two columns
    # from the second header to the sensor_header row (because the labels might be translated)
    # then delete the second row
    if (index_headers := sensor_headers.findNext('tr')) is None:
        # if the index_header row is empty, it's because there's now data loaded and no point in continuing.
        return

    # copy the 'Sample' label

    # instead of just copying the sample label, we'll use a button so the user can access the Gear Type form
    # to set gear types and load volume data.
    index_column = index_headers.find('th')
    sensor_column = sensor_headers.find('th')

    database = settings.DATABASES[mission._state.db]['LOADED']
    button = df_soup.new_tag('A', attrs={'class': 'btn btn-sm btn-primary',
                                         'href': reverse_lazy("core:mission_gear_type_details", args=(
                                             database, mission.pk, models.InstrumentType.ctd.value))})
    button.string = _("Sample")
    sensor_column.append(button)
    sensor_column.attrs['class'] = "sticky-column"
    sensor_column.attrs['style'] = "left: -1px;"

    # copy the 'Pressure' label
    index_column = index_column.findNext('th')
    sensor_column = sensor_column.findNext('th')
    sensor_column.attrs['class'] = "sticky-column"
    sensor_column.attrs['style'] = "left: 89px;"
    sensor_column.string = index_column.string
    # remove the now unneeded index_header row
    index_headers.decompose()

    # Now add a row to the table header that will contain checkbox inputs for the user to select
    # a sensor or sample to upload to biochem
    upload_row = df_soup.new_tag('tr')
    df_soup.find("thead").insert(0, upload_row)

    # the first column of the table will have the 'Sample' and 'Pressure' lables under it so it spans two columns
    upload_row_title = df_soup.new_tag('th')
    upload_row_title.attrs['colspan'] = "2"
    upload_row_title.string = _("Biochem upload")
    upload_row_title.attrs['class'] = "sticky-column"
    upload_row_title.attrs['style'] = "left: -1px;"

    upload_row.append(upload_row_title)

    # Now we're going to convert all of the sensor/sample column labels, which are actually the
    # core.models.SampleType ids, into buttons the user can press to open up a specific sensor to set
    # data types at a row level
    column = sensor_column.findNext('th')  # Sensor column
    while column:
        column['class'] = 'text-center text-nowrap'

        sampletype_id = int(column.string)

        button = get_sensor_table_button(df_soup, mission, sampletype_id)

        # clear the column string and add the button instead
        column.string = ''
        column.append(button)

        # add the upload checkbox to the upload_row we created above, copy the attributes of the button column
        upload = df_soup.new_tag('th')
        upload.attrs = column.attrs

        check = get_sensor_table_upload_checkbox(df_soup, mission, sampletype_id)
        upload.append(check)
        upload_row.append(upload)

        # we're done with this column, get the next column and start again
        column = column.find_next_sibling('th')


def add_sensor_to_upload(request, mission_id, sensor_id, **kwargs):
    soup = BeautifulSoup('', 'html.parser')
    mission = models.Mission.objects.get(pk=mission_id)
    if request.method == 'POST':
        button = get_sensor_table_button(soup, mission, sensor_id)
        button.attrs['hx-swap-oob'] = 'true'

        upload_sensors: QuerySet[models.BioChemUpload] = \
            models.BioChemUpload.objects.filter(type_id=sensor_id)

        if 'add_sensor' in request.POST:
            add_sensor = upload_sensors.get_or_create(type_id=sensor_id)[0]
            add_sensor.status = models.BioChemUploadStatus.upload
            add_sensor.save()
        else:
            if upload_sensors.filter(type_id=sensor_id).exists():
                sensor = upload_sensors.get(type_id=sensor_id)
                if sensor.status == models.BioChemUploadStatus.uploaded or sensor.upload_date:
                    sensor.status = models.BioChemUploadStatus.delete
                    sensor.save()
                else:
                    sensor.delete()

        check = get_sensor_table_upload_checkbox(soup, mission, sensor_id)
        soup.append(check)
        soup.append(button)

        return HttpResponse(soup)

    logger.error("user has entered an unmanageable state")
    logger.error(kwargs)
    logger.error(request.method)
    logger.error(request.GET)
    logger.error(request.POST)

    return Http404("You shouldn't be here")


def biochem_batches_card(request, mission_id):

    # The first time we get into this function will be a GET request from the mission_samples.html template asking
    # to put the UI component on the web page.

    # The second time will be whenever a database is connected to or disconnected from which will be a POST
    # request that should update the Batch selection drop down and then fire a trigger to clear the tables

    soup = BeautifulSoup('', 'html.parser')
    form_soup = form_biochem_discrete.get_batches_form(request, mission_id)

    if request.method == "POST":
        batch_div = form_soup.find('div', {"id": "div_id_selected_batch"})
        batch_div.attrs['hx-swap-oob'] = 'true'
        soup.append(batch_div)
        response = HttpResponse(soup)
        response['HX-Trigger'] = 'clear_batch'
        return response

    soup.append(biochem_card_wrapper := soup.new_tag('div', id="div_id_biochem_batches_card_wrapper"))
    biochem_card_wrapper.attrs['class'] = "mb-2"
    biochem_card_wrapper.attrs['hx-trigger'] = 'biochem_db_connect from:body'
    biochem_card_wrapper.attrs['hx-post'] = request.path
    biochem_card_wrapper.attrs['hx-swap'] = 'none'

    biochem_card_wrapper.append(form_soup)
    return HttpResponse(soup)


def delete_file_error(request, error_id):
    models.FileError.objects.filter(id=error_id).delete()

    return HttpResponse()


# ###### Mission Sample ###### #
url_patterns = [
    path(f'<str:database>/sample/<int:pk>/', SampleDetails.as_view(), name="mission_samples_sample_details"),

    # used to reload elements on the sample form if a GET htmx request
    path(f'sample/file_errors/<int:mission_id>/', get_file_error_card, name="mission_samples_get_file_errors"),

    # load samples using a given sample type configuration file configuration
    path(f'sample/load/', load_samples, name="mission_samples_load_samples"),

    # ###### sample details ###### #

    path('sample/list/<int:mission_id>/', list_samples, name="mission_samples_sample_list"),

    path('sample/upload/sensor/<int:mission_id>/<int:sensor_id>/', add_sensor_to_upload, name="mission_samples_add_sensor_to_upload"),
    path(f'sample/batch/<int:mission_id>/', biochem_batches_card, name="mission_samples_biochem_batches_card"),

    path(f'sample/sample/error/<int:error_id>/', delete_file_error, name="mission_samples_delete_file_error"),
]
