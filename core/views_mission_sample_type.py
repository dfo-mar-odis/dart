import numpy as np
import pandas as pd

from bs4 import BeautifulSoup
from crispy_forms.utils import render_crispy_form
from django.db.models import Max
from django.http import HttpResponse
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _
from django_pandas.io import read_frame

from core import views, models, forms

from dart2.views import GenericDetailView


class SampleTypeDetails(GenericDetailView):
    model = models.MissionSampleType
    page_title = _("Sample Type")
    template_name = "core/mission_sample_type.html"

    def get_page_title(self):
        return _("Mission Sample Type") + f" : {self.object.mission.name} - {self.object.name}"

    def get_settings_url(self):
        return reverse_lazy("core:mission_edit", args=(self.object.pk,))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['reports'] = {key: reverse_lazy(views.reports[key], args=(self.object.mission.pk,)) for key in
                              views.reports.keys()}

        context['mission_sample_type'] = self.object
        data_type_seq = self.object.datatype

        database = self.kwargs['database']
        initial = {'sample_type_id': self.object.id, 'mission_id': self.object.mission.id}
        if data_type_seq:
            initial['data_type_code'] = data_type_seq.data_type_seq

        context['biochem_form'] = forms.BioChemDataType(database=database, initial=initial)

        return context


def sample_type_card(request, database, sample_type_id):
    mission_sample_type = models.MissionSampleType.objects.using(database).get(pk=sample_type_id)

    sample_type_form = forms.CardForm(card_title=str(mission_sample_type), card_name="mission_sample_type")
    sample_type_html = render_crispy_form(sample_type_form)
    sample_type_soup = BeautifulSoup(sample_type_html, 'html.parser')

    card_body_div = sample_type_soup.find(id=sample_type_form.get_card_body_id())
    card_body_div.attrs['hx-get'] = reverse_lazy("core:mission_sample_type_sample_list", args=(database,
                                                                                               sample_type_id,))
    card_body_div.attrs['hx-trigger'] = 'load'

    form_soup = BeautifulSoup(f'<div id="div_id_{sample_type_form.get_card_name()}"></div>', 'html.parser')
    form = form_soup.find('div')
    form.append(sample_type_soup)

    return HttpResponse(form_soup)


def list_samples(request, database, sample_type_id, **kwargs):
    mission_sample_type = models.MissionSampleType.objects.using(database).get(pk=sample_type_id)

    page = int(request.GET['page'] if 'page' in request.GET else 0)
    page_limit = 50
    page_start = page_limit * page

    # unfortunately if a page doesn't contain columns for 1 or 2 replicates when there's more the
    # HTML table that gets returned to the interface will be missing columns and it throws everything
    # out of alignment. We'll get the replicate columns here and use that value to insert blank
    # columns into the dataframe if a replicate column is missing from the query set.
    replicates = models.DiscreteSampleValue.objects.using(database).filter(
        sample__type__id=sample_type_id).aggregate(Max('replicate'))['replicate__max']

    queryset = mission_sample_type.samples.all()
    queryset = queryset.order_by('bottle__bottle_id')[page_start:(page_start + page_limit)]

    if not queryset.exists():
        # if there are no more bottles then we stop loading, otherwise weird things happen
        return HttpResponse()

    queryset = queryset.values(
        'bottle__bottle_id',
        'bottle__pressure',
        'discrete_values__replicate',
        'discrete_values__value',
        'discrete_values__flag',
        'discrete_values__datatype',
        'discrete_values__comment',
    )
    headings = ['Value', 'Flag', 'Datatype', 'Comments']
    df = read_frame(queryset)
    df.columns = ["Sample", "Pressure", "Replicate", ] + headings
    df = df.pivot(index=['Sample', 'Pressure', ], columns=['Replicate'])

    for j, column in enumerate(headings):
        for i in range(1, replicates + 1):
            col_index = (column, i,)
            if col_index not in df.columns:
                index = j * replicates + i - 1
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
                                           args=(database, sample_type_id,)) + f"?page={page + 1}"
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


def format_sensor_table(df: pd.DataFrame, mission_sample_type: models.MissionSampleType) -> BeautifulSoup:
    # Pandas has the ability to render dataframes as HTML and it's super fast, but the default table looks awful.

    # start by replacing nan values with '---'
    df.fillna('---', inplace=True)

    # reformat the Datatype columns, which will be represented as floats, but we want them as integers
    for i in range(1, df['Datatype'].shape[1] + 1):
        df[('Datatype', i,)] = df[('Datatype', i)].astype('string')
        df[('Datatype', i,)] = df[('Datatype', i,)].map(lambda x: int(float(x)) if x != '---' else x)

    # convert the dataframe to an HTML table
    html = '<div id="sample_table">' + df.to_html() + "</div>"

    # Using BeautifulSoup for html manipulation to post process the HTML table Pandas created
    soup = BeautifulSoup(html, 'html.parser')

    # this will be a big table add scrolling
    sample_table = soup.find(id="sample_table")
    sample_table.attrs['class'] = "vertical-scrollbar"

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
    while (th := th.findNext('th')):
        th.attrs['class'] = 'text-center'
        if th.string == 'Comments':
            th.attrs['class'] += ' w-100'

    root.append(table)

    return soup


def sample_delete(request, database, sample_type_id):
    mission_sample_type = models.MissionSampleType.objects.using(database).get(pk=sample_type_id)
    mission = mission_sample_type.mission

    if request.method == "POST":
        models.Sample.objects.filter(type=mission_sample_type).delete()
        mission_sample_type.delete()

        # send the user back to the all samples page.
        attrs = {
            'component_id': "div_id_delete_samples",
            'alert_type': 'info',
            'message': _("Loading"),
            'hx-get': reverse_lazy('core:mission_samples_sample_details', args=(database, mission.pk,)),
            'hx-trigger': 'load',
            'hx-push-url': 'true'
        }
        soup = forms.save_load_component(**attrs)
        return HttpResponse(soup)

    return list_samples(request, sample_type_id=sample_type_id)


# ###### Mission Sample ###### #
url_prefix = "<str:database>/sampletype"
mission_sample_type_urls = [
    path(f'{url_prefix}/<int:pk>/', SampleTypeDetails.as_view(), name="mission_sample_type_details"),

    path(f'{url_prefix}/card/<int:mission_sample_type_id>/', sample_type_card, name="mission_sample_type_card"),
    path(f'{url_prefix}/list/<int:mission_sample_type_id>/', list_samples, name="mission_sample_type_sample_list"),

    path(f'{url_prefix}/delete/<int:sample_type_id>/', sample_delete, name="mission_sample_type_delete"),

]