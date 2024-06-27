import datetime
import os
from os import listdir

from bs4 import BeautifulSoup
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, Column, Row, Hidden
from crispy_forms.utils import render_crispy_form

from django import forms
from django.core.files.base import ContentFile
from django.db import connections, OperationalError
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.conf import settings

from render_block import render_block_to_string

from dart.utils import load_svg
from settingsdb import models as setting_models
from core import models
from core import forms as core_forms
from settingsdb import filters, utils

from dart.views import GenericTemplateView

import logging

logger = logging.getLogger('dart')


if 'settingsdb_globalstation' in connections['default'].introspection.table_names():
    # if running migrations this will cause an issue if the global stations table hasn't been created yet
    reports = {
        f"Fix Station {station.name}": reverse_lazy('settingsdb:fixstation', args=(station.pk,))
        for station in setting_models.GlobalStation.objects.filter(fixstation=True).order_by('name')
    }


class MissionFilterForm(forms.Form):
    before_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'max': "9999-12-31"}))
    after_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'max': "9999-12-31"}))
    hidden_change = forms.HiddenInput()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False

        url = reverse_lazy('settingsdb:mission_filter_list_missions')
        attrs = {'hx-trigger': "keyup delay:500ms, change", 'hx-post': url, 'hx-target': "#mission_table"}
        hidden_attrs = {'hx-trigger': "db_dir_changed from:body", 'hx-post': url, 'hx-target': "#mission_table"}

        self.helper.layout = Layout(
            Row(
                Hidden('hidden_change', '', **hidden_attrs),
                Column(Field('after_date', **attrs), css_class=''),
                Column(Field('before_date', **attrs), css_class=''),
            )
        )


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
        try:
            if models.Mission.objects.using(database).exists():
                if not utils.is_database_synchronized(database):
                    version = getattr(models.Mission.objects.using(database).first(), 'dart_version', None)
                    missions[database] = {'name': database, 'biochem_table': '',
                                          'requires_migration': 'true', 'version': version}
                else:
                    mission = models.Mission.objects.using(database).first()
                    missions[database] = mission
        except Exception as ex:
            logger.exception(ex)
            logger.error(_("Cound not open database, it appears to be corrupted") + " : " + database)

    for connection in connections.all():
        if connection.alias != 'default':
            connection.close()
            settings.DATABASES.pop(connection.alias)

    return missions


def init_connection(use_default=False):
    connected = setting_models.LocalSetting.objects.using('default').filter(connected=True)
    if connected.exists() and not use_default:
        if connected.count() > 1:
            for connection in connected:
                connection.connected = False
                connection.save()
            initial = connected.first()
            initial.connected = True
            initial.save()
        else:
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
        try:
            context['missions'] = get_mission_dictionary(initial.database_location)
        except Exception as e:
            # if for some reason the get mission directory fails, revert the connected directory to the default
            # initial = init_connection(use_default=True)
            # context['missions'] = get_mission_dictionary(initial.database_location)
            pass

        context['new_url'] = self.new_url
        context['mission_filter_form'] = MissionFilterForm()
        context['dir_select_form'] = MissionDirForm(initial={"directory": initial.pk})

        if reports:
            context['reports'] = reports
        return context


def get_filter_dates(array: dict):
    before_date = array.get('before_date', '')
    if before_date:
        try:
            before_date = datetime.datetime.strptime(before_date, "%Y-%m-%d").date()
        except ValueError:
            before_date = None

    after_date = array.get('after_date', '')
    if after_date:
        try:
            after_date = datetime.datetime.strptime(after_date, "%Y-%m-%d").date()
        except ValueError:
            after_date = None

    return after_date, before_date


def filter_missions(after_date, before_date) -> list[dict]:
    connected = init_connection()
    missions_dict = {}
    try:
        missions_dict = get_mission_dictionary(connected.database_location)
    except Exception as ex:
        pass

    missions = []
    for database, mission in missions_dict.items():
        if before_date:
            if mission.end_date and mission.end_date > before_date:
                continue
        if after_date:
            if mission.start_date and mission.start_date < after_date:
                continue

        version = mission['version'] if type(mission) == dict else getattr(mission, 'dart_version', 'No version number')
        missions.append({'database': database, 'mission': mission,
                         'version': version})

    return missions


def list_missions(request):

    report_filter = []

    before_date = None
    after_date = None
    if request.method == 'POST':
        after_date, before_date = get_filter_dates(request.POST)

    if before_date:
        report_filter.append(f'before_date={before_date}')
    if after_date:
        report_filter.append(f'after_date={after_date}')

    missions = filter_missions(after_date, before_date)

    def sort_key(m):
        start_date = getattr(m['mission'], 'start_date', None)  # m['mission'].start_date if
        return start_date if start_date else datetime.datetime.strptime('1900-01-01', '%Y-%m-%d').date()

    missions = sorted(missions, key=sort_key, reverse=True)

    context = {'missions': missions}
    html = render_block_to_string('settingsdb/partials/mission_table.html', 'mission_table_block', context)
    soup = BeautifulSoup('', 'html.parser')
    table_soup = BeautifulSoup(html, 'html.parser')

    # update the report dropdown to use the after/before dates in the fixstation report call
    soup.append(ul_reports := soup.new_tag('ul', id="ul_id_fixstation_reports"))
    ul_reports.attrs['class'] = "dropdown-menu"
    ul_reports.attrs['hx-swap-oob'] = 'innerHTML'

    stations = setting_models.GlobalStation.objects.filter(fixstation=True).order_by('name')
    r_filters = ("?" + '&'.join(report_filter)) if len(report_filter) > 0 else ''
    for station in stations:
        ul_reports.append(li := soup.new_tag("li"))
        li.append(a := soup.new_tag('a'))
        a.string = f"Fix Station {station.name}"
        a.attrs['href'] = reverse_lazy('settingsdb:fixstation', args=(station.pk,)) + r_filters
        a.attrs['class'] = "dropdown-item"

    soup.append(table_soup)
    response = HttpResponse(soup)
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
            submit.attrs['title'] = _('Add directory')
            submit.append(BeautifulSoup(load_svg('plus-square'), 'html.parser').svg)

            cancel = soup.new_tag('button')
            cancel.attrs['class'] = 'btn btn-danger btn-sm ms-2 col-auto'
            cancel.attrs['name'] = "cancel"
            cancel.attrs['hx-post'] = request.path
            cancel.attrs['hx-target'] = '#div_id_directory'
            cancel.attrs['hx-select'] = '#div_id_directory'
            cancel.attrs['hx-swap'] = 'outerHTML'
            cancel.attrs['title'] = _('Cancel')
            cancel.append(BeautifulSoup(load_svg('x-square'), 'html.parser').svg)

            row.append(station_input)
            row.append(submit)
            row.append(cancel)

            soup.append(row)

            return HttpResponse(soup)

        location_id = int(request.GET['directory'])
        reset_connection(location_id)

        soup = BeautifulSoup()
        mission_form = MissionDirForm(initial={"directory": location_id})
        mission_html = render_crispy_form(mission_form)
        select_soup = BeautifulSoup(mission_html)
        soup.append(select_soup.find(id="select_id_mission_directory"))

    else:
        location = setting_models.LocalSetting.objects.first()
        if 'cancel' in request.POST:
            if setting_models.LocalSetting.objects.filter(connected=True).exists():
                location = setting_models.LocalSetting.objects.get(connected=True)

        elif 'directory' in request.POST:
            new_location = request.POST['directory']
            if new_location.strip() == '':
                location = setting_models.LocalSetting.objects.first()
            elif not (location := setting_models.LocalSetting.objects.filter(database_location=new_location)).exists():
                location = setting_models.LocalSetting(database_location=new_location)
                location.save(using='default')
                location = setting_models.LocalSetting.objects.order_by('id').last()
            else:
                location = location.first()

        reset_connection(location.pk)

        mission_form = MissionDirForm(initial={"directory": location.pk})
        mission_html = render_crispy_form(mission_form)

        soup = BeautifulSoup(mission_html, 'html.parser')

    response = HttpResponse(soup)
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

    missions = []
    utils.connect_database(database)
    utils.migrate(database)

    if models.Mission.objects.using(database).exists():
        mission = models.Mission.objects.using(database).first()
        missions.append({'mission': mission, 'database': database})

    context = {
        'missions': missions
    }
    html = render_block_to_string('settingsdb/partials/mission_table.html', "mission_table_block", context)
    soup = BeautifulSoup(html, 'html.parser')

    return HttpResponse(soup)


def fixstation(request, station_id):
    before_date = None
    after_date = None
    if request.method == 'GET':
        after_date, before_date = get_filter_dates(request.GET)

    missions = filter_missions(after_date, before_date)
    station = setting_models.GlobalStation.objects.get(pk=station_id)

    sample_types = {"Oxygen": "oxy", "Salinity": "salts"}
    sample_type_order = [sample_type for sample_type in sample_types.keys()]

    headings = ['Mission', 'Event', 'Date', 'Bottom_id']
    headings += sample_type_order
    headings.append("Comments")
    data = ",".join(headings) + "\n"

    for mission in missions:
        key = mission['database']
        utils.connect_database(key)
        events = models.Event.objects.using(key).filter(station__name__iexact=station,
                                                        instrument__type=models.InstrumentType.ctd)
        logger.info(f"Mission: {key} - Events found: {events.count()}")
        for event in events:
            mission = event.mission
            event_id = f"{event.event_id:03d}"
            date = event.start_date if event.start_date else event.start_date
            sample_id = f"{event.sample_id}"
            data += ",".join([mission.name, event_id, date.strftime("%Y-%m-%d") if date else "----", sample_id])

            for sample_type in sample_type_order:
                data += ","
                if mission.mission_sample_types.filter(name=sample_types[sample_type]).exists():
                    data += "x"

            comment = ""
            if (action := event.actions.filter(type=models.ActionType.deployed)).exists():
                comment = action.first().comment
            data += f",{comment}\n"

    file_to_send = ContentFile(data)

    response = HttpResponse(file_to_send, content_type="text/csv")
    response['Content-Length'] = file_to_send.size
    response['Content-Disposition'] = f'attachment; filename="FixStation_{station}.csv"'
    return response
