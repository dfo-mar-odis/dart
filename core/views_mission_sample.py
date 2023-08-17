import io
import os
import threading
from threading import Thread

import bs4
import pandas as pd
from bs4 import BeautifulSoup
from django.http import HttpResponse, Http404
from django.template.context_processors import csrf
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django_pandas.io import read_frame
from render_block import render_block_to_string

import dart2.utils
from biochem import models

from core import forms
from core import models
from core.parsers.SampleParser import get_headers, get_file_configs, parse_data_frame, get_excel_dataframe
from core.views import logger, sample_file_queue, load_ctd_files

from dart2.utils import load_svg

import logging

logger = logging.getLogger('dart')


def save_sample_type(request, **kwargs):
    # Validate and save the mission form once the user has filled out the details
    #
    # Template: 'core/partials/form_sample_type.html template
    #
    # return the sample_type_block if the sample_type or the file configuration forms fail
    # returns the loaded_samples_block if the forms validate and the objects are created

    context = {}
    context.update(csrf(request))

    if request.method == "POST":
        mission_id = kwargs['mission']
        context['mission'] = models.Mission.objects.get(pk=mission_id)

        # I don't know how to tell the user what is going on here if no sample_file has been chosen
        # They shouldn't even be able to view the rest of the form with out it.
        file = request.FILES['sample_file']
        file_name = file.name
        context['file'] = file_name
        file_type = file_name.split('.')[-1].lower()

        tab = int(request.POST['tab']) if 'tab' in request.POST else 0
        skip = int(request.POST['header']) if 'header' in request.POST else 0

        data = file.read()
        tab, skip, field_choices = get_headers(data, file_type, tab, skip)

        sample_type_form = forms.SampleTypeForm(request.POST)
        file_config_form = forms.SampleFileConfigurationForm(request.POST, field_choices=field_choices)
        if sample_type_form.is_valid():
            sample_type: models.SampleType = sample_type_form.save()
            config_args = request.POST.dict()
            config_args['sample_type'] = sample_type
            file_config_form = forms.SampleFileConfigurationForm(config_args)
            if file_config_form.is_valid():
                file_settings: models.SampleFileSettings = file_config_form.save()
                lowercase_fields = [field[0] for field in field_choices]

                file_configs = models.SampleFileSettings.objects.filter(
                    file_type=file_settings.file_type, tab=file_settings.tab, header=file_settings.header,
                    sample_field__in=lowercase_fields, value_field__in=lowercase_fields
                )

                context['file_configurations'] = []
                if file_configs:
                    for config in file_configs:
                        context['file_configurations'].append(forms.SampleTypeLoadForm(mission_id=mission_id,
                                                                                       instance=config))

                html = render_block_to_string("core/partials/form_sample_type.html", "loaded_samples_block",
                                              context=context)
                return HttpResponse(html)
            else:
                # if the file config isn't valid then remove the sample type too
                sample_type.delete()
        context['sample_type_form'] = sample_type_form
        context['file_form'] = file_config_form
        context['file_configurations'] = get_file_config_forms(mission_id, data, file_type)

        html = render_block_to_string("core/partials/form_sample_type.html", "loaded_samples_block", context=context)
        return HttpResponse(html)


def get_file_config_forms(mission_id, data, file_type) -> [forms.SampleTypeLoadForm]:
    config_forms = []
    file_configs = get_file_configs(data, file_type)

    if file_configs:
        for config in file_configs:
            config_forms.append(forms.SampleTypeLoadForm(mission_id=mission_id, instance=config))

    return config_forms


def load_sample_type(request, **kwargs):

    context = {}
    context.update(csrf(request))

    # the mission id is used to determine if we're actually going to save anything or if we're just process
    # and sending back updated forms
    mission_id = kwargs['mission'] if 'mission' in kwargs else None
    if request.method == "GET":
        if 'sample_file' in request.GET:
            # when the file changes we want to quickly clear the form and let the user know we're loading stuff
            # Let's make some soup
            soup = BeautifulSoup('', "html.parser")

            # create an alert area saying we're loading
            alert_div = soup.new_tag("div", attrs={'class': "alert alert-info mt-2"})
            alert_div.string = _("Loading")

            # create a progress bar to give the user something to stare at while they wait.
            progress_bar = soup.new_tag("div")
            progress_bar.attrs = {
                'class': "progress-bar progress-bar-striped progress-bar-animated",
                'role': "progressbar",
                'style': "width: 100%"
            }
            progress_bar_div = soup.new_tag("div", attrs={'class': "progress"})
            progress_bar_div.append(progress_bar)

            # create the root 'div_id_loaded_sample_type' element that the 'sample_file' input is replacing
            # and set it up so as soon as it's on the page it'll send an htmx request to load sample types
            # that match the file the file input field contains, then this div will replace itself with the results
            root_div = soup.new_tag("div")
            root_div.attrs = {
                'id': "div_id_loaded_sample_type",
                'hx-trigger': "load",
                'hx-post': reverse_lazy("core:load_sample_type", args=(mission_id,)),
                'hx-target': "#div_id_loaded_sample_type",
                'hx-select': "#div_id_loaded_sample_type",
                'hx-swap': "outerHTML"
            }

            root_div.append(alert_div)
            root_div.append(progress_bar_div)
            soup.append(root_div)

            return HttpResponse(soup)

        if request.htmx:
            # if this is an htmx request it's to grab an updated element from the form, like the BioChem Datatype
            # field after the Datatype_filter has been triggered.
            sample_type_form = forms.SampleTypeForm(initial=request.GET, post_url=request.path)
            context['sample_type_form'] = sample_type_form
            html = render_block_to_string("core/partials/form_sample_type.html", "sample_type_form_block",
                                          context=context)
            return HttpResponse(html)

        if mission_id is None:
            raise Http404(_("Mission does not exist"))

        context['object'] = models.Mission.objects.get(pk=mission_id)
        html = render_to_string("core/mission_samples.html", request=request, context=context)
        return HttpResponse(html)
    elif request.method == "POST":

        if 'sample_file' not in request.FILES:
            context['message'] = _("File is required before adding sample")
            html = render_block_to_string("core/partials/form_sample_type.html", "sample_type_block", context=context)
            return HttpResponse(html)

        file = request.FILES['sample_file']
        file_name = file.name
        context['file'] = file_name
        file_type = file_name.split('.')[-1].lower()

        data = file.read()

        if not mission_id or 'add_sample' in request.POST:
            # if the add sample button was pressed we want to reset the form
            add_sample = 'add_sample' in request.POST
            if mission_id:
                context['mission'] = models.Mission.objects.get(pk=mission_id)

            field_choices = []
            tab = int(request.POST['tab']) if 'tab' in request.POST and not add_sample else 0
            skip = int(request.POST['header']) if 'header' in request.POST and not add_sample else -1

            try:
                tab, skip, field_choices = get_headers(data, file_type, tab, skip)
            except IndexError as ex:
                # there's a chance we couldn't automatically detect a header row
                # in which case the user should be able to manually find it.
                logger.error(f"Could not detect header row for file {file_name}")
                logger.exception(ex)

            file_initial = {"file_type": file_type, "header": skip, "tab": tab}

            sample_type_form = forms.SampleTypeForm(post_url=request.path)
            file_config_form = forms.SampleFileConfigurationForm(
                initial=file_initial,
                field_choices=field_choices,
            )
            context['sample_type_form'] = sample_type_form
            context['file_form'] = file_config_form
            html = render_block_to_string("core/partials/form_sample_type.html", "sample_type_block",
                                          context=context)
            return HttpResponse(html)

        # If mission ID is present this is an initial page load from the sample_file input
        # We want to locate file configurations that match this file_type
        context['file_configurations'] = get_file_config_forms(mission_id, data, file_type)
        html = render_block_to_string("core/partials/form_sample_type.html", "loaded_samples_block",
                                      context=context)
        return HttpResponse(html)


def load_samples(request, **kwargs):
    context = {}
    context.update(csrf(request))

    mission_id = kwargs['mission']
    config_id = kwargs['config']
    load_block = "loaded_sample_list_block"

    if request.method == "POST":
        # Todo: Add a unit test to test that the message block gets shown if no file is
        #  present when this function is active
        if 'sample_file' not in request.FILES:
            context['message'] = _("File is required before adding sample")
            html = render_block_to_string("core/partials/form_sample_type.html", load_block,
                                          context=context)
            return HttpResponse(html)

        file = request.FILES['sample_file']
        file_name = file.name
        context['file'] = file_name
        file_type = file_name.split('.')[-1].lower()

        data = file.read()

        if 'load' in request.POST:
            file_config = models.SampleFileSettings.objects.get(pk=config_id)
            mission = models.Mission.objects.get(pk=mission_id)
            dataframe = get_excel_dataframe(stream=data, sheet_number=file_config.tab, header_row=file_config.header)

            button_class = "btn btn-success btn-sm"
            try:
                parse_data_frame(mission=mission, file_settings=file_config, file_name=file_name, dataframe=dataframe)

                errors = models.FileError.objects.filter(file_name=file_name)
                if errors.exists():
                    button_class = "btn btn-warning btn-sm"
            except Exception as ex:
                logger.error(f"Failed to load file {file_name}")
                logger.exception(ex)
                button_class = "btn btn-danger btn-sm"

            url = reverse_lazy('core:load_samples', args=(mission_id, file_config.pk,))
            soup = BeautifulSoup('', 'html.parser')
            button = soup.new_tag('button')
            button.attrs = {
                'id': "id_load_button",
                'name': "load",
                'hx-post': url,
                'hx-swap': "outerHTML",
                'class': button_class
            }

            soup.append(button)
            icon = BeautifulSoup(load_svg("folder-check"), 'html.parser').svg
            button.append(icon)
            response = HttpResponse(soup)
            response['HX-Trigger'] = 'update_samples'
            return response

        if 'delete' in request.POST:

            models.SampleFileSettings.objects.get(pk=config_id).delete()

            context['file_configurations'] = get_file_config_forms(mission_id, data, file_type)

            html = render_block_to_string("core/partials/form_sample_type.html", load_block, context=context)
            return HttpResponse(html)


def hx_sample_form(request, mission_id):
    context = {}
    context.update(csrf(request))

    mission = models.Mission.objects.get(pk=mission_id)
    if request.method == "GET":

        datatype_filter = request.GET['datatype_filter'] if 'datatype_filter' in request.GET else None
        initial = {"mission": mission_id, 'datatype_filter': datatype_filter}
        if request.FILES:
            initial['file'] = request.FILES['file']

        # context['sample_form'] = forms.NewSampleForm(initial=initial)
        context['object'] = mission
        html = render_block_to_string('core/mission_samples.html', 'new_sample_form_block', context)
        response = HttpResponse(html)

        return response

    elif request.method == "POST":
        datatype_filter = request.GET['datatype_filter'] if 'datatype_filter' in request.GET else None
        initial = {"mission": mission_id, 'datatype_filter': datatype_filter}

        file_data = None
        if request.FILES:
            file = request.FILES['file']
            initial['file_name'] = file.name
            file_data = file.read().decode('utf-8')
            initial['file_data'] = file_data

        # A POST action is required to upload a file even to just read a couple lines of it, but if the POST
        # request comes form a 'choose file' changed event then the 'submit' button won't be in the POST request
        # so we can update the form the user sees here when they select a file and ask them to choose tabs and columns
        # that we'll need to know when processing the file.
        if 'submit' not in request.POST:
            context['sample_form'] = forms.NewSampleForm(initial=initial)
            html = render_block_to_string('core/mission_samples.html', 'new_sample_form_block', context)
            response = HttpResponse(html)

            return response

        form = forms.NewSampleForm(request.POST, initial=initial)
        if form.is_valid():
            tab = int(request.POST['tab']) if 'tab' in request.POST else -1
            skip_lines = int(request.POST['skip_lines']) if 'skip_lines' in request.POST else -1
            sample_column = int(request.POST['sample_id_col']) if 'sample_id_col' in request.POST else -1
            value_column = int(request.POST['sample_value_col']) if 'sample_value_col' in request.POST else -1

            stream = io.StringIO(file_data)
            df = pd.read_csv(filepath_or_buffer=stream, header=skip_lines)
            dart2.utils.parse_csv_sample_file(df, sample_column, value_column)

            logger.info(f"Processing file {file.name}")
            context['sample_form'] = forms.NewSampleForm(initial={"mission": mission_id})
            html = render_block_to_string('core/mission_samples.html', 'new_sample_form_block', context)
            response = HttpResponse(html)

            return response

        context['sample_form'] = form
        html = render_block_to_string('core/mission_samples.html', 'new_sample_form_block', context)
        response = HttpResponse(html)
        return response


def hx_sample_upload_ctd(request, mission_id):
    context = {}
    context.update(csrf(request))

    thread_name = "load_ctd_files"

    if request.method == "GET":
        bottle_dir = request.GET['bottle_dir']
        files = [f for f in os.listdir(bottle_dir) if f.lower().endswith('.btl')]
        files.sort(key=lambda fn: os.path.getmtime(os.path.join(bottle_dir, fn)))
        context['file_form'] = forms.BottleSelection(initial={'mission': mission_id,
                                                              'bottle_dir': bottle_dir,
                                                              'file_name': files})
        html = render_block_to_string('core/mission_samples.html', 'ctd_list', context=context)
        response = HttpResponse(html)

        mission = models.Mission.objects.get(pk=mission_id)
        mission.bottle_directory = bottle_dir
        mission.save()

        return response
    elif request.method == "POST":
        bottle_dir = request.POST['bottle_dir']
        files = request.POST.getlist('file_name')
        mission = models.Mission.objects.get(pk=mission_id)

        logger.info(sample_file_queue.empty())
        for file in files:
            sample_file_queue.put({"mission": mission, "file": file, "bottle_dir": bottle_dir})

        start = True
        for thread in threading.enumerate():
            if thread.name == thread_name:
                start = False

        if start:
            Thread(target=load_ctd_files, name=thread_name, daemon=True, args=(mission,)).start()

        context['object'] = mission
        html = render_block_to_string('core/mission_samples.html', 'ctd_list', context=context)
        response = HttpResponse(html)
        return response
    response = HttpResponse("Hi!")
    return response


def soup_split_column(soup: BeautifulSoup, column: bs4.Tag) -> bs4.Tag:
    # if the th colspan is > 1 it's because there are replicates, the column should be split up
    # return the last column
    if 'colspan' in column.attrs and int(column.attrs['colspan']) > 1:
        label = column.string
        col_count = int(column.attrs['colspan'])
        column.attrs['colspan'] = 1
        column.string = f'{label}-1'
        for i in range(1, col_count):
            new_th = soup.new_tag('th')
            new_th.attrs = column.attrs
            new_th.string = f'{label}-{str(i + 1)}'
            column.insert_after(new_th)
            column = new_th

    return column


def hx_list_samples(request, **kwargs):
    context = {}

    mission_id = kwargs['mission_id']
    sensor_id = kwargs['sensor_id'] if 'sensor_id' in kwargs else None

    page = int(request.GET['page'] if 'page' in request.GET else 0)
    page_limit = 50
    page_start = page_limit * page

    mission = models.Mission.objects.get(pk=mission_id)
    bottle_limit = models.Bottle.objects.filter(event__mission=mission).order_by('bottle_id')[page_start:(page_start+page_limit)]
    headings = []
    if sensor_id:
        queryset = models.Sample.objects.filter(type_id=sensor_id, bottle__in=bottle_limit)
        queryset = queryset.order_by('bottle__bottle_id')
        queryset = queryset.values(
            'type__short_name', 'bottle__bottle_id', 'bottle__pressure', 'discrete_value__value',
            'discrete_value__replicate', 'discrete_value__flag', 'discrete_value__sample_datatype'
        )
        headings = ['Flag', 'Datatype']
        df = read_frame(queryset)
        df.columns = ["Sensor", "Sample", "Pressure", "Value", 'Replicate',] + headings

    else:
        queryset = models.Sample.objects.filter(bottle__in=bottle_limit)
        queryset = queryset.order_by('bottle__bottle_id')
        queryset = queryset.values(
            'type__short_name',
            'bottle__bottle_id',
            'bottle__pressure',
            'discrete_value__value',
            'discrete_value__replicate'
        )
        df = read_frame(queryset)
        df.columns = ["Sensor", "Sample", "Pressure", "Value", "Replicate"]

    if not queryset.exists():
        soup = BeautifulSoup('<table id="sample_table"></table>', 'html.parser')
        response = HttpResponse(soup)
        return response

    df = df.pivot(index=['Sample', 'Pressure'], columns=['Sensor', 'Replicate'])
    # df = df.groupby(["Sample", 'Sensor']).count().reset_index()
    html = '<div id="sample_table">' + df.to_html(classes=['table', 'table-striped', 'tscroll']) + "</div>"

    # Using BeautifulSoup for html manipulation to post process the HTML table Pandas created
    soup = BeautifulSoup(html, 'html.parser')

    table = soup.find('table')

    # remove the first table row pandas adds for the "Value" column header
    soup.find("thead").find("tr").decompose()

    # This row contains the headers we actually want... Except for the 'Sensor' header
    # fix the headers, then remove the 'index' table row
    sensor_headers = soup.find("thead").find("tr")

    # this is the replicate column, get rid of it for now
    replicate_headers = sensor_headers.findNext("tr")
    replicate_headers.decompose()

    index_headers = soup.find("thead").find("tr").find_next("tr")

    column = sensor_headers.find('th')  # blank column
    index = index_headers.find('th')  # Sample column

    column.string = index.string

    column = column.find_next_sibling('th')  # blank column
    index = index.find_next_sibling('th')  # Pressure Column

    column.string = index.string

    index_headers.decompose()

    column = column.find_next_sibling('th')  # Sensor column

    if sensor_id:

        # if the sensor_id is present then we want to show the specific details for this sensor/sample
        short_name = column.string
        sensor = models.SampleType.objects.get(short_name=short_name)

        sensor_row = soup.new_tag("div")
        sensor_row.attrs['class'] = "row alert alert-info mt-2"

        data_type_label = soup.new_tag("div")
        data_type_label.attrs['class'] = 'col-auto'
        data_type_label.string = _("Sensor Datatype")
        sensor_row.append(data_type_label)

        data_type_value = soup.new_tag("div")
        data_type_value.attrs['class'] = "col-auto"
        data_type_value.string = str(sensor.datatype.pk) if sensor.datatype else _("None")
        sensor_row.append(data_type_value)

        data_type_des_des = soup.new_tag("div")
        data_type_des_des.attrs['class'] = "col-auto"
        data_type_des_des.string = _("Datatype Description")
        sensor_row.append(data_type_des_des)

        data_type_des_value = soup.new_tag("div")
        data_type_des_value.attrs['class'] = "col"
        data_type_des_value.string = sensor.datatype.description if sensor.datatype else _("None")
        sensor_row.append(data_type_des_value)

        col_span = -1
        # if we're looking at a sensor then keep the first column label, but change the next two

        column = soup_split_column(soup, column)

        column = column.find_next_sibling('th')

        for heading in headings:
            column.string = heading
            span = 1
            if 'colspan' in column.attrs:
                span = int(column.attrs['colspan'])

            column = soup_split_column(soup, column)

            column = column.find_next_sibling('th')
            col_span += span

        root = soup.findChildren()[0]

        # create a button so the user can go back to viewing all loaded sensors/samples
        back_button = soup.new_tag('button')
        back_button.attrs['class'] = 'btn btn-primary'
        back_button.attrs['hx-trigger'] = 'click'
        back_button.attrs['hx-get'] = reverse_lazy('core:hx_sample_list', args=(mission_id,))
        back_button.attrs['hx-target'] = "#sample_table"
        back_button.attrs['hx-swap'] = 'outerHTML'
        back_button.attrs['title'] = _("Back")
        back_button.attrs['name'] = 'back'
        svg = dart2.utils.load_svg('arrow-left-square')
        icon = BeautifulSoup(svg, 'html.parser').svg
        back_button.append(icon)

        # create a button to remove discrete samples
        delete_button = soup.new_tag('button')
        delete_button.attrs['class'] = 'btn btn-danger'
        delete_button.attrs['hx-trigger'] = 'click'
        delete_button.attrs['hx-post'] = reverse_lazy('core:hx_sample_list', args=(mission_id, sensor_id,))
        delete_button.attrs['hx-target'] = "#sample_table"
        delete_button.attrs['hx-swap'] = 'outerHTML'
        delete_button.attrs['title'] = _("Delete")
        delete_button.attrs['name'] = 'delete'
        svg = dart2.utils.load_svg('dash-square')
        icon = BeautifulSoup(svg, 'html.parser').svg
        delete_button.append(icon)

        root.append(back_button)
        root.append(sensor_row)
        root.append(table)

    else:
        tds = table.find_all('td')
        for td in tds:
            td['class'] = 'text-center'
        # now add htmx tags to the rest of the TH elements in the row so the user
        # can click that row for details on the sensor
        while column:
            column['class'] = 'text-center text-nowrap'

            short_name = column.string
            sampletype = models.SampleType.objects.get(short_name=short_name)
            button = soup.new_tag("button")
            button.string = short_name
            column.string = ''
            button.attrs['class'] = 'btn btn-primary'
            button.attrs['hx-trigger'] = 'click'
            button.attrs['hx-get'] = reverse_lazy('core:hx_sample_list', args=(mission_id, sampletype.pk,))
            button.attrs['hx-target'] = "#sample_table"
            button.attrs['hx-swap'] = 'outerHTML'
            button.attrs['title'] = sampletype.long_name

            column.append(button)

            column = column.find_next_sibling('th')

    # now we'll attach an HTMX call to the last queried table row so when the user scrolls to it the next batch
    # of samples will be loaded into the table.
    args = (mission_id, sensor_id,) if sensor_id else (mission_id,)
    last_tr = table.find('tbody').find_all('tr')[-1]
    last_tr.attrs['hx-target'] = 'this'
    last_tr.attrs['hx-trigger'] = 'intersect once'
    last_tr.attrs['hx-get'] = reverse_lazy('core:hx_sample_list', args=args) + f"?page={page+1}"
    last_tr.attrs['hx-swap'] = "afterend"

    if page > 0:
        response = HttpResponse(soup.find('tbody').findAll('tr', recursive=False))
    else:
        response = HttpResponse(soup)
    return response