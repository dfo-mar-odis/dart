import logging

from bs4 import BeautifulSoup

from django import forms
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import path, reverse_lazy
from django.utils.translation import gettext_lazy as _

from config import utils
from config.utils import load_svg
from dart import models

logger = logging.getLogger('dart')
user_logger = logging.getLogger('dart.user')


class MissionListFilterForm(forms.Form):
    mission_name = forms.CharField(
        label="Mission Name",
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    start_date = forms.DateField(
        label="Start Date",
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    end_date = forms.DateField(
        label="End Date",
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )


def get_button_col(soup, database):
    btn_column = soup.new_tag('div', attrs={'class': 'col-auto'})
    attr_common = {'class': 'btn btn-primary ms-1'}
    btn_column.append(btn_metadata:=soup.new_tag('a', title=_("Mission Metadata"), attrs=attr_common))
    btn_column.append(btn_events:=soup.new_tag('a', title=_("Mission Events"), attrs=attr_common))
    btn_column.append(btn_samples:=soup.new_tag('a', title=_("Mission Samples"), attrs=attr_common))
    btn_column.append(btn_plankton:=soup.new_tag('a', title=_("Mission Plankton"), attrs=attr_common))

    btn_metadata.append(BeautifulSoup(load_svg('gear'), 'html.parser'))
    btn_events.append(BeautifulSoup(load_svg('calendar'), 'html.parser'))
    btn_samples.append(BeautifulSoup(load_svg('beaker'), 'html.parser'))
    btn_plankton.append(BeautifulSoup(load_svg('plankton'), 'html.parser'))

    btn_metadata.attrs['href'] = reverse_lazy("dart:mission_update", args=(database, 1,))
    btn_events.attrs['href'] = reverse_lazy("dart:mission_events", args=(database, 1,))
    return btn_column

def get_mission_details(database):
    if isinstance(database, models.Mission):
        db_name = database.name
        start_date = database.start_date
        end_date = database.end_date
    else:
        db_name = database['name']
        start_date = None
        end_date = None

    return db_name, start_date, end_date

def list_missions(request):
    soup = BeautifulSoup('<div hx-swap-oob="true" class="vertical-scrollbar" id="card_body_mission_filter"></div>', 'html.parser')

    if request.method == "POST":
        database_dict = utils.get_mission_dictionary(filter=request.POST)
    else:
        database_dict = utils.get_mission_dictionary()

    div = soup.find('div', id="card_body_mission_filter")
    div.append(table := soup.new_tag('table', attrs={'class': 'table table-striped', 'id': 'mission_list_table'}))
    thead = soup.new_tag('thead')
    tr_head = soup.new_tag('tr')
    for col in ['Mission Name', 'Start Date', 'End Date', 'Status', 'Actions']:
        th = soup.new_tag('th', string=col)
        tr_head.append(th)
    thead.append(tr_head)
    table.append(thead)

    tbody = soup.new_tag('tbody')
    for index, key in enumerate(database_dict):
        database = database_dict[key]
        db_name, start_date, end_date = get_mission_details(database)

        tr = soup.new_tag('tr', id=f'mission_list_{index}_row')
        tr.append(soup.new_tag('td', string=f"{db_name}"))
        tr.append(soup.new_tag('td', string=f"{start_date}"))
        tr.append(soup.new_tag('td', string=f"{end_date}"))
        tr.append(soup.new_tag('td', id=f'mission_list_{index}_status'))
        td_actions = soup.new_tag('td')
        td_actions.append(get_button_col(soup, key))
        tr.append(td_actions)
        tbody.append(tr)

    table.append(tbody)
    return soup


def filter_missions(request, **kwargs):
    soup = BeautifulSoup('', 'html.parser')

    if request.method == "GET":
        soup.append(soup.new_tag("div", id="form_id_mission_list_hidden_submit",
                                 attrs={'hx-swap': 'none',
                                        'hx-post': request.path,
                                        'hx-swap-oob': 'true',
                                        'hx-trigger': 'load'}))
        return HttpResponse(soup)


    soup = list_missions(request)
    return HttpResponse(soup)

def filter_missions_reset(request, **kwargs):
    soup = BeautifulSoup('', 'html.parser')

    if request.method == "GET":
        form = MissionListFilterForm()
        form_html = render_to_string('dart/forms/mission_list_filter_form.html', {'form': form})
        form_soup = BeautifulSoup(form_html, 'html.parser')
        form = form_soup.find(id="form_id_mission_list")
        form.attrs['hx-swap-oob'] = 'true'
        soup.append(form)
        return HttpResponse(soup)

    return HttpResponse(soup)

urlpatterns = [
    path("mission/list/", list_missions, name="form_mission_list_missions"),
    path('mission/filter_form/filter/', filter_missions, name='form_mission_list_filter_filter'),
    path('mission/filter_form/reset/', filter_missions_reset, name='form_mission_list_filter_filter_reset'),
]