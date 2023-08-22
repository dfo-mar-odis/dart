import numpy as np
import os
import threading
from threading import Thread

import bs4
import pandas as pd
from bs4 import BeautifulSoup
from crispy_forms.utils import render_crispy_form
from django.db.models import Max
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
from core.views import sample_file_queue, load_ctd_files, MissionMixin, reports

from dart2.utils import load_svg

from dart2.views import GenericDetailView

import logging

logger = logging.getLogger('dart')


def process_file(file) -> [str, str, str]:
    file_name = file.name
    file_type = file_name.split('.')[-1].lower()

    # the file can only be read once per request
    data = file.read()

    return file_name, file_type, data


def get_alert(soup, message, alert_type):
    # creates an alert dialog with an animated progress bar to let the user know we're saving or loading something

    # type should be a bootstrap css type, (danger, info, warning, success, etc.)

    # create an alert area saying we're loading
    alert_div = soup.new_tag("div", attrs={'class': f"alert alert-{alert_type} mt-2"})
    alert_div.string = message

    # create a progress bar to give the user something to stare at while they wait.
    progress_bar = soup.new_tag("div")
    progress_bar.attrs = {
        'class': "progress-bar progress-bar-striped progress-bar-animated",
        'role': "progressbar",
        'style': "width: 100%"
    }
    progress_bar_div = soup.new_tag("div", attrs={'class': "progress"})
    progress_bar_div.append(progress_bar)

    alert_div.append(progress_bar_div)

    return alert_div


def get_file_config_forms(data, file_type) -> [forms.SampleTypeLoadForm]:
    config_forms = []
    file_configs = get_file_configs(data, file_type)

    if file_configs:
        for config in file_configs:
            config_forms.append(forms.SampleTypeLoadForm(instance=config))

    return config_forms


def get_error_list(soup, card_id, errors):

    msg_div = soup.find(id=f'{card_id}_message')
    if not msg_div:
        msg_div = soup.new_tag('div')
        msg_div.attrs['class'] = ''
        msg_div.attrs['id'] = f'{card_id}_message'
        soup.append(msg_div)

    msg_div_error_card = soup.new_tag('div')
    msg_div_error_card.attrs['class'] = 'card mt-2'
    msg_div.append(msg_div_error_card)

    msg_div_error_card_header = soup.new_tag('div')
    msg_div_error_card_header.attrs['class'] = 'card-header text-bg-warning'
    msg_div_error_card.append(msg_div_error_card_header)

    msg_div_error_title = soup.new_tag('div')
    msg_div_error_title.string = _("Warnings")
    msg_div_error_title.attrs['class'] = 'card-title'
    msg_div_error_card_header.append(msg_div_error_title)

    msg_div_error_card_body = soup.new_tag('div')
    msg_div_error_card_body.attrs['class'] = 'card-body vertical-scrollbar-sm'
    msg_div_error_card.append(msg_div_error_card_body)

    ul_list = soup.new_tag('ul')
    ul_list['id'] = f'{card_id}_error_list'
    ul_list['class'] = 'list-group'
    msg_div_error_card_body.append(ul_list)
    for error in errors:
        li = soup.new_tag('li')
        li['class'] = 'list-group-item'
        li.string = error.message
        ul_list.append(li)


def save_sample_type(request, **kwargs):
    # Validate and save the mission form once the user has filled out the details
    #
    # Template: 'core/partials/form_sample_type.html template
    #
    # return the sample_type_block if the sample_type or the file configuration forms fail
    # returns the loaded_samples_block if the forms validate and the objects are created

    context = {}
    context.update(csrf(request))

    if request.method == "GET":
        if 'sample_type_id' in kwargs and 'update_sample_type' in request.GET:
            sample_type = models.SampleType.objects.get(pk=kwargs['sample_type_id'])
            url = reverse_lazy("core:save_sample_type", args=(sample_type.pk,))
            oob_select = f"#div_id_sample_type, #div_id_{sample_type.pk}:outerHTML"
        else:
            url = reverse_lazy("core:save_sample_type")
            oob_select = "#div_id_sample_type, #div_id_loaded_samples_list:beforeend"

        soup = BeautifulSoup('', "html.parser")

        root_div = soup.new_tag("div")
        alert_div = get_alert(soup, _("Saving"), 'info')

        root_div.attrs = {
            'id': "div_id_loaded_sample_type_message",
            'hx-trigger': "load",
            'hx-target': "#div_id_sample_type",
            'hx-select-oob': oob_select,
            'hx-post': url,
        }

        root_div.append(alert_div)
        soup.append(root_div)

        return HttpResponse(soup)
    elif request.method == "POST":
        # mission_id is a hidden field in the 'core/partials/form_sample_type.html' template, if it's needed
        # mission_id = request.POST['mission_id']

        # I don't know how to tell the user what is going on here if no sample_file has been chosen
        # They shouldn't even be able to view the rest of the form with out it.
        file = request.FILES['sample_file']
        file_name, file_type, data = process_file(file)

        tab = int(request.POST['tab']) if 'tab' in request.POST else 0
        skip = int(request.POST['skip']) if 'skip' in request.POST else 0

        tab, skip, field_choices = get_headers(data, file_type, tab, skip)

        if 'sample_type_id' in kwargs:
            sample_type = models.SampleType.objects.get(pk=kwargs['sample_type_id'])
            sample_type_form = forms.SampleTypeForm(request.POST, instance=sample_type, field_choices=field_choices)
        else:
            sample_type_form = forms.SampleTypeForm(request.POST, field_choices=field_choices)

        if sample_type_form.is_valid():
            sample_type: models.SampleType = sample_type_form.save()
            # the load form is immutable to the user it just allows them the delete, send for edit or load the
            # sample into the mission
            load_form = render_crispy_form(forms.SampleTypeLoadForm(instance=sample_type))
            html = f'<div id="div_id_loaded_samples_list">{load_form}</div>'
            return HttpResponse(html)

        html = render_crispy_form(sample_type_form)
        return HttpResponse(html)


def new_sample_type(request, **kwargs):
    context = {}
    context.update(csrf(request))

    if request.method == "GET":
        # return a loading alert that calls this methods post request
        # Let's make some soup
        url = reverse_lazy("core:new_sample_type")

        soup = BeautifulSoup('', "html.parser")

        root_div = soup.new_tag("div")
        alert_div = get_alert(soup, _("Loading"), 'info')

        root_div.attrs = {
            'id': "div_id_loaded_sample_type_message",
            'hx-trigger': "load",
            'hx-post': url,
            'hx-target': "#div_id_sample_type",
        }

        root_div.append(alert_div)
        soup.append(root_div)

        return HttpResponse(soup)
    elif request.method == "POST":

        if 'sample_file' not in request.FILES:
            soup = BeautifulSoup('<div id="div_id_sample_type"></div>', 'html.parser')

            div = soup.new_tag('div')
            div.attrs['class'] = 'alert alert-warning mt-2'
            div.string = _("File is required before adding sample")
            soup.find(id="div_id_sample_type").append(div)
            return HttpResponse(soup)

        file = request.FILES['sample_file']
        file_name, file_type, data = process_file(file)

        if 'sample_type_id' in kwargs:
            config = models.SampleType.objects.get(pk=kwargs['sample_type_id'])
            tab, skip, field_choices = get_headers(data, config.file_type, config.tab, config.skip)
            sample_type_form = forms.SampleTypeForm(instance=config, field_choices=field_choices)
        else:
            tab = int(request.POST['tab']) if 'tab' in request.POST else 0
            skip = int(request.POST['skip']) if 'skip' in request.POST else -1

            tab, skip, field_choices = get_headers(data, file_type, tab, skip)
            file_initial = {"file_type": file_type, "skip": skip, "tab": tab}
            sample_type_form = forms.SampleTypeForm(initial=file_initial, field_choices=field_choices)

        html = render_crispy_form(sample_type_form)
        return HttpResponse(html)


def load_sample_type(request, **kwargs):
    context = {}
    context.update(csrf(request))

    if request.method == "GET":
        mission_id = request.GET['mission'] if 'mission' in request.GET else None
        loading = 'sample_file' in request.GET

        if loading:
            # Let's make some soup
            url = reverse_lazy("core:load_sample_type")
            oob_select = "#div_id_loaded_samples_list:outerHTML, #div_id_sample_type:outerHTML"

            soup = BeautifulSoup('<div id="div_id_loaded_sample_type"><div id=div_id_loaded_samples_list></div</div>',
                                 "html.parser")

            root_div = soup.new_tag("div")
            alert_div = get_alert(soup, _("Loading"), 'info')

            root_div.attrs = {
                'id': "div_id_loaded_sample_type_message",
                'hx-trigger': "load",
                'hx-post': url,
                'hx-target': "#div_id_loaded_sample_type_message",
                'hx-swap': "outerHTML",
                'hx-select-oob': oob_select,
            }

            root_div.append(alert_div)
            soup.find(id="div_id_loaded_sample_type").append(root_div)

            return HttpResponse(soup)

        if request.htmx:
            # if this is an htmx request it's to grab an updated element from the form, like the BioChem Datatype
            # field after the Datatype_filter has been triggered.
            sample_type_form = forms.SampleTypeForm(file_type="", field_choices=[], initial=request.GET)
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
            html += '<div id=div_id_loaded_samples_list>'
            for config in config_forms:
                form_html = render_crispy_form(config)
                if (errors := models.FileError.objects.filter(file_name=file_name)).exists():
                    soup = BeautifulSoup(form_html, 'html.parser')
                    get_error_list(soup, config.get_card_id(), errors)
                    form_html = str(soup)
                html += form_html
            html += "</div>"

            # if a sample type has already been loaded I want there to be an indication like a different button icon
            soup = BeautifulSoup(html, 'html.parser')
        else:
            html += '<div id=div_id_loaded_samples_list></div>'

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

    if 'sample_type_id' not in kwargs:
        raise Http404("Missing Sample ID")

    sample_type_id = kwargs['sample_type_id']
    load_block = "loaded_sample_list_block"

    if request.method == "GET":

        message_div_id = f'div_id_{sample_type_id}'
        soup = BeautifulSoup(f'', 'html.parser')
        root_div = soup.new_tag("div")

        url = reverse_lazy("core:load_samples", args=(sample_type_id,))
        root_div.attrs = {
            'id': f'div_id_loading_{message_div_id}',
            'hx-trigger': "load",
            'hx-post': url,
            'hx-target': f'#div_id_loading_{message_div_id}',
            'hx-swap': "outerHTML",
            'hx-select-oob': f"#{message_div_id}_load_button, #{message_div_id}_message"
        }

        root_div.append(get_alert(soup, _("Loading"), 'info'))
        soup.append(root_div)

        return HttpResponse(soup)

    elif request.method == "POST":
        mission_id = request.POST['mission_id']
        message_div_id = f'div_id_{sample_type_id}'

        # Todo: Add a unit test to test that the message block gets shown if no file is
        #  present when this function is active
        if 'sample_file' not in request.FILES:
            context['message'] = _("File is required before adding sample")
            html = render_block_to_string("core/partials/form_sample_type.html", load_block,
                                          context=context)
            return HttpResponse(html)

        file = request.FILES['sample_file']
        file_name, file_type, data = process_file(file)

        sample_type = models.SampleType.objects.get(pk=sample_type_id)
        mission = models.Mission.objects.get(pk=mission_id)

        # at the moment this will just prevent a user for accidentally deleting a sample_type that's used
        # across multiple missions. Eventually I'd like this to be a deep copy of the sample_type
        # where it can be edited from one mission to another without affecting settings for other missions
        mission_sample_type = models.MissionSampleType(mission=mission, type=sample_type)
        mission_sample_type.save()

        dataframe = get_excel_dataframe(stream=data, sheet_number=sample_type.tab, header_row=sample_type.skip)

        soup = BeautifulSoup('', 'html.parser')

        button_class = "btn btn-success btn-sm"
        try:
            parse_data_frame(settings=mission_sample_type, file_name=file_name, dataframe=dataframe)

            if (errors := models.FileError.objects.filter(file_name=file_name)).exists():
                button_class = "btn btn-warning btn-sm"
                get_error_list(soup, message_div_id, errors)

        except Exception as ex:
            logger.error(f"Failed to load file {file_name}")
            logger.exception(ex)
            button_class = "btn btn-danger btn-sm"

        # url = reverse_lazy('core:load_samples', args=(file_config.pk,))
        button = soup.new_tag('button')
        button.attrs = {
            'id': f"{message_div_id}_load_button",
            'name': "load",
            'hx-get': reverse_lazy('core:load_samples', args=(sample_type_id,)),
            'hx-target': f"#{message_div_id}_message",
            'class': button_class
        }

        soup.append(button)
        icon = BeautifulSoup(load_svg("folder-check"), 'html.parser').svg
        button.append(icon)
        response = HttpResponse(soup)

        # This will trigger the Sample table on the 'core/mission_samples.html' template to update
        response['HX-Trigger'] = 'update_samples'
        return response


def delete_sample_type(request, **kwargs):
    config_id = kwargs['sample_type_id']
    if request.method == "POST":
        models.SampleType.objects.get(pk=config_id).delete()

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
    if sensor_id:
        queryset = models.Sample.objects.filter(type_id=sensor_id).order_by('bottle__bottle_id')[
                   page_start:(page_start + page_limit)]
        queryset = queryset.values(
            'bottle__bottle_id',
            'bottle__pressure',
            'discrete_values__replicate',
            'discrete_values__value',
            'discrete_values__flag',
            'discrete_values__sample_datatype',
            'discrete_values__comment',
        )
        headings = ['Flag', 'Datatype', 'Comments']
        df = read_frame(queryset)
        df.columns = ["Sample", "Pressure", "Replicate", "Value"] + headings

        df = df.pivot(index=['Sample', 'Pressure', ], columns=['Replicate'])

        soup = format_sensor_table(df, mission_id, sensor_id)
    else:
        bottle_limit = models.Bottle.objects.filter(event__mission=mission).order_by('bottle_id')[
                       page_start:(page_start + page_limit)]
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
            sensors = models.SampleType.objects.filter(samples__bottle__event__mission=mission).distinct()
            df = pd.pivot_table(df, values='Value', index=['Sample', 'Pressure'], columns=['Sensor', 'Replicate'])

            # if the initial sample/sensor doesn't have any values on the first page, then they won't be in the
            # table header. So add in blank columns for them, which pandas/Django is smart enough to fill in later.
            missing = np.setdiff1d([s.pk for s in sensors.order_by('pk').distinct()], [v[0] for v in df.columns.values])
            if len(missing) > 0:
                for m in missing:
                    replicate_count = sensors.get(pk=m).samples.aggregate(replicates=Max('discrete_values__replicate'))
                    for i in range(replicate_count['replicates']):
                        df[m, i] = df.apply(lambda _: np.nan, axis=1)

            df = df.reindex(sorted(df.columns), axis=1)
            soup = format_all_sensor_table(df, mission_id)
        except Exception as ex:
            logger.exception(ex)

    if not queryset.exists():
        soup = BeautifulSoup('<table id="sample_table"></table>', 'html.parser')
        response = HttpResponse(soup)
        return response

    # add styles to the table so it's consistent with the rest of the application
    table = soup.find('table')
    table.attrs['class'] = 'dataframe table table-striped tscroll'

    # now we'll attach an HTMX call to the last queried table row so when the user scrolls to it the next batch
    # of samples will be loaded into the table.
    args = (mission_id, sensor_id,) if sensor_id else (mission_id,)
    last_tr = table.find('tbody').find_all('tr')[-1]
    last_tr.attrs['hx-target'] = 'this'
    last_tr.attrs['hx-trigger'] = 'intersect once'
    last_tr.attrs['hx-get'] = reverse_lazy('core:hx_sample_list', args=args) + f"?page={page + 1}"
    last_tr.attrs['hx-swap'] = "afterend"

    # finally, align all text in each column to the center of the cell
    tds = soup.find('table').find_all('td')
    for td in tds:
        td['class'] = 'text-center'

    if page > 0:
        response = HttpResponse(soup.find('tbody').findAll('tr', recursive=False))
    else:
        response = HttpResponse(soup)

    return response


def format_all_sensor_table(df, mission_id):
    # Pandas has the ability to render dataframes as HTML and it's super fast, but the default table looks awful.
    html = '<div id="sample_table">' + df.to_html() + "</div>"

    # Using BeautifulSoup for html manipulation to post process the HTML table Pandas created
    soup = BeautifulSoup(html, 'html.parser')

    # this will be a big table add scrolling
    sample_table = soup.find(id="sample_table")
    sample_table.attrs['class'] = "vertical-scrollbar"

    # remove the first table row pandas adds for the "Value" column header
    # soup.find("thead").find("tr").decompose()

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

    return soup


def format_sensor_table(df, mission_id, sensor_id):
    # Pandas has the ability to render dataframes as HTML and it's super fast, but the default table looks awful.
    html = '<div id="sample_table">' + df.to_html() + "</div>"

    # Using BeautifulSoup for html manipulation to post process the HTML table Pandas created
    soup = BeautifulSoup(html, 'html.parser')

    # this will be a big table add scrolling
    sample_table = soup.find(id="sample_table")
    sample_table.attrs['class'] = "vertical-scrollbar"

    # delete the row with the 'replicates' labels
    # soup.find("thead").find('tr').findNext('tr').decompose()

    # The next few rows will be the 'Sensor' row with labels like C0SM, T090C, and oxy
    # followed by the 'replicate' row that describes if this is a single, double, triple sample.

    # We're going to flatten the headers down to one row then remove the others.

    sensor_headers = soup.find("thead").find("tr")

    # we now have two header rows. The first contains all the sensor/sample names. The second contains the "Sample"
    # and "Pressure" labels. I want to copy the first two columns from the second header to the first two columns
    # of the first header (because the labels might be translated) then delete the second row
    replicate_header = soup.find('tr').findNext('tr')
    if replicate_header:
        replicate_header.decompose()

    sensor_column = sensor_headers.find('th')
    column = sensor_column.findNext('th')  # 'Value' column

    # if the sensor_id is present then we want to show the specific details for this sensor/sample
    sampletype = models.SampleType.objects.get(pk=sensor_id)
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

    table = soup.find('table')
    th = table.find('tr').find('th')
    th.attrs['class'] = 'text-center'
    # center all of the header text
    while (th := th.findNext('th')):
        th.attrs['class'] = 'text-center'

    root.append(button_row)
    root.append(sensor_row_container)
    root.append(table)

    return soup


def hx_sample_delete(request, **kwargs):
    mission = kwargs['mission_id']
    sample_type = kwargs['sample_type_id']
    if request.method == "POST":
        models.Sample.objects.filter(type=sample_type).delete()

    return hx_list_samples(request, mission_id=mission)


# Used in testing the mission samples type form
class SampleDetails(MissionMixin, GenericDetailView):
    page_title = _("Mission Samples")
    template_name = "core/mission_samples_test.html"

    def get_settings_url(self):
        return reverse_lazy("core:mission_edit", args=(self.object.pk,))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['mission'] = self.object

        return context
