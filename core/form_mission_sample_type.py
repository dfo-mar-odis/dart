import pandas as pd
import numpy as np

from bs4 import BeautifulSoup
from crispy_forms.bootstrap import StrictButton
from crispy_forms.layout import Field, Div, Row, Column, Hidden, HTML
from crispy_forms.utils import render_crispy_form

from django import forms
from django.db.models import Q, Max, QuerySet
from django.http import HttpResponse
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _
from django_pandas.io import read_frame
from django.conf import settings

from bio_tables import models as bio_models
from core import models as core_models
from core import forms as core_forms
from config.utils import load_svg
from core import form_mission_sample_filter
from core.form_mission_sample_filter import SampleFilterForm, get_samples_card, SAMPLES_CARD_NAME, SAMPLES_CARD_ID


class MissionSampleTypeFilter(SampleFilterForm):

    def get_samples_card_update_url(self):
        return reverse_lazy('core:mission_sample_type_sample_list', args=[self.mission_sample_type.pk])

    def get_clear_filters_url(self):
        return reverse_lazy("core:form_mission_sample_type_clear", args=[self.mission_sample_type.pk])

    def __init__(self, mission_sample_type: core_models.MissionSampleType, collapsed=True, *args, **kwargs):
        self.card_name = "mission_sample_type_filter"
        self.mission_sample_type = mission_sample_type
        self.events = core_models.Event.objects.filter(instrument__type=core_models.InstrumentType.ctd, sample_id__isnull=False, sample_id__gt=0)

        super().__init__(*args, card_name=self.card_name, collapsed=collapsed, **kwargs)

        samples = mission_sample_type.samples.order_by('bottle__bottle_id')
        if samples.exists():
            self.fields['sample_id_start'].widget.attrs['placeholder'] = samples.first().bottle.bottle_id
            self.fields['sample_id_end'].widget.attrs['placeholder'] = samples.last().bottle.bottle_id


class BioChemDataType(core_forms.CollapsableCardForm):

    class BioChemDataTypeIdBuilder(core_forms.CollapsableCardForm.CollapsableCardIDBuilder):

        @staticmethod
        def get_data_type_code_id():
            return 'id_data_type_code'

        @staticmethod
        def get_data_type_description_id():
            return 'id_data_type_description'

        @staticmethod
        def get_data_type_filter_id():
            return 'id_data_type_filter'

        @staticmethod
        def get_range_row_id():
            return 'div_id_range_row'

    @staticmethod
    def get_id_builder_class():
        return BioChemDataType.BioChemDataTypeIdBuilder

    help_text = _("This form allows for the search and selection of a Biochem Datatype.\n\n"
                  "If the Datatype Code field is empty when applied, it will be cleared from all visible samples\n\n"
                  "If no filter is applied, the selected datatype will become the default for all samples "
                  "belonging to this mission sample type.\n"
                  "Otherwise, the datatype will be only be applied the visible samples selected in the Sample Type "
                  "Filter form.\n\n"
                  )
    sample_type_id = forms.IntegerField(label=_("Sample Type"),
                                        help_text=_("The Sample Type to apply the BioChem datatype to"))
    mission_id = forms.IntegerField(label=_("Mission"),
                                    help_text=_("The mission to apply the BioChem datatype to"))
    data_type_filter = forms.CharField(label=_("Filter Datatype"), required=False)
    data_type_code = forms.IntegerField(label=_("Datatype Code"), required=False)
    data_type_description = forms.ChoiceField(label=_("Datatype Description"), required=False)

    def get_button_apply_datatype(self):
        apply_attrs = {
            'title': _('Apply Datatype'),
            'hx-post': reverse_lazy('core:form_mission_sample_type_set', args=(self.mission_sample_type.pk,)),
            'hx-swap': 'none'
        }
        button = StrictButton(
            load_svg('check-square'),
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
            self.get_button_apply_datatype(),
            css_class="col-auto"
        )

        header.fields[0].fields.append(spacer_row)
        header.fields[0].fields.append(button_row)

        return header

    def get_card_body(self) -> Div:
        body = super().get_card_body()

        data_type_code_id = self.get_id_builder().get_data_type_code_id()
        data_type_description_id = self.get_id_builder().get_data_type_description_id()
        data_type_filter_id = self.get_id_builder().get_data_type_filter_id()
        range_row_id = self.get_id_builder().get_range_row_id()

        reload_form_url = reverse_lazy('core:form_mission_filter_datatype', args=(self.mission_sample_type.pk,))

        data_type_filter = Field('data_type_filter', id=data_type_filter_id, css_class="form-control form-control-sm")
        data_type_filter.attrs['hx-get'] = reload_form_url
        data_type_filter.attrs['hx-trigger'] = 'keyup changed delay:500ms'
        data_type_filter.attrs['hx-swap'] = 'none'
        data_type_filter.attrs['hx-select'] = "#" + self.get_collapsable_card_body_id()
        data_type_filter.attrs['hx-select-oob'] = f"#{data_type_code_id}, #{data_type_description_id}, #{range_row_id}"

        data_type_code = Field('data_type_code', id=data_type_code_id, css_class="form-control-sm")
        data_type_code.attrs['hx-get'] = reload_form_url
        data_type_code.attrs['hx-trigger'] = 'keyup changed delay:500ms'
        data_type_code.attrs['hx-swap'] = 'none'
        data_type_code.attrs['hx-select'] = "#" + self.get_collapsable_card_body_id()
        data_type_code.attrs['hx-select-oob'] = f"#{data_type_filter_id}, #{data_type_description_id}, #{range_row_id}"

        data_type_description = Field('data_type_description', id=data_type_description_id,
                                      css_class='form-control form-select-sm')
        data_type_description.attrs['hx-get'] = reload_form_url
        data_type_description.attrs['hx-swap'] = 'none'
        data_type_description.attrs['hx-select'] = "#" + self.get_collapsable_card_body_id()
        data_type_description.attrs['hx-select-oob'] = f"#{data_type_code_id}, #{range_row_id}"

        body.append(Hidden('sample_type_id', self.mission_sample_type.pk))
        body.append(Row(
            Column(data_type_filter, css_class='col'),
        ))

        body.append(Row(
            Column(data_type_code, css_class='col-auto'),
            Column(data_type_description, css_class="col"),
            id="div_id_data_type_row"
        ))

        retrival = bio_models.BCDataType.objects.get(pk=(self.initial_choice if self.initial_choice else self.mission_sample_type.datatype.pk)).data_retrieval
        body.append(Row(
            Column(HTML(str(retrival)), css_class='col-auto'),
            id=range_row_id
        ))

        return body

    def __init__(self, mission_sample_type: core_models.MissionSampleType, render_description_list=True, *args, **kwargs):
        self.mission_sample_type = mission_sample_type

        self.initial_choice = None
        data_type_choices_qs = bio_models.BCDataType.objects.all()
        filtered = False
        if 'initial' in kwargs:
            if 'data_type_filter' in kwargs['initial']:
                filtered = True
                data_type_filter = kwargs['initial']['data_type_filter'].split(" ")
                q_set = Q()
                for f in data_type_filter:
                    q_set = Q(description__icontains=f) & q_set
                data_type_choices_qs = data_type_choices_qs.filter(q_set)
            elif 'data_type_code' in kwargs['initial']:
                self.initial_choice = kwargs['initial']['data_type_code']

        super().__init__(*args, card_name="biochem_data_type_form", card_title=_("Apply Biochem Datatype"),
                         collapsed=False, **kwargs)

        data_type_choices = [(None, '---------')]

        if mission_sample_type.datatype:
            self.initial_choice = mission_sample_type.datatype.pk

        if data_type_choices_qs.exists():
            data_type_choices += [(st.pk, st) for st in data_type_choices_qs]

            # Select the None element if there's no better choices. If there are other choices
            # select the first available choice
            self.initial_choice = self.initial_choice if not filtered else data_type_choices[1][0] if len(data_type_choices) > 1 else None

        if render_description_list:
            # Rendering the description list is really slow when it's large. A lot of the time we've already loaded
            # the options and the user is selecting an option from the list. In the response only the data_type_code
            # and the retrievals description will need to be updated so not reloading the list really speeds up
            # this form
            self.fields['data_type_description'].choices = data_type_choices
            self.fields['data_type_description'].initial = self.initial_choice
        self.fields['data_type_code'].initial = self.initial_choice


def format_sensor_table(df: pd.DataFrame) -> BeautifulSoup:
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
        return soup

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


def get_samples_queryset(filter_dict: dict, initial_samples_queryset: QuerySet):
    queryset = initial_samples_queryset.order_by('bottle__bottle_id')

    event_id = int(filter_dict.get('event', 0) or 0)
    if event_id > 0:
        event = core_models.Event.objects.get(pk=event_id)
        sample_id_start = event.sample_id
        sample_id_end = event.end_sample_id
    else:
        sample_id_start = int(filter_dict.get('sample_id_start', 0) or 0)
        sample_id_end = int(filter_dict.get('sample_id_end', 0) or 0)

    if bool(sample_id_start) and not bool(sample_id_end):
        queryset = queryset.filter(bottle__bottle_id=sample_id_start)
    elif bool(sample_id_start) and bool(sample_id_end):
        queryset = queryset.filter(bottle__bottle_id__gte=sample_id_start, bottle__bottle_id__lte=sample_id_end)

    return queryset

# provided an initial queryset, build a table using BeautifulSoup
def process_samples_func(queryset, **kwargs) -> BeautifulSoup:
    mission_sample_type = kwargs['mission_sample_type']

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

    # unfortunately if a page doesn't contain columns for all possible replicates when there's more than 1 or 2
    # the HTML table that gets returned to the interface will be missing columns and it throws everything
    # out of alignment. We'll get the replicate columns here and use that value to insert blank
    # columns into the dataframe if a replicate column is missing from the query set.
    replicates = core_models.DiscreteSampleValue.objects.filter(
        sample__type=mission_sample_type).order_by('sample__bottle__bottle_id')

    replicate_max = replicates.aggregate(Max('replicate'))['replicate__max']

    for j, column in enumerate(headings):
        for i in range(1, replicate_max + 1):
            col_index = (column, i,)
            if col_index not in df.columns:
                index = j * replicate_max + i - 1
                if index < df.shape[1]:
                    df.insert(index, col_index, np.nan)
                else:
                    df[col_index] = np.nan

    return format_sensor_table(df)


def list_samples(request, mission_sample_type_id):
    mission_sample_type = core_models.MissionSampleType.objects.get(pk=mission_sample_type_id)
    delete_samples_url = reverse_lazy("core:form_mission_sample_type_delete", args=[mission_sample_type_id])

    card_title = mission_sample_type.name
    if mission_sample_type.datatype:
        card_title = (f'{mission_sample_type.name} - {mission_sample_type.datatype} '
                      f'[{mission_sample_type.datatype.data_retrieval.minimum_value} : '
                      f'{mission_sample_type.datatype.data_retrieval.maximum_value}]')

    queryset = get_samples_queryset(request.POST, mission_sample_type.samples.all())

    soup = form_mission_sample_filter.list_samples(request, queryset, card_title, delete_samples_url,
                                                   process_samples_func, mission_sample_type=mission_sample_type)

    return HttpResponse(soup)


def update_sample_type(request, mission_sample_type_id):

    filters = ['event', 'sample_id_start', 'sample_id_end']
    sample_type = core_models.MissionSampleType.objects.get(pk=mission_sample_type_id)

    data_type_code = request.POST['data_type_code']

    data_type = None
    if data_type_code:
        data_type = bio_models.BCDataType.objects.get(data_type_seq=data_type_code)

    filtered = any(request.POST.get(filter_name) for filter_name in filters)
    if not filtered:
        sample_type.datatype = data_type
        sample_type.save()
    else:
        queryset = get_samples_queryset(request.POST, sample_type.samples.all())
        discrete_update = core_models.DiscreteSampleValue.objects.filter(sample__in=queryset)

        for value in discrete_update:
            value.datatype = data_type

        core_models.DiscreteSampleValue.objects.bulk_update(discrete_update, ['datatype'])

    response = list_samples(request, sample_type.pk)
    response['HX-Trigger'] = 'reload_samples'
    return response


def filter_datatype(request, mission_sample_type_id):
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
        render_description_list = True
        if 'data_type_description' in request.GET:
            # Rendering the description list is really slow. In cases where the user is selecting an option from the
            # list, the list won't need to be updated and in the response only the data type code and retrievals
            # description will be updated so we don't need to reload the list.
            render_description_list = False
            data_type_code = request.GET['data_type_description']
        elif 'data_type_code' in request.GET:
            data_type_code = request.GET['data_type_code']

        initial = {
            'data_type_code': data_type_code,
            'data_type_description': data_type_code,
        }
        biochem_form = BioChemDataType(mission_sample_type=mission_sample_type, render_description_list=render_description_list, initial=initial)
        html = render_crispy_form(biochem_form)
        return HttpResponse(html)


def sample_delete(request, mission_sample_type_id):
    mission_sample_type = core_models.MissionSampleType.objects.get(pk=mission_sample_type_id)

    queryset = get_samples_queryset(request.POST, mission_sample_type.samples.all())
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


def clear_filters(request, mission_sample_type_id):
    mission_sample_type = core_models.MissionSampleType.objects.get(pk=mission_sample_type_id)
    form = MissionSampleTypeFilter(mission_sample_type=mission_sample_type, collapsed=False)

    return form_mission_sample_filter.clear_filters(form)


url_prefix = "sample_type"
sample_type_urls = [
    path(f'{url_prefix}/<int:mission_sample_type_id>/', filter_datatype, name="form_mission_filter_datatype"),
    path(f'{url_prefix}/row/<int:mission_sample_type_id>/', update_sample_type, name="form_mission_sample_type_set"),
    path(f'{url_prefix}/delete/<int:mission_sample_type_id>/', sample_delete, name="form_mission_sample_type_delete"),
    path(f'{url_prefix}/clear/<int:mission_sample_type_id>/', clear_filters, name="form_mission_sample_type_clear"),

    path(f'{url_prefix}/list/<int:mission_sample_type_id>/', list_samples, name="mission_sample_type_sample_list"),

]
