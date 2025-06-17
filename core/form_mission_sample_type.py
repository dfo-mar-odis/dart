import pandas as pd
import numpy as np

from bs4 import BeautifulSoup
from crispy_forms.bootstrap import StrictButton
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Field, Layout, Div, Row, Column, Hidden
from crispy_forms.utils import render_crispy_form

from django import forms
from django.db.models import Q, Min, Max
from django.http import HttpResponse
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _
from django_pandas.io import read_frame
from django.conf import settings

from bio_tables import models as bio_models
from core import models as core_models
from core import forms as core_forms
from config.utils import load_svg


class BioChemDataType(forms.Form):
    sample_type_id = forms.IntegerField(label=_("Sample Type"),
                                        help_text=_("The Sample Type to apply the BioChem datatype to"))
    mission_id = forms.IntegerField(label=_("Mission"),
                                    help_text=_("The mission to apply the BioChem datatype to"))
    data_type_filter = forms.CharField(label=_("Filter Datatype"), required=False)
    data_type_code = forms.IntegerField(label=_("Datatype Code"), required=False)
    data_type_description = forms.ChoiceField(label=_("Datatype Description"), required=False)

    start_sample = forms.IntegerField(label=_("Start"))
    end_sample = forms.IntegerField(label=_("End"))

    def __init__(self, mission_sample_type: core_models.MissionSampleType, *args, **kwargs):
        super().__init__(*args, **kwargs)

        mission = mission_sample_type.mission
        min_max = core_models.Bottle.objects.filter(event__mission=mission).aggregate(
            Min('bottle_id'), Max('bottle_id'))

        self.fields['start_sample'].initial = min_max['bottle_id__min']
        self.fields['end_sample'].initial = min_max['bottle_id__max']

        data_type_choices_qs = bio_models.BCDataType.objects.all()
        data_type_choices = [(st.pk, st) for st in data_type_choices_qs]
        data_type_choices.insert(0, (None, '---------'))
        self.fields['data_type_description'].choices = data_type_choices
        self.fields['data_type_description'].initial = None

        if mission_sample_type.datatype:
            self.fields['data_type_code'].initial = mission_sample_type.datatype.pk
            self.fields['data_type_description'].initial = mission_sample_type.datatype.pk

        if 'initial' in kwargs:
            if 'data_type_filter' in kwargs['initial']:
                data_type_filter = kwargs['initial']['data_type_filter'].split(" ")
                q_set = Q()
                for f in data_type_filter:
                    q_set = Q(description__icontains=f) & q_set
                data_type_choices_qs = data_type_choices_qs.filter(q_set)

                if data_type_choices_qs.exists():
                    data_type_choices = [(st.pk, st) for st in data_type_choices_qs]
                    data_type_choices.insert(0, (None, '---------'))

                    initial_choice = data_type_choices[0][0]
                    if len(data_type_choices) > 1:
                        initial_choice = data_type_choices[1][0]
                    self.fields['data_type_description'].choices = data_type_choices
                    self.fields['data_type_description'].initial = initial_choice
                    self.fields['data_type_code'].initial = initial_choice
                else:
                    self.fields['data_type_description'].choices = [(None, '---------')]
                    self.fields['data_type_description'].initial = None
                    self.fields['data_type_code'].initial = None
            elif 'data_type_code' in kwargs['initial']:
                self.fields['data_type_code'].initial = kwargs['initial']['data_type_code']
                self.fields['data_type_description'].initial = kwargs['initial']['data_type_code']

            if 'start_sample' in kwargs['initial']:
                self.fields['start_sample'].initial = kwargs['initial']['start_sample']

            if 'end_sample' in kwargs['initial']:
                self.fields['end_sample'].initial = kwargs['initial']['end_sample']

        self.helper = FormHelper(self)

        reload_form_url = reverse_lazy('core:form_mission_sample_type_set_get', args=(mission_sample_type.pk,))

        data_type_filter = Field('data_type_filter', css_class="form-control form-control-sm")
        data_type_filter.attrs['hx-get'] = reload_form_url
        data_type_filter.attrs['hx-trigger'] = 'keyup changed delay:500ms'
        data_type_filter.attrs['hx-target'] = "#div_id_data_type_row"
        data_type_filter.attrs['hx-select'] = "#div_id_data_type_row"

        data_type_code = Field('data_type_code', id='id_data_type_code', css_class="form-control-sm")
        data_type_code.attrs['hx-get'] = reload_form_url
        data_type_code.attrs['hx-trigger'] = 'keyup changed delay:500ms'
        data_type_code.attrs['hx-target'] = "#id_data_type_description"
        data_type_code.attrs['hx-select-oob'] = "#id_data_type_description"

        data_type_description = Field('data_type_description', id='id_data_type_description',
                                      css_class='form-control form-select-sm')
        data_type_description.attrs['hx-get'] = reload_form_url
        data_type_description.attrs['hx-trigger'] = 'change'
        data_type_description.attrs['hx-target'] = "#id_data_type_code"
        data_type_description.attrs['hx-select-oob'] = "#id_data_type_code"

        apply_attrs = {
            'name': 'apply_data_type_row',
            'title': _('Apply Datatype to row(s)'),
            'hx-get': reload_form_url,
            'hx-target': "#div_id_data_type_message",
            'hx-swap': 'innerHTML'
        }
        row_apply_button = StrictButton(load_svg('arrow-down-square'), css_class="btn btn-primary btn-sm ms-2",
                                        **apply_attrs)

        apply_attrs = {
            'name': 'apply_data_type_sensor',
            'title': _('Apply Datatype to mission'),
            'hx-get': reload_form_url,
            'hx-target': "#div_id_data_type_message",
            'hx-swap': 'innerHTML'
        }
        sensor_apply_button = StrictButton(load_svg('arrow-up-square'), css_class="btn btn-primary btn-sm ms-2",
                                           **apply_attrs)

        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                Hidden('sample_type_id', mission_sample_type.pk),
                Row(
                    Column(data_type_filter, css_class='col'),
                ),
                Row(
                    Column(data_type_code, css_class='col-auto'),
                    Column(data_type_description, css_class="col"),
                    id="div_id_data_type_row"
                ),
                Row(
                    Column(Field('start_sample', css_class="form-control-sm"), css_class='col-auto'),
                    Column(Field('end_sample', css_class="form-control-sm"), css_class="col-auto"),
                    Column(row_apply_button, css_class="col-auto align-self-end mb-3"),
                    Column(sensor_apply_button, css_class="col-auto align-self-end mb-3"),
                    id="div_id_sample_range"
                ),
                Row(
                    Column(id="div_id_data_type_message")
                ), css_class="alert alert-secondary mt-2", id="div_id_data_type_form"
            )
        )


def format_sensor_table(df: pd.DataFrame, mission_sample_type: core_models.MissionSampleType) -> BeautifulSoup:
    # Pandas has the ability to render dataframes as HTML and it's super fast, but the default table looks awful.

    # start by replacing nan values with '---'
    df.fillna('---', inplace=True)

    # reformat the Datatype columns, which will be represented as floats, but we want them as integers
    for i in range(1, df['Datatype'].shape[1] + 1):
        df[('Datatype', i,)] = df[('Datatype', i)].astype('string')
        df[('Datatype', i,)] = df[('Datatype', i,)].map(lambda x: int(float(x)) if x != '---' else x)

    # Using BeautifulSoup for html manipulation to post process the HTML table Pandas created
    soup = BeautifulSoup('', 'html.parser')
    soup.append(sample_table := soup.new_tag('div', attrs={'id': "div_id_sample_type_details",
                                                           'class': "vertical-scrollbar"}))

    # convert the dataframe to an HTML table
    sample_table.append(BeautifulSoup(df.to_html(), 'html.parser'))

    # add a message area that will hold saving, loading, error alerts
    msg_div = soup.new_tag("div")
    msg_div.attrs['id'] = "div_id_sample_table_msg"
    sample_table.insert(0, msg_div)

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
    column.string = f'{mission_sample_type.name}'

    root = soup.findChildren()[0]

    table = soup.find('table')
    table.attrs['id'] = 'table_id_sample_table'
    th = table.find('tr').find('th')
    th.attrs['class'] = 'text-center'

    # center all of the header text
    while th := th.findNext('th'):
        th.attrs['class'] = 'text-center'
        if th.string == 'Comments':
            th.attrs['class'] += ' w-100'

    root.append(table)

    return soup


def list_samples(request, mission_sample_type_id):
    mission_sample_type = core_models.MissionSampleType.objects.get(pk=mission_sample_type_id)

    page = int(request.GET.get('page', 0) or 0)
    page_limit = 50
    page_start = page_limit * page

    # unfortunately if a page doesn't contain columns for 1 or 2 replicates when there's more the
    # HTML table that gets returned to the interface will be missing columns and it throws everything
    # out of alignment. We'll get the replicate columns here and use that value to insert blank
    # columns into the dataframe if a replicate column is missing from the query set.
    replicates = core_models.DiscreteSampleValue.objects.filter(
        sample__type=mission_sample_type).order_by('sample__bottle__bottle_id')

    replicate_max = replicates.aggregate(Max('replicate'))['replicate__max']
    queryset = mission_sample_type.samples.order_by('bottle__bottle_id')[page_start:(page_start + page_limit)]

    if not queryset.exists():
        # if there are no more bottles then we stop loading, otherwise weird things happen
        return HttpResponse()

    discrete_queryset = core_models.DiscreteSampleValue.objects.filter(
        sample__in=queryset
    ).order_by('sample__bottle__bottle_id')
    queryset_vals = discrete_queryset.values(
        'sample__bottle__bottle_id',
        'sample__bottle__pressure',
        'replicate',
        'value',
        'limit',
        'flag',
        'datatype',
        'comment',
    )

    headings = ['Value', 'Limit', 'Flag', 'Datatype', 'Comments']
    df = read_frame(queryset_vals)
    df.columns = ["Sample", "Pressure", "Replicate", ] + headings
    df = df.pivot(index=['Sample', 'Pressure', ], columns=['Replicate'])

    for j, column in enumerate(headings):
        for i in range(1, replicate_max + 1):
            col_index = (column, i,)
            if col_index not in df.columns:
                index = j * replicate_max + i - 1
                if index < df.shape[1]:
                    df.insert(index, col_index, np.nan)
                else:
                    df[col_index] = np.nan

    soup = format_sensor_table(df, mission_sample_type)

    # add styles to the table so it's consistent with the rest of the application
    table = soup.find('table')
    table.attrs['class'] = 'dataframe table table-striped table-sm tscroll horizontal-scrollbar'

    # now we'll attach an HTMX call to the last queried table row so when the user scrolls to it the next batch
    # of samples will be loaded into the table.
    table_head = table.find('thead')

    table_body = table.find('tbody')

    last_tr = table_body.find_all('tr')[-1]
    last_tr.attrs['hx-target'] = 'this'
    last_tr.attrs['hx-trigger'] = 'intersect once'
    last_tr.attrs['hx-get'] = reverse_lazy('core:mission_sample_type_sample_list',
                                           args=(mission_sample_type_id,)) + f"?page={page + 1}"
    last_tr.attrs['hx-swap'] = "afterend"

    # finally, align all text in each column to the center of the cell
    tds = soup.find('table').find_all('td')
    for td in tds:
        td['class'] = 'text-center text-nowrap'

    if page > 0:
        response = HttpResponse(soup.find('tbody').findAll('tr', recursive=False))
    else:
        response = HttpResponse(soup)

    return response


def update_sample_type_row(request, mission_sample_type_id):

    if request.method == "GET":
        url = request.path
        attrs = {
            'component_id': "div_id_data_type_message_alert",
            'message': _("Saving"),
            'hx-post': url,
            'hx-trigger': 'load'
        }
        alert = core_forms.save_load_component(**attrs)

        soup = BeautifulSoup("", "html.parser")
        soup.append(msg_div := soup.new_tag('div', attrs={'id': "div_id_data_type_message", 'hx-swap-oob': "true"}))

        msg_div.append(alert)
        return HttpResponse(soup)

    sample_type = core_models.MissionSampleType.objects.get(pk=mission_sample_type_id)

    data_type_code = request.POST['data_type_code']
    start_sample = request.POST['start_sample']
    end_sample = request.POST['end_sample']

    data_type = None
    if data_type_code:
        data_type = bio_models.BCDataType.objects.get(data_type_seq=data_type_code)

    discrete_update = core_models.DiscreteSampleValue.objects.filter(
        sample__bottle__bottle_id__gte=start_sample,
        sample__bottle__bottle_id__lte=end_sample,
        sample__type=sample_type,
    )
    for value in discrete_update:
        value.datatype = data_type
    core_models.DiscreteSampleValue.objects.bulk_update(discrete_update, ['datatype'])

    response = list_samples(request, sample_type.pk)
    return response


def update_sample_type_mission(request, mission_sample_type_id):
    if request.method == "GET":
        url = request.path
        attrs = {
            'component_id': "div_id_data_type_message_alert",
            'message': _("Saving"),
            'hx-post': url,
            'hx-trigger': 'load'
        }
        alert = core_forms.save_load_component(**attrs)

        soup = BeautifulSoup("", "html.parser")
        soup.append(msg_div := soup.new_tag('div', attrs={'id': "div_id_data_type_message", 'hx-swap-oob': "true"}))

        msg_div.append(alert)
        return HttpResponse(soup)

    sample_type = core_models.MissionSampleType.objects.get(pk=mission_sample_type_id)

    data_type_code = request.POST['data_type_code']

    data_type = None
    if data_type_code:
        data_type = bio_models.BCDataType.objects.get(data_type_seq=data_type_code)

    sample_type.datatype = data_type
    sample_type.save()

    response = list_samples(request, sample_type.pk)
    return response


def update_sample_type(request, mission_sample_type_id):
    mission_sample_type = core_models.MissionSampleType.objects.get(pk=mission_sample_type_id)
    if request.method == "GET":
        # if the GET request is empty populate the form with the default values
        if len(request.GET) <= 0:
            biochem_form = BioChemDataType(mission_sample_type=mission_sample_type)
            html = render_crispy_form(biochem_form)
            return HttpResponse(html)

        attrs = {
            'component_id': 'div_id_data_type_update_save',
            'message': _("Saving"),
            'hx-trigger': 'load',
            'hx-target': '#div_id_data_type_message',
            'hx-select': '#div_id_data_type_message',
            'hx-select-oob': '#table_id_sample_table'
        }
        if 'apply_data_type_row' in request.GET:
            attrs['hx-post'] = reverse_lazy('core:form_mission_sample_type_set_row', args=(mission_sample_type.pk,))
            soup = core_forms.save_load_component(**attrs)
            return HttpResponse(soup)
        elif 'apply_data_type_sensor' in request.GET:
            attrs['hx-post'] = reverse_lazy('core:form_mission_sample_type_set_mission', args=(mission_sample_type.pk,))
            soup = core_forms.save_load_component(**attrs)
            return HttpResponse(soup)

        if 'data_type_filter' in request.GET:
            initial = {'data_type_filter': request.GET['data_type_filter']}
            biochem_form = BioChemDataType(mission_sample_type=mission_sample_type, initial=initial)
            html = render_crispy_form(biochem_form)
            return HttpResponse(html)

        data_type_code = None
        if 'data_type_description' in request.GET:
            data_type_code = request.GET['data_type_description']
        elif 'data_type_code' in request.GET:
            data_type_code = request.GET['data_type_code']

        initial = {
            'data_type_code': data_type_code,
            'data_type_description': data_type_code,
        }
        biochem_form = BioChemDataType(mission_sample_type=mission_sample_type, initial=initial)
        html = render_crispy_form(biochem_form)
        return HttpResponse(html)


def sample_delete(request, mission_sample_type_id):
    mission_sample_type = core_models.MissionSampleType.objects.get(pk=mission_sample_type_id)

    if request.method == "GET":
        url = request.path
        attrs = {
            'component_id': "div_id_data_type_message_alert",
            'message': _("Saving"),
            'hx-post': url,
            'hx-trigger': 'load'
        }
        alert = core_forms.save_load_component(**attrs)

        soup = BeautifulSoup("", "html.parser")
        soup.append(msg_div := soup.new_tag('div', attrs={'id': "div_id_data_type_message", 'hx-swap-oob': "true"}))

        msg_div.append(alert)
        return HttpResponse(soup)

    database = settings.DATABASES[mission_sample_type.mission._state.db]['LOADED'] if (
            'LOADED' in settings.DATABASES[mission_sample_type.mission._state.db]) else 'default'
    mission_sample_url = reverse_lazy('core:mission_samples_sample_details',
                                      args=(database, mission_sample_type.mission.pk,))
    mission_sample_type.samples.all().delete()
    mission_sample_type.delete()

    response = HttpResponse()
    response['Hx-Redirect'] = mission_sample_url
    return response


url_prefix = "sample_type"
sample_type_urls = [
    path(f'{url_prefix}/<int:mission_sample_type_id>/', update_sample_type,
         name="form_mission_sample_type_set_get"),  # mission_samples_update_sample_type
    path(f'{url_prefix}/row/<int:mission_sample_type_id>/', update_sample_type_row,
         name="form_mission_sample_type_set_row"),  # mission_samples_update_sample_type_row
    path(f'{url_prefix}/mission/<int:mission_sample_type_id>/', update_sample_type_mission,
         name="form_mission_sample_type_set_mission"),  # mission_samples_update_sample_type_mission
    path(f'{url_prefix}/delete/<int:mission_sample_type_id>/', sample_delete,
         name="form_mission_sample_type_delete"),  # mission_sample_type_delete

    path(f'{url_prefix}/list/<int:mission_sample_type_id>/', list_samples, name="mission_sample_type_sample_list"),

]
