import os
from os import listdir

from bs4 import BeautifulSoup
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field
from crispy_forms.utils import render_crispy_form

from django import forms
from django.db import connections
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.conf import settings
from django.core.cache import caches

from render_block import render_block_to_string

import settingsdb.utils
from dart.utils import load_svg
from settingsdb import models as setting_models
from core import models
from settingsdb import filters

from dart.views import GenericTemplateView


def get_mission_dictionary(db_dir):
    if not os.path.exists(db_dir):
        os.mkdir(db_dir)

    databases = [f.replace(".sqlite3", "") for f in listdir(db_dir) if
                 os.path.isfile(os.path.join(db_dir, f)) and f.endswith('sqlite3')]

    missions = {}
    for database in databases:
        databases = settings.DATABASES
        databases[database] = databases['default'].copy()
        databases[database]['NAME'] = os.path.join(db_dir, f'{database}.sqlite3')
        if models.Mission.objects.using(database).exists():
            if not settingsdb.utils.is_database_synchronized(database):
                missions[database] = {'name': database, 'biochem_table': '', 'requires_migration': 'true'}
            else:
                mission = models.Mission.objects.using(database).first()
                missions[database] = mission

    for connection in connections.all():
        if connection.alias != 'default':
            connection.close()
            settings.DATABASES.pop(connection.alias)

    return missions


class MissionDirForm(forms.Form):
    directory = forms.ChoiceField(label="Mission Databases Directory")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['directory'].choices = [(db.pk, db.database_location) for db in
                                            setting_models.LocalSetting.objects.using('default').all()]
        self.fields['directory'].choices.append((-1, '--- New ---'))

        self.helper = FormHelper(self)
        self.helper.form_tag = False

        selection_attrs = {
            'hx-trigger': 'change',
            'hx-get': reverse_lazy("settingsdb:update_mission_directory"),
            'hx-swap': "outerHTML"
        }
        self.helper.layout = Layout(
            Div(Field('directory', css_class="form-select-sm", id="select_id_mission_directory", **selection_attrs))
        )


def init_connection():
    connected = setting_models.LocalSetting.objects.using('default').filter(connected=True)
    if connected.count() > 1:
        for connection in connected:
            connection.connected = False
            connection.save()
        initial = connected.first()
        initial.connected = True
        initial.save()
    elif connected.exists():
        initial = connected.first()
    else:
        if not setting_models.LocalSetting.objects.using('default').filter(pk=1).exists():
            initial = setting_models.LocalSetting(pk=1, database_location="./missions")
            initial.save()
            return initial

        initial = setting_models.LocalSetting.objects.using('default').get(pk=1)

    return initial


class MissionFilterView(GenericTemplateView):
    model = models.Mission
    page_title = _("Mission")
    template_name = 'settingsdb/mission_filter.html'

    filterset_class = filters.MissionFilter
    new_url = reverse_lazy("core:mission_new")
    home_url = ""
    fields = ["id", "name", "biochem_table"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        initial = init_connection()
        context['new_url'] = self.new_url
        context['dir_select_form'] = MissionDirForm(initial={"directory": initial.pk})
        context['missions'] = get_mission_dictionary(initial.database_location)

        return context


def list_missions(request):
    connected = init_connection()

    context = {'missions': get_mission_dictionary(connected.database_location)}
    html = render_block_to_string('settingsdb/mission_filter.html', 'mission_table_block', context)
    response = HttpResponse(html)

    return response


def reset_connection(location_id):
    connections = setting_models.LocalSetting.objects.filter(connected=True)
    for connected in connections:
        connected.connected = False
        connected.save()

    connection = setting_models.LocalSetting.objects.get(pk=location_id)
    connection.connected = True
    connection.save()


def add_mission_dir(request):
    soup = BeautifulSoup()

    if request.method == "GET" and 'directory' in request.GET:
        if request.GET['directory'] == '-1':
            row = soup.new_tag('div')
            row.attrs['class'] = 'container-fluid row'

            station_input = soup.new_tag('input')
            station_input.attrs['name'] = 'directory'
            station_input.attrs['id'] = 'id_directory_field'
            station_input.attrs['type'] = 'text'
            station_input.attrs['class'] = 'textinput form-control form-control-sm col'

            submit = soup.new_tag('button')
            submit.attrs['class'] = 'btn btn-primary btn-sm ms-2 col-auto'
            submit.attrs['name'] = "update_mission_directory"
            submit.attrs['hx-post'] = request.path
            submit.attrs['hx-target'] = '#div_id_directory'
            submit.attrs['hx-select'] = '#div_id_directory'
            submit.attrs['hx-swap'] = 'outerHTML'
            submit.append(BeautifulSoup(load_svg('plus-square'), 'html.parser').svg)

            row.append(station_input)
            row.append(submit)

            soup.append(row)

            return HttpResponse(soup)

        location_id = int(request.GET['directory'])
        reset_connection(location_id)

        soup = BeautifulSoup()
        mission_form = MissionDirForm(initial={"directory": location_id})
        mission_html = render_crispy_form(mission_form)
        select_soup = BeautifulSoup(mission_html)
        soup.append(select_soup.find(id="select_id_mission_directory"))

        response = HttpResponse(soup)
        response['Hx-Trigger'] = "db_dir_changed"
        return response

    elif 'directory' in request.POST:
        new_location = request.POST['directory']
        location = setting_models.LocalSetting(database_location=new_location)
        location.save(using='default')
        location = setting_models.LocalSetting.objects.order_by('id').last()

        reset_connection(location.pk)

        mission_form = MissionDirForm(initial={"directory": location.pk})
        mission_html = render_crispy_form(mission_form)

        response = HttpResponse(mission_html)
        response['Hx-Trigger'] = "db_dir_changed"
        return response


def migrate_database(request, database):
    if request.method == 'GET':
        soup = BeautifulSoup('', 'html.parser')
        soup.append(spinner := soup.new_tag('div', attrs={'id': "div_id_spinner",
                                                          'class': 'spinner-border',
                                                          'role': 'status'}))

        spinner.attrs['hx-post'] = request.path
        spinner.attrs['hx-trigger'] = "load"
        spinner.attrs['hx-target'] = f"#tr_id_mission_{ database }"
        spinner.attrs['hx-select'] = f"#tr_id_mission_{ database }"
        spinner.attrs['hx-swap'] = "outerHTML"

        spinner.append(status := soup.new_tag('span', attrs={'class': "visually-hidden"}))
        status.string = _("Migrating...")

        return HttpResponse(soup)

    missions = {}
    settingsdb.utils.connect_database(database)
    settingsdb.utils.migrate(database)

    if models.Mission.objects.using(database).exists():
        mission = models.Mission.objects.using(database).first()
        missions[database] = mission

    context = {
        'missions': missions
    }
    html = render_block_to_string('settingsdb/mission_filter.html', "mission_table_block", context)
    soup = BeautifulSoup(html, 'html.parser')

    return HttpResponse(soup)
