import os
import pandas as pd
import numpy as np

from bs4 import BeautifulSoup
from crispy_forms.bootstrap import StrictButton
from crispy_forms.layout import Field, Div, Row, Column, Hidden, HTML
from crispy_forms.utils import render_crispy_form

from django import forms
from django.db.models import Q, Min, Max
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _
from django_pandas.io import read_frame
from django.conf import settings

import core.models
from bio_tables import models as bio_models
from core import models as core_models
from core import forms as core_forms
from config.utils import load_svg


class MissionSampleTypeFilter(core_forms.CollapsableCardForm):
    sample_id_start = forms.IntegerField(label=_("Start"), required=False)
    sample_id_end = forms.IntegerField(label=_("End"), required=False)

    # Using this to remove large gaps around input fields crispy forms puts in
    field_template = os.path.join(settings.TEMPLATE_DIR, "field.html")

    # I make these static methods so when functions outside of the form want to manipulate elements on the form
    # we can be sure we're using the same IDs
    @staticmethod
    def get_input_mission_sample_type_id():
        return "input_id_mission_sample_type"

    @staticmethod
    def get_input_sample_id_start_id():
        return "input_id_sample_id_start"

    @staticmethod
    def get_input_sample_id_end_id():
        return "input_id_sample_id_end"

    @staticmethod
    def get_button_delete_mission_samples_id():
        return "btn_id_delete_mission_samples"

    def get_input_hidden_mission_sample_type(self):
        attrs = self.htmx_attributes.copy()
        attrs['hx-trigger'] = "reload_samples from:body"
        input =  Hidden(value=self.mission_sample_type.pk, name='mission_sample_type', id=self.get_input_mission_sample_type_id(), **attrs)
        return input

    def get_input_sample_id_start(self):
        attrs = self.htmx_attributes.copy()
        attrs['hx-trigger'] = "keyup changed delay:500ms"
        return Field('sample_id_start', name='sample_id_start', id=self.get_input_sample_id_start_id(),
                     css_class="form-control-sm", template=self.field_template, **attrs)

    def get_input_sample_id_end(self):
        attrs = self.htmx_attributes.copy()
        attrs['hx-trigger'] = "keyup changed delay:500ms"
        return Field('sample_id_end', name='sample_id_end', id=self.get_input_sample_id_end_id(),
                     css_class="form-control-sm", template=self.field_template, **attrs)

    def get_button_delete_mission_samples(self):
        attrs = {
            'title': _("Delete Visible Samples"),
            'hx-confirm': _("Are you sure?"),
            'hx-swap': "none",
            'hx-post': reverse_lazy("core:form_mission_sample_type_delete", args=[self.mission_sample_type.pk])
        }
        button = StrictButton(
            load_svg('dash-square'),
            css_class='btn btn-sm btn-danger',
            id=self.get_button_delete_mission_samples_id(),
            **attrs
        )
        return button

    def get_card_header(self):
        header = super().get_card_header()
        spacer_row = Column(
            css_class="col"
        )

        button_row = Column(
            self.get_button_delete_mission_samples(),
            css_class="col-auto"
        )

        header.fields[0].fields.append(spacer_row)
        header.fields[0].fields.append(button_row)

        return header

    def get_card_body(self) -> Div:
        body = super().get_card_body()

        body.append(self.get_input_hidden_mission_sample_type())

        helptext = _("The start of the sample range. If no ending ID is provided only samples matching this "
                     "ID will be returned.")
        sample_row = Row(
            Row(
                Column(self.get_input_sample_id_start()),
                Column(self.get_input_sample_id_end())
            ),
            Row(
                HTML(f'<small class="form-text">{helptext}</small>')
            ),
            css_class='mb-3'
        )
        body.append(sample_row)

        return body

    def __init__(self, mission_sample_type: core_models.MissionSampleType, *args, **kwargs):
        self.mission_sample_type = mission_sample_type

        url = reverse_lazy('core:mission_sample_type_sample_list', args=[self.mission_sample_type.pk])
        self.htmx_attributes = {
            'hx-target': "#div_id_card_mission_sample_type_samples",
            'hx-post': url,
            'hx-swap': 'outerHTML'
        }
        super().__init__(*args, card_name="missing_sample_type_filter", card_title=_("Sample Type Filter"),
                         collapsed=False, **kwargs)

        samples = mission_sample_type.samples.order_by('bottle__bottle_id')
        self.fields['sample_id_start'].widget.attrs['placeholder'] = samples.first().bottle.bottle_id
        self.fields['sample_id_end'].widget.attrs['placeholder'] = samples.last().bottle.bottle_id



class BioChemDataType(core_forms.CollapsableCardForm):
    sample_type_id = forms.IntegerField(label=_("Sample Type"),
                                        help_text=_("The Sample Type to apply the BioChem datatype to"))
    mission_id = forms.IntegerField(label=_("Mission"),
                                    help_text=_("The mission to apply the BioChem datatype to"))
    data_type_filter = forms.CharField(label=_("Filter Datatype"), required=False)
    data_type_code = forms.IntegerField(label=_("Datatype Code"), required=False)
    data_type_description = forms.ChoiceField(label=_("Datatype Description"), required=False)

    def get_button_apply_to_row(self):
        apply_attrs = {
            'name': 'apply_data_type_row',
            'title': _('Apply Datatype to row(s)'),
            'hx-post': reverse_lazy('core:form_mission_sample_type_set_row', args=(self.mission_sample_type.pk,)),
            'hx-swap': 'none'
        }
        button = StrictButton(
            load_svg('arrow-down-square'),
            css_class="btn btn-sm btn-primary btn-sm ms-2",
            **apply_attrs
        )
        return button

    def get_button_apply_to_mission(self):
        apply_attrs = {
            'name': 'apply_data_type_sensor',
            'title': _('Apply Datatype to mission'),
            'hx-post': reverse_lazy('core:form_mission_sample_type_set_mission', args=(self.mission_sample_type.pk,)),
            'hx-swap': 'none'
        }
        button = StrictButton(
            load_svg('arrow-up-square'),
            css_class="btn btn-sm btn-primary btn-sm ms-2",
            **apply_attrs
        )
        return button

    def get_card_header(self):
        header = super().get_card_header()

        spacer_row = Column(
            css_class="col"
        )

        button_row = Column(
            self.get_button_apply_to_row(),
            self.get_button_apply_to_mission(),
            css_class="col-auto"
        )

        header.fields[0].fields.append(spacer_row)
        header.fields[0].fields.append(button_row)

        return header

    def get_card_body(self) -> Div:
        body = super().get_card_body()

        reload_form_url = reverse_lazy('core:form_mission_sample_type_set_get', args=(self.mission_sample_type.pk,))

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

        body.append(Hidden('sample_type_id', self.mission_sample_type.pk))
        body.append(Row(
            Column(data_type_filter, css_class='col'),
        ))

        body.append(Row(
            Column(data_type_code, css_class='col-auto'),
            Column(data_type_description, css_class="col"),
            id="div_id_data_type_row"
        ))

        return body

    def __init__(self, mission_sample_type: core_models.MissionSampleType, *args, **kwargs):
        self.mission_sample_type = mission_sample_type

        super().__init__(*args, card_name="biochem_data_type_form", card_title=_("Apply Biochem Datatype"), **kwargs)

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


def get_mission_samples_type_samples_queryset(request, mission_sample_type):
    queryset = mission_sample_type.samples.order_by('bottle__bottle_id')
    if request.method == 'POST':
        sample_id_start = int(request.POST.get('sample_id_start', 0) or 0)
        sample_id_end = int(request.POST.get('sample_id_end', 0) or 0)
        if bool(sample_id_start) and not bool(sample_id_end):
            queryset = queryset.filter(bottle__bottle_id=sample_id_start)
        elif bool(sample_id_start) and bool(sample_id_end):
            queryset = queryset.filter(bottle__bottle_id__gte=sample_id_start, bottle__bottle_id__lte=sample_id_end)

    return queryset


def format_sensor_table(df: pd.DataFrame, mission_sample_type: core_models.MissionSampleType) -> BeautifulSoup:
    # Pandas has the ability to render dataframes as HTML and it's super fast, but the default table looks awful.

    # start by replacing nan values with '---'
    df.fillna('---', inplace=True)

    # reformat the Datatype columns, which will be represented as floats, but we want them as integers
    for i in range(1, df['Datatype'].shape[1] + 1):
        df[('Datatype', i,)] = df[('Datatype', i)].astype('string')
        df[('Datatype', i,)] = df[('Datatype', i,)].map(lambda x: x.pk if isinstance(x, bio_models.BCDataType) else int(float(x)) if x != '---' else x)

    # Using BeautifulSoup for html manipulation to post process the HTML table Pandas created
    soup = BeautifulSoup('', 'html.parser')

    # convert the dataframe to an HTML table
    soup.append(BeautifulSoup(df.to_html(), 'html.parser'))

    # delete the row with the 'replicates' labels
    # soup.find("thead").find('tr').findNext('tr').decompose()

    # We're going to flatten the headers down to one row then remove the others.

    table_header = soup.find('thead')
    table_header.attrs['class'] = 'sticky-top bg-white'

    sensor_headers = table_header.find("tr")

    # this is the replicate row, but we aren't doing anything with this row so get rid of it
    if(replicate_headers := sensor_headers.findNext("tr")):
        replicate_headers.decompose()

    # we now have two header rows. The first contains all the sensor/sample names. The second contains the "Sample"
    # and "Pressure" labels. I want to copy the first two columns from the second header to the first two columns
    # of the first header (because the labels might be translated) then delete the second row
    if (index_headers := sensor_headers.findNext('tr')) is None:
        # if the index_header row is empty, it's because there's now data loaded and no point in continuing.
        return

    index_column = index_headers.find('th')
    sensor_column = sensor_headers.find('th')

    # copy the 'Sample ID' label
    sensor_column.attrs['class'] = "sticky-column"
    sensor_column.attrs['style'] = "left: 89px;"
    sensor_column.string = index_column.string

    # copy the 'Pressure' label
    index_column = index_column.findNext('th')
    sensor_column = sensor_column.findNext('th')
    sensor_column.attrs['class'] = "sticky-column"
    sensor_column.attrs['style'] = "left: 89px;"
    sensor_column.string = index_column.string

    # remove the now unneeded index_header row
    index_headers.decompose()

    table = soup.find('table')
    table.attrs['id'] = 'table_id_sample_table'
    table.attrs['class'] = 'table table-striped'
    th = table.find('tr').find('th')
    th.attrs['class'] = 'text-center'

    # center all of the header text
    while th := th.findNext('th'):
        th.attrs['class'] = 'text-center'
        if th.string == 'Comments':
            th.attrs['class'] += ' w-100'

    return soup


def list_samples(request, mission_sample_type_id):
    mission_sample_type = core_models.MissionSampleType.objects.get(pk=mission_sample_type_id)
    sample_card_context = {
        'card_name': 'mission_sample_type_samples',
        'card_title': f'{mission_sample_type.long_name} - {mission_sample_type.datatype}'
    }

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

    queryset = get_mission_samples_type_samples_queryset(request, mission_sample_type)

    if not queryset.exists():
        # if there are no more bottles then we stop loading, otherwise weird things happen
        card_soup = get_samples_card(mission_sample_type, sample_card_context, show_scrollbar=False)

        card_body = card_soup.find(id=f"div_id_card_collapse_{sample_card_context['card_name']}")
        card_body.append(info:=card_soup.new_tag('div', attrs={'class': 'alert alert-info'}))
        info.string = _("No Samples found")
        response = HttpResponse(card_soup)
        return response

    pages = queryset.count()/page_limit if queryset.exists() else 0
    queryset = queryset[page_start:(page_start + page_limit)]

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
        'datatype__pk',
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
    table.attrs['class'] = 'table table-striped table-sm horizontal-scrollbar'

    # now we'll attach an HTMX call to the last queried table row so when the user scrolls to it the next batch
    # of samples will be loaded into the table.
    table_head = table.find('thead')
    table_head.attrs['class'] = 'sticky-top'

    table_body = table.find('tbody')

    if pages > 1 and queryset.count() >= page_limit:
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

    # If the page is <= zero then we're constructing the table for the first time and we'll want to encapsulate
    # the whole table in a card with the mission sample type details as the cart title.
    #
    # if page is > 0 then the user is scrolling down and we only want to return new rows to be swapped into
    # the table.
    if page > 0:
        response = HttpResponse(soup.find('tbody').findAll('tr', recursive=False))
        return response

    card_soup = get_samples_card(mission_sample_type, sample_card_context, show_scrollbar=(pages>1 or queryset.count()>11))

    card_body = card_soup.find(id=f"div_id_card_collapse_{sample_card_context['card_name']}")
    card_body.append(soup.find('table'))
    response = HttpResponse(card_soup)

    return response

def get_samples_card(mission_sample_type, context, show_scrollbar=True):

    card_html = render_to_string('core/partials/card_placeholder.html', context)
    card_soup = BeautifulSoup(card_html, 'html.parser')

    card_body = card_soup.find(id=f"div_id_card_collapse_{context['card_name']}")
    card_body.attrs['class'] = ''  # We're clearing the class to get rid of the card-body class' margins
    if show_scrollbar:
        card_body.attrs['class'] = 'vertical-scrollbar'

    return card_soup

def update_sample_type_row(request, mission_sample_type_id):

    sample_type = core_models.MissionSampleType.objects.get(pk=mission_sample_type_id)

    data_type_code = request.POST['data_type_code']

    data_type = None
    if data_type_code:
        data_type = bio_models.BCDataType.objects.get(data_type_seq=data_type_code)

    queryset = get_mission_samples_type_samples_queryset(request, sample_type)
    discrete_update = core_models.DiscreteSampleValue.objects.filter(sample__in=queryset)

    for value in discrete_update:
        value.datatype = data_type

    core_models.DiscreteSampleValue.objects.bulk_update(discrete_update, ['datatype'])

    response = list_samples(request, sample_type.pk)
    response['HX-Trigger'] = 'reload_samples'
    return response


def update_sample_type_mission(request, mission_sample_type_id):
    sample_type = core_models.MissionSampleType.objects.get(pk=mission_sample_type_id)

    data_type_code = request.POST['data_type_code']

    data_type = None
    if data_type_code:
        data_type = bio_models.BCDataType.objects.get(data_type_seq=data_type_code)

    sample_type.datatype = data_type
    sample_type.save()

    response = list_samples(request, sample_type.pk)
    response['HX-Trigger'] = 'reload_samples'
    return response


def update_sample_type(request, mission_sample_type_id):
    mission_sample_type = core_models.MissionSampleType.objects.get(pk=mission_sample_type_id)
    if request.method == "GET":
        # if the GET request is empty populate the form with the default values
        if len(request.GET) <= 0:
            biochem_form = BioChemDataType(mission_sample_type=mission_sample_type)
            html = render_crispy_form(biochem_form)
            return HttpResponse(html)

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

    queryset = get_mission_samples_type_samples_queryset(request, mission_sample_type)
    discrete_update = core_models.DiscreteSampleValue.objects.filter(sample__in=queryset)
    discrete_update.delete()

    mission_sample_type.samples.filter(discrete_values__isnull=True).delete()

    response = HttpResponse()
    if mission_sample_type.samples.exists():
        response['HX-Trigger'] = 'reload_samples'
    else:
        # if we delete all the samples we'll want to send the user back to the Mission Samples page
        database = settings.DATABASES[mission_sample_type.mission._state.db]['LOADED'] if (
                'LOADED' in settings.DATABASES[mission_sample_type.mission._state.db]) else 'default'
        mission_sample_url = reverse_lazy('core:mission_samples_sample_details',
                                          args=(database, mission_sample_type.mission.pk,))
        mission_sample_type.samples.all().delete()
        mission_sample_type.delete()
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
