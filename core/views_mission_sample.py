import io
import os
import threading
from threading import Thread

import bs4
import pandas as pd
from bs4 import BeautifulSoup
from crispy_forms.utils import render_crispy_form
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


def process_file(file) -> [str, str, str]:
    file_name = file.name
    file_type = file_name.split('.')[-1].lower()

    # the file can only be read once per request
    data = file.read()

    return file_name, file_type, data


def get_file_config_forms(data, file_type) -> [forms.SampleTypeLoadForm]:
    config_forms = []
    file_configs = get_file_configs(data, file_type)

    if file_configs:
        for config in file_configs:
            config_forms.append(forms.SampleTypeLoadForm(instance=config))

    return config_forms


def create_div_id_sample_type_form(sample_type_form, file_config_form, **kwargs):
    html = render_crispy_form(sample_type_form)
    html += render_crispy_form(file_config_form)
    html = f'<div id="div_id_sample_type">{html}</div>'

    soup = BeautifulSoup(html, 'html.parser')
    submit_button = soup.new_tag('button')
    submit_button.attrs['hx-get'] = reverse_lazy('core:load_sample_type')
    submit_button.attrs['hx-target'] = "#div_id_loaded_sample_type"
    submit_button.attrs['hx-select'] = "#div_id_loaded_sample_type_message"
    submit_button.attrs['hx-swap'] = "afterbegin"

    submit_button.attrs['class'] = "btn btn-primary btn-sm"
    submit_button.attrs['name'] = "save"
    if 'config' in kwargs:
        submit_button.attrs['value'] = kwargs['config']

    svg = load_svg('plus-square')
    icon = BeautifulSoup(svg, 'html.parser').svg

    submit_button.append(icon)

    div_col = soup.new_tag('div')
    div_col['class'] = "col-auto ms-auto"
    div_col.append(submit_button)

    div_row = soup.new_tag('div')
    div_row.attrs['class'] = "row mt-2 justify-content-end"
    div_row.append(div_col)

    soup.find(id="div_id_sample_type").append(div_row)

    return soup


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
        mission_id = request.POST['mission_id']

        # I don't know how to tell the user what is going on here if no sample_file has been chosen
        # They shouldn't even be able to view the rest of the form with out it.
        file = request.FILES['sample_file']
        file_name, file_type, data = process_file(file)

        tab = int(request.POST['tab']) if 'tab' in request.POST else 0
        skip = int(request.POST['header']) if 'header' in request.POST else 0

        tab, skip, field_choices = get_headers(data, file_type, tab, skip)

        file_config_instance = None
        sample_type_instance = None

        if 'id' in request.POST:
            file_config_instance = models.SampleFileSettings.objects.get(pk=request.POST['id'])

        if 'short_name' in request.POST:
            sample_type_instance = models.SampleType.objects.filter(short_name=request.POST['short_name'])
            sample_type_instance = sample_type_instance[0] if sample_type_instance.exists() else None

        if file_config_instance:
            sample_type_instance = sample_type_instance if sample_type_instance else file_config_instance.sample_type
            sample_type_form = forms.SampleTypeForm(request.POST, instance=sample_type_instance)
            file_config_form = forms.SampleFileConfigurationForm(request.POST, instance=file_config_instance,
                                                                 field_choices=field_choices)
        elif sample_type_instance:
            sample_type_form = forms.SampleTypeForm(request.POST, instance=sample_type_instance)
            file_config_form = forms.SampleFileConfigurationForm(request.POST, field_choices=field_choices)
        else:
            sample_type_form = forms.SampleTypeForm(request.POST)
            file_config_form = forms.SampleFileConfigurationForm(request.POST, field_choices=field_choices)

        if sample_type_form.is_valid():
            sample_type: models.SampleType = sample_type_form.save()
            config_args = request.POST.dict()
            config_args['sample_type'] = sample_type
            if 'id' not in request.POST:
                file_config_form = forms.SampleFileConfigurationForm(config_args)

            if file_config_form.is_valid():
                file_settings: models.SampleFileSettings = file_config_form.save()
                if file_settings.sample_type != sample_type:
                    file_settings.sample_type = sample_type
                    file_settings.save()

                html = '<div id="div_id_sample_type"></div>'  # used to clear the message saying a file has to be loaded
                html += render_crispy_form(forms.SampleTypeLoadForm(instance=file_settings))

                return HttpResponse(html)
            else:
                # if the file config isn't valid then remove the sample type too
                sample_type.delete()

        soup = create_div_id_sample_type_form(sample_type_form, file_config_form, **kwargs)
        return HttpResponse(soup)


def new_sample_type(request, **kwargs):
    context = {}
    context.update(csrf(request))

    if request.method == "POST":

        if 'sample_file' not in request.FILES:
            soup = BeautifulSoup('<div id="div_id_sample_type"></div>', 'html.parser')

            div = soup.new_tag('div')
            div.attrs['class'] = 'alert alert-warning mt-2'
            div.string = _("File is required before adding sample")
            soup.find(id="div_id_sample_type").append(div)
            return HttpResponse(soup)

        file = request.FILES['sample_file']
        file_name, file_type, data = process_file(file)

        tab = 0
        skip = -1

        field_choices = []

        try:
            tab, skip, field_choices = get_headers(data, file_type, tab, skip)
        except IndexError as ex:
            # there's a chance we couldn't automatically detect a header row
            # in which case the user should be able to manually find it.
            logger.error(f"Could not detect header row for file {file_name}")
            logger.exception(ex)

        if 'config' in kwargs:
            config = models.SampleFileSettings.objects.get(pk=kwargs['config'])
            sample_type_form = forms.SampleTypeForm(instance=config.sample_type)
            file_config_form = forms.SampleFileConfigurationForm(
                field_choices=field_choices,
                instance=config
            )
        else:
            file_initial = {"file_type": file_type, "header": skip, "tab": tab}

            sample_type_form = forms.SampleTypeForm()
            file_config_form = forms.SampleFileConfigurationForm(
                initial=file_initial,
                field_choices=field_choices,
            )

        soup = create_div_id_sample_type_form(sample_type_form, file_config_form, **kwargs)
        return HttpResponse(soup)


def load_sample_type(request, **kwargs):

    context = {}
    context.update(csrf(request))

    if request.method == "GET":
        mission_id = request.GET['mission'] if 'mission' in request.GET else None
        saving = 'save' in request.GET
        loading = 'sample_file' in request.GET

        if saving or loading:
            # when the file changes we want to quickly clear the form and let the user know we're loading stuff

            # Let's make some soup
            soup = BeautifulSoup('', "html.parser")

            # create an alert area saying we're loading
            alert_div = soup.new_tag("div", attrs={'class': "alert alert-info mt-2"})
            alert_div.string = _("Loading") if loading else _("Saving") if saving else "Why are you even here?"

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
            url = None
            root_div = soup.new_tag("div")
            if loading:
                url = reverse_lazy("core:load_sample_type")
                oob_select = "#div_id_loaded_samples_list:afterbegin, #div_id_sample_type:outerHTML"
            elif saving:
                # when the form is loaded using the edit button, the 'core/partials/form_sample_type.html'
                # template gets a config id which is added to the save button for the new sample form
                # if the config id is present we're updating a config, otherwise creating a new sampletype/config
                if request.GET['save']:
                    config = models.SampleFileSettings.objects.get(pk=int(request.GET['save']))
                    url = reverse_lazy("core:save_sample_type", args=(config.pk,))
                    card_id = f"div_id_{config.sample_type.short_name}_{config.pk}"
                    oob_select = f"#{card_id}:outerHTML, #div_id_sample_type:outerHTML"
                else:
                    url = reverse_lazy("core:save_sample_type")
                    oob_select = "#div_id_sample_type:outerHTML"
            else:
                raise Http404("Why are you here?")

            root_div.attrs = {
                'id': "div_id_loaded_sample_type_message",
                'hx-trigger': "load",
                'hx-post': url,
                'hx-target': "#div_id_loaded_sample_type_message",
                'hx-swap': "outerHTML",
                'hx-select-oob': oob_select,
            }

            root_div.append(alert_div)
            root_div.append(progress_bar_div)
            soup.append(root_div)

            return HttpResponse(soup)

        if request.htmx:
            # if this is an htmx request it's to grab an updated element from the form, like the BioChem Datatype
            # field after the Datatype_filter has been triggered.
            sample_type_form = forms.SampleTypeForm(initial=request.GET)
            html = render_crispy_form(sample_type_form)
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

        if 'config' in kwargs:
            return new_sample_type(request, config=kwargs['config'])

        file = request.FILES['sample_file']
        file_name, file_type, data = process_file(file)

        # If mission ID is present this is an initial page load from the sample_file input
        # We want to locate file configurations that match this file_type
        config_forms: [forms.SampleTypeLoadForm] = get_file_config_forms(data, file_type)

        html = '<div id="div_id_sample_type"></div>'  # used to clear the message saying a file has to be loaded
        if config_forms:
            for config in config_forms:
                html += render_crispy_form(config)
        else:
            soup = BeautifulSoup(html, 'html.parser')
            alert_div = soup.new_tag("div", attrs={'class': "alert alert-warning mt-2"})
            alert_div.string = _("No File Configurations Found")
            soup.find(id="div_id_sample_type").append(alert_div)
            return HttpResponse(soup)

        # html = render_block_to_string("core/partials/form_sample_type.html", "loaded_samples_block",
        #                               context=context)
        return HttpResponse(html)


def load_samples(request, **kwargs):
    # Either delete a file configuration or load the samples from the sample file
    context = {}
    context.update(csrf(request))

    config_id = kwargs['config']
    load_block = "loaded_sample_list_block"

    if request.method == "POST":
        mission_id = request.POST['mission_id']

        # Todo: Add a unit test to test that the message block gets shown if no file is
        #  present when this function is active
        if 'sample_file' not in request.FILES:
            context['message'] = _("File is required before adding sample")
            html = render_block_to_string("core/partials/form_sample_type.html", load_block,
                                          context=context)
            return HttpResponse(html)

        file = request.FILES['sample_file']
        file_name, file_type, data = process_file(file)

        if 'load' in request.POST:
            file_config = models.SampleFileSettings.objects.get(pk=config_id)
            mission = models.Mission.objects.get(pk=mission_id)
            dataframe = get_excel_dataframe(stream=data, sheet_number=file_config.tab, header_row=file_config.header)

            button_class = "btn btn-success btn-sm"
            try:
                errors = parse_data_frame(mission=mission, settings=file_config, file_name=file_name, dataframe=dataframe)
                if errors:
                    models.FileError.objects.bulk_create(errors)

                errors = models.FileError.objects.filter(file_name=file_name)
                if errors.exists():
                    button_class = "btn btn-warning btn-sm"
            except Exception as ex:
                logger.error(f"Failed to load file {file_name}")
                logger.exception(ex)
                button_class = "btn btn-danger btn-sm"

            url = reverse_lazy('core:load_samples', args=(file_config.pk,))
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


def delete_config(request, **kwargs):

    config_id = kwargs['config']
    if request.method == "POST":
        models.SampleFileSettings.objects.get(pk=config_id).delete()

    return HttpResponse()


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
    columns = ["Sample", "Pressure", "Sensor", "Replicate", "Value"]
    if sensor_id:
        queryset = models.Sample.objects.filter(type_id=sensor_id, bottle__in=bottle_limit)
        queryset = queryset.order_by('bottle__bottle_id')
        queryset = queryset.values(
            'bottle__bottle_id',
            'bottle__pressure',
            'type__id',
            'discrete_value__replicate',
            'discrete_value__value',
            'discrete_value__flag',
            'discrete_value__sample_datatype',
        )
        headings = ['Flag', 'Datatype']
        df = read_frame(queryset)
        df.columns = columns + headings

    else:
        queryset = models.Sample.objects.filter(bottle__in=bottle_limit)
        queryset = queryset.order_by('bottle__bottle_id')
        queryset = queryset.values(
            'bottle__bottle_id',
            'bottle__pressure',
            'type__id',
            'discrete_value__replicate',
            'discrete_value__value',
        )
        df = read_frame(queryset)
        df.columns = columns

    if not queryset.exists():
        soup = BeautifulSoup('<table id="sample_table"></table>', 'html.parser')
        response = HttpResponse(soup)
        return response

    df = df.pivot(index=['Sample', 'Pressure'], columns=['Sensor', 'Replicate'])
    if not sensor_id:
        df = df.reindex(sorted(df.columns), axis=1)
    # Pandas has the ability to render dataframes as HTML and it's super fast, but the default table looks awful.
    html = '<div id="sample_table">' + df.to_html() + "</div>"

    # Using BeautifulSoup for html manipulation to post process the HTML table Pandas created
    soup = BeautifulSoup(html, 'html.parser')

    # this will be a big table add scrolling
    sample_table = soup.find(id="sample_table")
    sample_table.attrs['class'] = "vertical-scrollbar"

    # add styles to the table so it's consistant with the rest of the application
    table = soup.find('table')
    table.attrs['class'] = 'dataframe table table-striped tscroll'

    # remove the first table row pandas adds for the "Value" column header
    soup.find("thead").find("tr").decompose()

    # The next few rows will be the 'Sensor' row with labels like C0SM, T090C, and oxy
    # followed by the 'replicate' row that describes if this is a single, double, triple sample.

    # We're going to flatten the headers down to one row then remove the others.

    sensor_headers = soup.find("thead").find("tr")

    # this is the replicate column, get rid of it for now
    replicate_headers = sensor_headers.findNext("tr")

    # we aren't doing anything else with these for now.
    replicate_headers.decompose()

    # we now have two header rows. The first contains all the sensor/sample names. The second contains the "Sample"
    # and "Pressure" labels. I want to copy the first two columns from the second header to the first two columns
    # of the first header (because the labels might be translated) then delete the second row
    index_headers = soup.find('tr').findNext('tr')
    index_column = index_headers.find('th')

    sensor_column = sensor_headers.find('th')
    sensor_column.string = index_column.string

    index_column = index_column.findNext('th')
    sensor_column = sensor_column.findNext('th')
    sensor_column.string = index_column.string

    index_headers.decompose()

    column = sensor_column.findNext('th')  # Sensor column

    if sensor_id:

        # if the sensor_id is present then we want to show the specific details for this sensor/sample
        pk = column.string
        sampletype = models.SampleType.objects.get(pk=pk)
        column.string = f'{sampletype.short_name}'

        data_type_label = soup.new_tag("div")
        data_type_label.attrs['class'] = 'col-auto fw-bold'
        data_type_label.string = _("Sensor Datatype") + " : "

        data_type_value = soup.new_tag("div")
        data_type_value.attrs['class'] = "col-auto"
        data_type_value.string = str(sampletype.datatype.pk) if sampletype.datatype else _("None")

        data_type_des_des = soup.new_tag("div")
        data_type_des_des.attrs['class'] = "col-auto fw-bold"
        data_type_des_des.string = _("Datatype Description") + " : "

        data_type_des_value = soup.new_tag("div")
        data_type_des_value.attrs['class'] = "col"
        data_type_des_value.string = sampletype.datatype.description if sampletype.datatype else _("None")

        sensor_details_row = soup.new_tag("div")
        sensor_details_row.attrs['class'] = "row alert alert-secondary mt-2"
        sensor_details_row.append(data_type_label)
        sensor_details_row.append(data_type_value)
        sensor_details_row.append(data_type_des_des)
        sensor_details_row.append(data_type_des_value)

        sensor_row_container = soup.new_tag("div")
        sensor_row_container.attrs['class'] = "container-fluid"
        sensor_row_container.append(sensor_details_row)

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
        delete_button.attrs['hx-post'] = reverse_lazy('core:hx_sample_delete', args=(mission_id, sensor_id,))
        delete_button.attrs['hx-target'] = "#sample_table"
        delete_button.attrs['hx-swap'] = 'outerHTML'
        delete_button.attrs['hx-confirm'] = _("Are you sure?")
        delete_button.attrs['title'] = _("Delete")
        delete_button.attrs['name'] = 'delete'
        svg = dart2.utils.load_svg('dash-square')
        icon = BeautifulSoup(svg, 'html.parser').svg
        delete_button.append(icon)

        col_1 = soup.new_tag('div')
        col_1.attrs['class'] = 'col'
        col_1.append(back_button)

        col_2 = soup.new_tag('div')
        col_2.attrs['class'] = 'col-auto'
        col_2.append(delete_button)

        button_row = soup.new_tag('div')
        button_row.attrs['class'] = 'row justify-content-between'
        button_row.append(col_1)
        button_row.append(col_2)

        root.append(button_row)
        root.append(sensor_row_container)
        root.append(table)

    else:
        # if the sensor_id is not present then we're showing all of the sensor/sample tables with each
        # column label to take the user to the sensor details page

        # now add htmx tags to the rest of the TH elements in the row so the user
        # can click that row for details on the sensor
        while column:
            column['class'] = 'text-center text-nowrap'

            pk = column.string
            sampletype = models.SampleType.objects.get(pk=pk)

            button = soup.new_tag("button")
            button.string = f'{sampletype.short_name}'
            column.string = ''
            button.attrs['class'] = 'btn btn-primary'
            button.attrs['style'] = 'width: 100%'
            button.attrs['hx-trigger'] = 'click'
            button.attrs['hx-get'] = reverse_lazy('core:hx_sample_list', args=(mission_id, sampletype.pk,))
            button.attrs['hx-target'] = "#sample_table"
            button.attrs['hx-swap'] = 'outerHTML'
            button.attrs['title'] = sampletype.long_name

            column.append(button)

            column = column.find_next_sibling('th')

        # finally, align all text in each column to the center of the cell
        tds = table.find_all('td')
        for td in tds:
            td['class'] = 'text-center'

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


def hx_sample_delete(request, **kwargs):

    mission = kwargs['mission_id']
    sample_type = kwargs['sample_type_id']
    if request.method == "POST":
        models.Sample.objects.filter(type=sample_type).delete()

    return hx_list_samples(request, mission_id=mission)
