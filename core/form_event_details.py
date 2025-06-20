import datetime
import io
import time
import re
import numpy as np

from bs4 import BeautifulSoup
from crispy_forms.bootstrap import StrictButton
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Column, Row, Hidden, Field, Layout, HTML
from crispy_forms.utils import render_crispy_form
from django import forms
from django.core.cache import caches
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import path, reverse_lazy
from django.utils.translation import gettext as _

from render_block import render_block_to_string

from core import forms as core_forms, models, validation
from core.parsers import FilterLogParser, elog, andes, event_csv
from core.parsers.FixStationParser import FixStationParser

from config.utils import load_svg

from settingsdb import models as settings_models

import logging

logger = logging.getLogger('dart')


class EventDetails(core_forms.CardForm):

    event = None
    # when creating a new event a mission is required to attach the event too
    mission = None

    def get_delete_button(self) -> StrictButton:
        # url = reverse_lazy('core:mission_samples_upload_biochem', args=(self.mission_id,))
        button_icon = load_svg('dash-square')
        button_id = f'btn_id_delete_{self.card_name}'
        button_attrs = {
            'id': button_id,
            'name': 'delete_event',
            'title': _("Delete Event"),
            'hx-post': reverse_lazy("core:form_event_delete_event", args=(self.event.pk,)),
            'hx-confirm': _("Are you sure?"),
            'hx-swap': 'none'
        }
        button = StrictButton(button_icon, css_class='btn btn-sm btn-danger', **button_attrs)

        return button

    def get_edit_button(self) -> StrictButton:
        # url = reverse_lazy('core:mission_samples_upload_biochem', args=(self.mission_id,))
        button_icon = load_svg('pencil-square')
        button_id = f'btn_id_edit_{self.card_name}'
        button_attrs = {
            'id': button_id,
            'name': 'edit_event',
            'title': _("Edit Event"),
            'hx-get': reverse_lazy("core:form_event_edit_event", args=(self.event.pk,)),
            'hx-swap': 'outerHTML',
            'hx-target': f'#{self.get_card_id()}'
        }
        button = StrictButton(button_icon, css_class='btn btn-sm btn-secondary', **button_attrs)

        return button

    def get_add_button(self) -> StrictButton:
        # url = reverse_lazy('core:mission_samples_upload_biochem', args=(self.mission_id,))
        button_icon = load_svg('plus-square')
        button_id = f'btn_id_add_{self.card_name}'
        button_attrs = {
            'id': button_id,
            'name': 'new_event',
            'title': _("New Event"),
            'hx-get': reverse_lazy("core:form_event_add_event", args=(self.mission.pk,)),
            'hx-swap': 'outerHTML',
            'hx-target': f"#{self.get_card_id()}"
        }
        button = StrictButton(button_icon, css_class='btn btn-sm btn-primary', **button_attrs)

        return button

    def get_copy_button(self) -> StrictButton:
        # url = reverse_lazy('core:mission_samples_upload_biochem', args=(self.mission_id,))
        button_icon = load_svg('copy')
        button_id = f'btn_id_add_{self.card_name}'
        button_attrs = {
            'id': button_id,
            'name': 'copy_event',
            'title': _("Copy Station and Instrument"),
            'hx-get': reverse_lazy("core:form_event_add_event", args=(self.mission.pk, self.event.pk,)),
            'hx-swap': 'outerHTML',
            'hx-target': f"#{self.get_card_id()}"
        }
        button = StrictButton(button_icon, css_class='btn btn-sm btn-primary', **button_attrs)

        return button

    def get_bottle_file_button(self):
        # url = reverse_lazy('core:mission_samples_upload_biochem', args=(self.mission_id,))
        button_icon = load_svg('plastic-bottle-icon')
        button_id = f'btn_id_bottle_file_{self.card_name}'
        url = reverse_lazy("core:form_event_fix_station_bottle", args=(self.event.pk,))
        button = HTML(
            f'<span>'
            f'<label for="{button_id}" class ="btn btn-primary btn-sm" title="{_("Load Bottle File")}">'
            f'{button_icon}</label>'
            f'<input id="{button_id}" type="file" name="bottle_files" accept=".ros, .btl" multiple="true" '
            f'hx-get="{url}" hx-trigger="change" hx-swap="none" class="invisible"/>'
            f'</span>'
        )

        return button

    def get_card_message_area_id(self):
        return f"div_id_card_message_area_{self.card_name}"

    def get_card_message_area(self) -> Div:
        return Div(id=self.get_card_message_area_id())

    def get_card_header(self) -> Div:
        header = super().get_card_header()

        start_row_spacer = Column(id='col_id_event_button')

        end_row_spacer = Row(css_class="align-self-end")

        button_column = Column()
        if self.event and not self.event.files:
            del_btn = self.get_delete_button()
            edit_btn = self.get_edit_button()
            bottle_btn = self.get_bottle_file_button()
            if del_btn:
                button_column.fields.append(del_btn)

            if bottle_btn:
                start_row_spacer.fields.append(bottle_btn)

            if edit_btn:
                start_row_spacer.fields.append(edit_btn)

        add_btn = self.get_add_button()
        if add_btn and self.mission:
            if self.event:
                start_row_spacer.fields.append(self.get_copy_button())
            start_row_spacer.fields.append(add_btn)

        end_row_spacer.fields.append(button_column)
        input_column = Column(end_row_spacer, css_class="col-auto")

        header.fields[0].fields.append(start_row_spacer)
        header.fields[0].fields.append(input_column)

        header.fields.append(self.get_card_message_area())

        return header

    def get_card_content_id(self):
        return f"div_event_{self.card_name}_content_id"

    def get_card_body(self) -> Div:
        body = super().get_card_body()
        body.css_class += " vertical-scrollbar"
        div_content = Div(
            id=self.get_card_content_id(),
        )
        # content_frame = Div(div_content, css_class="vertical-scrollbar")
        content_frame = Div(div_content)

        body.fields.append(content_frame)
        return body

    def get_card(self, attrs: dict = None) -> Div:
        card = super().get_card({
            'hx-trigger': 'event_selected from:body',
            'hx-target': f'#{self.get_card_id()}',
            'hx-swap': "outerHTML",
            'hx-get': reverse_lazy("core:form_event_get_selected_event")
        })
        return card

    def __init__(self, event=None, mission=None, editing=False, *args, **kwargs):
        self.event = event
        self.mission = mission if mission else event.mission
        self.editing = editing

        super().__init__(card_name='event_details', card_title=_("Event Details"), *args, **kwargs)


# This form can be used the same as the event details form, but will remove buttons in the Card Header
class NoDeleteEditEventDetails(EventDetails):
    def get_add_button(self):
        # We're going to use a '<label for="">...</label>' element to activate this button to put the
        # button in a much more logical place for the user, this button still needs to exist and be referenced
        # by the label tag, but it can be hidden.
        #
        # Once the add_event post action happens this label will need to be removed

        button_icon = load_svg('check-square')
        label_string = '<label id="label_id_add_event" class="btn btn-sm btn-success" for="btn_id_add_event">'
        return HTML(label_string + button_icon + '</label>')

    def get_edit_button(self):
        return None

    def get_delete_button(self):
        return None


class EventForm(forms.ModelForm):

    global_station = forms.ChoiceField(label=_("Station"))

    class Meta:
        model = models.Event
        fields = ['mission', 'event_id', 'station', 'instrument', 'sample_id', 'end_sample_id',
                  'flow_start', 'flow_end', 'wire_out', 'wire_angle']

    @staticmethod
    def get_instrument_input_id():
        return "id_event_instrument_field"

    @staticmethod
    def get_station_input_id():
        return "id_event_station_field"

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.fields['station'].required = False
        self.fields['mission'].queryset = models.Mission.objects.all()
        self.mission = models.Mission.objects.first()  # There's only ever one mission per DB

        self.helper = FormHelper(self)

        # Have to disable the form tag in crispy forms because by default cirspy will add a method to the form tag #
        # that can't be removed and that plays havoc with htmx calls where the post action is on the input buttons #
        # the form tag has to surround the {% crispy <form name> %} tag and have an id matching the hx_target
        self.helper.form_tag = False

        stations = settings_models.GlobalStation.objects.all().order_by("name")
        self.fields['global_station'].queryset = stations

        self.fields['global_station'].choices = [(None, '--------')]
        self.fields['global_station'].choices += [(st.id, st) for st in settings_models.GlobalStation.objects.all()]
        self.fields['global_station'].choices.append((-1, '-- New --'))

        apply_attrs = {
            'name': 'add_event',
            'title': _('Submit'),
            'hx-swap': 'none',
        }

        if self.instance.pk:
            gl_station = settings_models.GlobalStation.objects.get_or_create(name=self.instance.station.name.upper())[0]
            self.fields['global_station'].initial = gl_station.pk
        elif self.mission:
            # When adding an event we'll swap the whole card the form appears on.
            submit_url = reverse_lazy('core:form_event_add_event', args=(self.mission.pk,))
            apply_attrs['hx-post'] = submit_url
            apply_attrs['hx-swap'] = "outerHTML"
            apply_attrs['hx-target'] = "#div_id_card_event_details"

            if 'station' in self.initial:
                station = models.Station.objects.get(pk=self.initial['station'])
                gl_station = settings_models.GlobalStation.objects.filter(name__iexact=station.name)
                if gl_station.exists():
                    self.fields['global_station'].initial = gl_station.first().pk

        # The event ID and refresh button are in the core/template/partials/event_edit_form.html template
        # if self.instance.pk:
        #     event_element = Column(Hidden('event_id', self.instance.event_id))
        #     submit_button = StrictButton(load_svg('arrow-clockwise'), css_class="btn btn-primary btn-sm ms-2",
        #                              **apply_attrs)

        self.fields['global_station'].widget.attrs["hx-swap"] = 'outerHTML'
        self.fields['global_station'].widget.attrs["hx-trigger"] = 'change'
        self.fields['global_station'].widget.attrs["hx-target"] = f'#{self.get_station_input_id()}'
        self.fields['global_station'].widget.attrs["hx-get"] = reverse_lazy('core:form_event_update_stations')

        instruments = models.Instrument.objects.all().order_by("name")
        self.fields['instrument'].queryset = instruments

        self.fields['instrument'].choices = [(None, '--------')]
        self.fields['instrument'].choices += [(ins.id, ins) for ins in instruments]
        self.fields['instrument'].choices.append((-1, '-- New --'))

        self.fields['instrument'].widget.attrs["hx-swap"] = 'outerHTML'
        self.fields['instrument'].widget.attrs["hx-trigger"] = 'change'
        self.fields['instrument'].widget.attrs["hx-target"] = f'#{self.get_instrument_input_id()}'
        self.fields['instrument'].widget.attrs["hx-get"] = reverse_lazy('core:form_event_update_instruments')

        self.helper.layout = Layout(
            Hidden('mission', self.initial.get('mission', '1')),
            Row(
                Column(Field('global_station', css_class='form-control form-select-sm', id=self.get_station_input_id()),
                       css_class='col-sm-12 col-md-6'),
                Column(Field('instrument', css_class='form-control form-select-sm', id=self.get_instrument_input_id()),
                       css_class='col-sm-12 col-md-6'),
                Column(Field('sample_id', css_class='form-control form-control-sm', id="id_event_sample_id_field"),
                       css_class='col-sm-6 col-md-6'),
                Column(Field('end_sample_id', css_class='form-control form-control-sm',
                             id="id_event_end_sample_id_field"), css_class='col-sm-6 col-md-6'),
                css_class="input-group input-group-sm"
            ),
            Row(
                Column(Field('flow_start', css_class='form-control form-control-sm',
                             id="id_event_flow_start_field"), css_class='col-sm-6 col-md-6'),
                Column(Field('flow_end', css_class='form-control form-control-sm',
                             id="id_event_flow_end_id_field"), css_class='col-sm-6 col-md-6'),
                Column(Field('wire_out', css_class='form-control form-control-sm',
                             id="id_event_wire_out_id_field"), css_class='col-sm-6 col-md-6'),
                Column(Field('wire_angle', css_class='form-control form-control-sm',
                             id="id_event_wire_angle_id_field"), css_class='col-sm-6 col-md-6'),
                css_class="input-group input-group-sm"
            )
        )

        if self.instance.pk is None:
            # We're going to use a '<label for="">...</lable>' element to activate this button to put the
            # button in a much more logical place for the user, this button still needs to exist and be referenced
            # by the label tag, but it can be hidden.
            submit_button = StrictButton('', id='btn_id_add_event', css_class="invisible", **apply_attrs)

            event_element = Column(Field('event_id', css_class='form-control-sm'))
            self.helper.layout.fields.insert(0,
                Row(
                    submit_button,
                    event_element,
                    css_class="input-group input-group-sm"
                ),
            )

    def save(self, commit=True):

        instance = super().save(False)

        gl_station_id = self.cleaned_data['global_station']
        gl_station = settings_models.GlobalStation.objects.get(pk=gl_station_id)
        if (n_station := models.Station.objects.filter(name__iexact=gl_station.name)).exists():
            instance.station = n_station.first()
        else:
            n_station = models.Station(name=gl_station.name)
            n_station.save()
            instance.station = n_station

        instance.save()
        return instance


class ActionForm(forms.ModelForm):
    date_time = forms.DateTimeField(widget=forms.DateTimeInput(
        attrs={'type': 'datetime-local', 'max': "9999-12-31 12:59:59",
               'value': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}))

    latitude = forms.CharField(widget=forms.TextInput())
    longitude = forms.CharField(widget=forms.TextInput())

    class Meta:
        model = models.Action
        fields = ['id', 'event', 'type', 'date_time', 'sounding', 'latitude', 'longitude', 'comment']
        widgets = {
            'event': forms.HiddenInput()
        }

    def __init__(self, event, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.helper = FormHelper(self)
        self.fields['event'].queryset = event.mission.events.all()

        # Have to disable the form tag in crispy forms because by default cirspy will add a method to the form tag #
        # that can't be removed and that plays havoc with htmx calls where the post action is on the input buttons #
        # the form tag has to surround the {% crispy <form name> %} tag and have an id matching the hx_target
        self.helper.form_tag = False

        if self.instance.pk:
            url = reverse_lazy('core:form_event_edit_action', args=(self.instance.pk,))
        else:
            url = reverse_lazy('core:form_event_add_action', args=(event.pk,))

        apply_attrs = {
            'name': 'add_action',
            'title': _('Submit'),
            'hx-post': url,
            'hx-swap': 'none'
            # 'hx-target': "#actions_form_id",
        }
        submit_button = StrictButton(load_svg('plus-square'), css_class="btn btn-primary btn-sm",
                                     **apply_attrs)
        clear_attrs = {
            'name': 'clear_action',
            'title': _('Clear'),
            'hx-get': reverse_lazy('core:form_event_add_action', args=(event.pk,)),
            'hx-swap': "none"
            # 'hx-target': "#actions_form_id",
        }
        clear_button = StrictButton(load_svg('eraser'), css_class="btn btn-secondary btn-sm",
                                    **clear_attrs)

        action_id_element = None
        if self.instance.pk:
            action_id_element = Hidden('id', self.instance.pk)

        station_name = event.station.name
        if event.actions.count() > 0:
            action = event.actions.last()
            self.fields['sounding'].initial = action.sounding
            self.fields['latitude'].initial = action.latitude
            self.fields['longitude'].initial = action.longitude
            self.fields['date_time'].widget.attrs['value'] = action.date_time.strftime("%Y-%m-%d %H:%M:%S")

        elif (global_station := settings_models.GlobalStation.objects.filter(name=station_name)).exists():
            global_station = global_station.first()
            if self.initial.get("sounding", -1) == -1:
                if global_station.sounding:
                    self.fields['sounding'].initial = global_station.sounding

            if self.initial.get("latitude", -1) == -1:
                if global_station.latitude:
                    self.fields['latitude'].initial = global_station.latitude

            if self.initial.get("longitude", -1) == -1:
                if global_station.longitude:
                    self.fields['longitude'].initial = global_station.longitude

            if (date_time := self.initial.get("date_time", -1)) != -1:
                self.fields['date_time'].widget.attrs['value'] = date_time.strftime("%Y-%m-%d %H:%M:%S")

        self.helper.layout = Layout(
            action_id_element,
            Hidden('event', event.pk),
            Row(
                Column(Field('type', css_class='form-control-sm form-select-sm', id="id_action_type_field"),
                       css_class='col-sm'),
                Column(Field('date_time', css_class='form-control-sm'), id="id_action_type_field", css_class='col-sm'),
                css_class="input-group"
            ),
            Row(
                Column(Field('latitude', css_class='form-control-sm', placeholder=_('Latitude'),
                             title=_('Latitude'), id="id_action_latitude_field"), css_class='col-sm'),
                Column(Field('longitude', css_class='form-control-sm', placeholder=_('Longitude'),
                             title=_('Longitude'), id="id_action_longitude_field"), css_class='col-sm'),
                Column(Field('sounding', css_class='form-control-sm', placeholder=_('Sounding'),
                             title=_('Sounding'), id="id_action_sounding_field"), css_class='col-sm'),
                css_class="input-group"
            ),
            Row(Column(Field('comment', css_class='form-control-sm', placeholder=_('Comment'),
                             title=_('Comment'), id="id_action_comment_field")),
                Column(clear_button, submit_button, css_class='col-auto'),
                css_class='input-group')
        )
        self.helper.form_show_labels = False

    def clean_longitude(self):
        data = self.cleaned_data['longitude']
        if re.match(r'(-{0,1}\d{1,3} \d{1,2}.*\d+( [Ee]|[Ww])*)', data):
            lon_split: [str] = data.split(' ')
            lon = float(lon_split[0])
            negative = False
            if lon < 0:
                lon *= -1
                negative = True

            if len(lon_split) > 1:
                lon += float(lon_split[1])/60
            if negative or (len(lon_split) > 2 and lon_split[2].upper() == 'W'):
                lon *= -1
            return str(np.round(lon, models.Action.longitude.field.decimal_places))

        try:
            lon = float(data)
            return str(np.round(lon, models.Action.longitude.field.decimal_places))
        except ValueError:
            message = _("Longitude is badly formatted. Must be in decimal degrees, or degree minutes with 'W' or 'E'.")
            raise forms.ValidationError(message)

    def clean_latitude(self):
        data = self.cleaned_data['latitude']
        if re.match(r'(-{0,1}\d{1,2} \d{1,2}\.*\d+( [Nn]|[Ss])*)', data):
            lat_split: [str] = data.split(' ')
            lat = float(lat_split[0])
            negative = False
            if lat < 0:
                lat *= -1
                negative = True

            if len(lat_split) > 1:
                lat += float(lat_split[1])/60
            if negative or (len(lat_split) > 2 and lat_split[2].upper() == 'S'):
                lat *= -1
            return str(np.round(lat, models.Action.latitude.field.decimal_places))

        try:
            lat = float(data)
            return str(np.round(lat, models.Action.latitude.field.decimal_places))
        except ValueError:
            message = _("Latitude is badly formatted. Must be in decimal degrees, or degree minutes with 'N' or 'S'.")
            raise forms.ValidationError(message)

    # def save(self, commit=True):
    #     instance = super().save(False)
    #     instance.save(using=self.database)
    #     return instance


class AttachmentForm(forms.ModelForm):
    class Meta:
        model = models.Attachment
        fields = ['id', 'event', 'name']
        widgets = {
            'event': forms.HiddenInput()
        }

    def __init__(self, event, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.fields['event'].queryset = event.mission.events.all()

        self.helper = FormHelper(self)

        # Have to disable the form tag in crispy forms because by default cirspy will add a method to the form tag #
        # that can't be removed and that plays havoc with htmx calls where the post action is on the input buttons #
        # the form tag has to surround the {% crispy <form name> %} tag and have an id matching the hx_target
        self.helper.form_tag = False

        if self.instance.pk:
            url = reverse_lazy('core:form_event_edit_attachment', args=(self.instance.pk,))
        else:
            url = reverse_lazy('core:form_event_add_attachment', args=(event.pk,))

        apply_attrs = {
            'name': 'add_attachment',
            'title': _('Submit'),
            'hx-post': url,
            'hx-swap': 'none'
            # 'hx-target': "#attachments_form_id",
            # 'hx-swap': "outerHTML"
        }
        submit_button = StrictButton(load_svg('plus-square'), css_class="btn btn-primary btn-sm",
                                     **apply_attrs)
        clear_attrs = {
            'name': 'clear_attachment',
            'title': _('Clear'),
            'hx-get': reverse_lazy('core:form_event_add_attachment', args=(event.pk,)),
            'hx-swap': 'none'
            # 'hx-target': "#attachments_form_id",
            # 'hx-swap': "outerHTML"
        }
        clear_button = StrictButton(load_svg('eraser'), css_class="btn btn-secondary btn-sm",
                                    **clear_attrs)

        attachment_id_element = None
        if self.instance.pk:
            attachment_id_element = Hidden('id', self.instance.pk)

        self.helper.layout = Layout(
            attachment_id_element,
            Hidden('event', event.pk),
            Row(
                Column(Field('name', css_class='form-control-sm', id="id_attachment_name_field"), css_class='col-sm'),
                Column(clear_button, submit_button, css_class='col-sm'),
                css_class="input-group"
            ),
        )
        self.helper.form_show_labels = False

    # def save(self, commit=True):
    #     instance = super().save(False)
    #     instance.save(using=self.database)
    #     return instance


def update_stations(request):
    soup = BeautifulSoup('', 'html.parser')

    if request.method == "GET":
        if request.GET.get('global_station', '-1') == '-1':

            row = soup.new_tag('div')
            row.attrs['class'] = 'container-fluid row'

            station_input = soup.new_tag('input')
            station_input.attrs['name'] = 'station'
            station_input.attrs['id'] = 'id_station'
            station_input.attrs['type'] = 'text'
            station_input.attrs['class'] = 'textinput form-control form-control-sm col'

            submit = soup.new_tag('button')
            submit.attrs['class'] = 'btn btn-primary btn-sm ms-2 col-auto'
            submit.attrs['hx-post'] = request.path
            submit.attrs['hx-target'] = '#div_id_global_station'
            submit.attrs['hx-select'] = '#div_id_global_station'
            submit.attrs['hx-swap'] = 'outerHTML'
            submit.append(BeautifulSoup(load_svg('plus-square'), 'html.parser').svg)

            row.append(station_input)
            row.append(submit)

            soup.append(row)

            return HttpResponse(soup)

        event_form = EventForm(data=request.GET)
        html = render_crispy_form(event_form)
        form_soup = BeautifulSoup(html, "html.parser")
        station_soup = form_soup.find(id="id_event_station_field")
        soup.append(station_soup)

        return HttpResponse(soup)

    elif request.method == "POST":
        mission_dict = request.POST.copy()
        if 'station' in request.POST and (new_station_name := request.POST['station'].strip()):
            if (station := settings_models.GlobalStation.objects.filter(name__iexact=new_station_name)).exists():
                mission_dict['global_station'] = station[0].id
            else:
                new_station = settings_models.GlobalStation(name=new_station_name.upper())
                new_station.save()
                mission_dict['global_station'] = new_station.pk

        mission_form = EventForm(data=mission_dict)
        html = render_crispy_form(mission_form)

        form_soup = BeautifulSoup(html, 'html.parser')
        station_select = form_soup.find(id="div_id_global_station")

        soup.append(station_select)
        return HttpResponse(soup)


def update_instruments(request):
    soup = BeautifulSoup('', 'html.parser')

    if request.method == "GET":
        if 'instrument' in request.GET and request.GET['instrument'] == '-1':

            row = soup.new_tag('div')
            row.attrs['class'] = 'container-fluid row'

            instrument_type_select = soup.new_tag('select')
            instrument_type_select.attrs['name'] = 'instrument_type'
            instrument_type_select.attrs['id'] = 'id_instrument_type'
            instrument_type_select.attrs['class'] = 'form-select form-select-sm col'

            for instrument_type in models.InstrumentType:
                instrument_type_option = soup.new_tag('option')
                instrument_type_option.attrs['value'] = str(instrument_type)
                instrument_type_option.string = instrument_type.label
                instrument_type_select.append(instrument_type_option)

            instrument_input = soup.new_tag('input')
            instrument_input.attrs['name'] = 'instrument'
            instrument_input.attrs['id'] = 'id_instrument'
            instrument_input.attrs['type'] = 'text'
            instrument_input.attrs['class'] = 'textinput form-control form-control-sm col ms-2'

            submit = soup.new_tag('button')
            submit.attrs['class'] = 'btn btn-primary btn-sm ms-2 col-auto'
            submit.attrs['hx-post'] = request.path
            submit.attrs['hx-target'] = '#div_id_instrument'
            submit.attrs['hx-select'] = '#div_id_instrument'
            submit.attrs['hx-swap'] = 'outerHTML'
            submit.append(BeautifulSoup(load_svg('plus-square'), 'html.parser').svg)

            row.append(instrument_type_select)
            row.append(instrument_input)
            row.append(submit)

            soup.append(row)

            return HttpResponse(soup)

        event_form = EventForm(data=request.GET)
        html = render_crispy_form(event_form)
        form_soup = BeautifulSoup(html, "html.parser")
        instrument_soup = form_soup.find(id="id_event_instrument_field")
        soup.append(instrument_soup)

        return HttpResponse(soup)

    elif request.method == "POST":
        mission_dict = request.POST.copy()
        instrument_name = None
        instrument_type = -1
        if 'instrument' in request.POST and request.POST['instrument'].strip():
            instrument_name = request.POST['instrument'].strip()

        if 'instrument_type' in request.POST:
            instrument_type = int(request.POST['instrument_type'])

        if instrument_name and instrument_type > 0:
            instruments = models.Instrument.objects.filter(
                name=instrument_name,
                type=instrument_type
            )
            if instruments.exists():
                mission_dict['instrument'] = instruments[0].id
            else:
                new_instrument = models.Instrument(name=instrument_name, type=instrument_type)
                new_instrument.save()
                mission_dict['instrument'] = models.Instrument.objects.get(
                    name=instrument_name,
                    type=instrument_type
                )

        mission_form = EventForm(data=mission_dict)
        html = render_crispy_form(mission_form)

        form_soup = BeautifulSoup(html, 'html.parser')
        instrument_select = form_soup.find(id="div_id_instrument")

        soup.append(instrument_select)
        return HttpResponse(soup)


# When appending a row to a table using an hx-swap-oob request the table has to have a body with an ID
# and the root element has to be the "table" tag.
#
# The response to update a table must look like:
# <table>
#   <tbody id="some_tbody_id" hx-swap-oob="beforeend">
#    <tr><td>something</td><td>to</td><td>insert</td></tr>
#   </tbody>
# </table>
def create_append_table(soup, table_body_id, tr_html):
    table = soup.new_tag("table")
    table.append(tbody := soup.new_tag("tbody", attrs={'id': table_body_id, 'hx-swap-oob': 'beforeend'}))
    tbody.append(BeautifulSoup(tr_html, 'html.parser'))

    return table


def create_replace_table(soup, tr_html):
    # wrap the row to be replaced in <table><tbody></tbody></table> tags
    table = soup.new_tag('table')
    table.append(tbody := soup.new_tag('tbody'))
    tbody.append(tr := BeautifulSoup(tr_html, 'html.parser').find('tr'))
    tr.attrs['hx-swap-oob'] = "true"

    return table


def deselect_event(soup):
    if caches['default'].touch("selected_event"):
        old_event_id = caches['default'].get('selected_event')
        old_event = models.Event.objects.get(pk=old_event_id)
        tr_html = render_block_to_string('core/partials/table_event.html', 'event_table_row', context={"event": old_event})
        table = create_replace_table(soup, tr_html)
        soup.append(table)


def add_event(request, mission_id, **kwargs):
    mission = models.Mission.objects.get(pk=mission_id)

    soup = BeautifulSoup("", "html.parser")

    # we don't need the edit and delete buttons on the EventDetail card if we're editing
    card_form = NoDeleteEditEventDetails(mission=mission)

    context = {}

    event_id = None
    if request.method == "POST":
        event_id = request.POST.get('event_id')
        event_form = EventForm(data=request.POST)

        if event_form.is_valid():
            # if the form is valid create the new event and return blank Action, Attachment *and* Event forms
            # otherwise return the event form with its issues
            event = event_form.save()
            card_form = EventDetails(event=event)

            action_form = ActionForm(event=event)
            attachments_form = AttachmentForm(event=event)
            event_form = EventForm(instance=event)
            context = {
                "event": event,
                "actionform": action_form,
                "attachmentform": attachments_form
            }

            # deselected the old event from the event selection table, select the newly created event
            deselect_event(soup)
            caches['default'].set("selected_event", event.pk, 3600)

            # create an out of band swap for the newly added event to put it in the page's event selection table
            tr_html = render_block_to_string('core/partials/table_event.html', 'event_table_row',
                                             context={'event': event, 'selected': 'true'})
            table = create_append_table(soup, 'event_table_body', tr_html)
            soup.append(table)

    if not event_id:
        # return a new Event card with a blank Event form
        # called with no event id to create a blank instance of the event_edit_form
        last_event = mission.events.last()
        event_id = last_event.event_id + 1 if last_event else 1
        initial = {'event_id': event_id, 'mission': mission.pk}
        if 'event' in kwargs:
            copy_event = mission.events.get(pk=kwargs['event'])
            initial['station'] = copy_event.station.pk
            initial['instrument'] = copy_event.instrument.pk

        event_form = EventForm(initial=initial)

    card_html = render_crispy_form(card_form)
    card_soup = BeautifulSoup(card_html, 'html.parser')

    content = card_soup.find(id=card_form.get_card_content_id())

    context['event_form'] = event_form
    form_html = render_to_string('core/partials/event_edit_form.html', context=context)
    form_soup = BeautifulSoup(form_html, 'html.parser')

    content.append(form_soup)
    soup.append(card_soup)

    return HttpResponse(soup)


def edit_event(request, event_id):
    event = models.Event.objects.get(pk=event_id)

    # we don't need the edit and delete buttons on the EventDetail card if we're editing
    class NoDeleteEditEventDetails(EventDetails):
        def get_add_button(self):
            return None

        def get_edit_button(self):
            return None

        def get_delete_button(self):
            return None

    card_form = NoDeleteEditEventDetails(event=event)

    event_form = None
    if request.method == "GET":
        event_form = EventForm(instance=event)
    elif request.method == "POST":
        event_form = EventForm(instance=event, data=request.POST)
        if event_form.is_valid():
            event_form.save()

    action_form = ActionForm(event=event)
    attachments_form = AttachmentForm(event=event)

    form_html = render_to_string('core/partials/event_edit_form.html',
                                 context={"event_form": event_form, "event": event,
                                          "actionform": action_form, "attachmentform": attachments_form})

    form_soup = BeautifulSoup(form_html, 'html.parser')

    card_html = render_crispy_form(card_form)
    card_soup = BeautifulSoup(card_html, 'html.parser')
    content = card_soup.find(id=card_form.get_card_content_id())
    content.append(form_soup)
    # soup.append(content)

    return HttpResponse(card_soup)


def selected_details(request, event_id):
    soup = BeautifulSoup('', 'html.parser')

    if caches['default'].get('selected_event', -1) != event_id:
        deselect_event(soup)

    caches['default'].set('selected_event', event_id, 3600)

    event = models.Event.objects.get(pk=event_id)
    tr_html = render_block_to_string('core/partials/table_event.html', 'event_table_row',
                                     context={"event": event, 'selected': 'true'})
    # table = create_replace_table(soup, tr_html)
    soup.append(BeautifulSoup("<table><tbody>" + tr_html + "</tbody></table>", 'html.parser'))
    response = HttpResponse(soup)
    response['Hx-Trigger'] = "event_selected"
    return response


def get_selected_event(request):

    soup = BeautifulSoup('', 'html.parser')
    event_id = caches['default'].get('selected_event', -1)
    if event_id == -1:
        card_details = EventDetails()
        card_details_html = render_crispy_form(card_details)
        card_details_soup = BeautifulSoup(card_details_html, 'html.parser')
        card = card_details_soup.find(id=card_details.get_card_id())
        soup.append(card)
        return HttpResponse(soup)

    event = models.Event.objects.get(pk=event_id)
    details_html = render_to_string("core/partials/event_details.html", context={"event": event})
    details_soup = BeautifulSoup(details_html, 'html.parser')

    card_details = EventDetails(event=event)
    card_details_html = render_crispy_form(card_details)
    card_details_soup = BeautifulSoup(card_details_html, 'html.parser')
    card = card_details_soup.find(id=card_details.get_card_id())

    card_details_content = card.find(id=card_details.get_card_content_id())
    event_details_content = details_soup.find(id='div_event_content_id')
    card_details_content.append(event_details_content)

    samples = models.MissionSampleType.objects.filter(is_sensor=False)
    bottles = event.bottles.all()
    bottle_list = {bottle: [sample.type for sample in bottle.samples.all()] for bottle in bottles}

    bottle_html = render_to_string("core/partials/table_bottle.html",
                                   context={"event": event, "sample_types": samples,
                                            "bottle_list": bottle_list})
    bottle_soup = BeautifulSoup(bottle_html, 'html.parser')

    event_details_content.append(bottle_soup.find())

    soup.append(card)
    return HttpResponse(soup)


def delete_details(request, event_id):
    event = models.Event.objects.get(pk=event_id)
    mission = event.mission

    if caches['default'].touch('selected_event'):
        caches['default'].delete('selected_event')

    event.delete()

    card = EventDetails(mission=mission)
    html = render_crispy_form(card)

    soup = BeautifulSoup(html, 'html.parser')

    card_soup = soup.find(id=card.get_card_id())
    card_soup.attrs['hx-swap-oob'] = "true"

    div_reload_event = soup.new_tag("tr")
    div_reload_event.attrs['id'] = f"event-{event_id}"
    div_reload_event.attrs['hx-target'] = f"#event-{event_id}"
    div_reload_event.attrs['hx-swap'] = "delete"

    soup.append(div_reload_event)

    response = HttpResponse(soup)
    response['HX-Trigger'] = "event_updated"
    return response


def list_action(request, event_id, editable=False):
    event = models.Event.objects.get(pk=event_id)
    context = {'event': event, 'editable': editable}
    response = HttpResponse(render_to_string('core/partials/table_action.html', context=context))
    return response


def render_action_form(soup, action_form):

    # the action form isn't wrapped in a form tag so it has to have that added
    action_form_html = render_crispy_form(action_form)
    action_form_soup = BeautifulSoup(action_form_html, 'html.parser')

    form = soup.new_tag('form', attrs={'id': 'actions_form_id', 'hx-swap-oob': 'true'})
    form.append(action_form_soup)
    soup.append(form)

    return HttpResponse(soup)


def add_action(request, event_id):
    event = models.Event.objects.get(pk=event_id)

    soup = BeautifulSoup('', 'html.parser')
    if request.method == "POST":
        action_form = ActionForm(event=event, data=request.POST)

        if action_form.is_valid():
            action = action_form.save()
            table_html = render_to_string('core/partials/table_action.html',
                                          context={'event': event, "editable": "true"})
            table_soup = BeautifulSoup(table_html, 'html.parser')
            table_soup.find(id="action_table_id").attrs['hx-swap-oob'] = 'true'
            soup.append(table_soup)
            # tr_html = render_block_to_string('core/partials/table_action.html', 'action_row_block',
            #                                  context={'database': database, 'action': action, "editable": "true"})
            # soup.append(create_append_table(soup, "tbody_id_action_table", tr_html))

            action_form = ActionForm(event=event)
    else:
        # if this is a get request we'll just send back a blank form
        action_form = ActionForm(event=event)

    return render_action_form(soup, action_form)


def edit_action(request, action_id):
    try:
        action = models.Action.objects.get(pk=action_id)
    except models.Action.DoesNotExist:
        event_id = request.POST.get('event', None)
        return add_action(request, event_id)

    soup = BeautifulSoup('', 'html.parser')
    if request.method == "POST":
        action_form = ActionForm(event=action.event, instance=action, data=request.POST)

        if action_form.is_valid():
            action = action_form.save()

            tr_html = render_block_to_string('core/partials/table_action.html', 'action_row_block',
                                             context={'action': action, "editable": "true"})
            soup.append(create_replace_table(soup, tr_html))

            action_form = ActionForm(event=action.event)
    else:
        # if this is a get request we'll just send back form populated with the object
        action_form = ActionForm(event=action.event, instance=action)

    return render_action_form(soup, action_form)


def delete_action(request, action_id):
    models.Action.objects.get(pk=action_id).delete()
    return HttpResponse()


def list_attachment(request, event_id, editable=False):
    event = models.Event.objects.get(pk=event_id)
    context = {'event': event, 'editable': editable}
    return HttpResponse(render_to_string('core/partials/table_attachment.html', context=context))


def render_attachment_form(soup, attachment_form):
    # the attachment form isn't wrapped in a form tag so it has to have that added
    attachment_form_html = render_crispy_form(attachment_form)
    attachment_form_soup = BeautifulSoup(attachment_form_html, 'html.parser')

    form = soup.new_tag('form', attrs={'id': 'attachments_form_id', 'hx-swap-oob': 'true'})
    form.append(attachment_form_soup)
    soup.append(form)

    return HttpResponse(soup)


def add_attachment(request, event_id):
    event = models.Event.objects.get(pk=event_id)
    soup = BeautifulSoup('', 'html.parser')

    if request.method == "POST":
        attachment_form = AttachmentForm(event=event, data=request.POST)

        if attachment_form.is_valid():
            attachment = attachment_form.save()

            tr_html = render_block_to_string('core/partials/table_attachment.html', 'attachments_row_block',
                                             context={"atta": attachment, "editable": "true"})
            soup.append(create_append_table(soup, "tbody_attachment_table_id", tr_html))

            attachment_form = AttachmentForm(event=event)
    else:
        # if this is a get request we'll just send back a blank form
        attachment_form = AttachmentForm(event=event)

    return render_attachment_form(soup, attachment_form)


def edit_attachment(request, attachment_id):
    attachment = models.Attachment.objects.get(pk=attachment_id)
    soup = BeautifulSoup('', 'html.parser')

    if request.method == "POST":
        attachment_form = AttachmentForm(event=attachment.event, instance=attachment, data=request.POST)

        if attachment_form.is_valid():
            attachment = attachment_form.save()

            tr_html = render_block_to_string('core/partials/table_attachment.html', 'attachments_row_block',
                                             context={"atta": attachment, "editable": "true"})
            soup.append(create_replace_table(soup, tr_html))

            attachment_form = AttachmentForm(event=attachment.event)
    else:
        # if this is a get request we'll just send back a blank form
        attachment_form = AttachmentForm(event=attachment.event, instance=attachment)

    return render_attachment_form(soup, attachment_form)


def delete_attachment(request, attachment_id):
    models.Attachment.objects.get(pk=attachment_id).delete()
    return HttpResponse()


def load_filter_log(request, event_id):
    soup = BeautifulSoup('', 'html.parser')

    if request.method == 'GET':
        attrs = {
            'alert_area_id': "div_id_card_message_area_event_details",
            # make sure not to use _ as gettext*_lazy*, only use _ as django.utils.translation.gettext
            'message': _("Loading"),
            'logger': FilterLogParser.logger_notifications.name,
            'hx-post': request.path,
            'hx-trigger': 'load',
            'hx-target': "#div_id_card_message_area_event_details"
        }
        return HttpResponse(core_forms.websocket_post_request_alert(**attrs))

    event = models.Event.objects.get(pk=event_id)
    time.sleep(2)
    file = request.FILES['filter_log']
    FilterLogParser.parse(event, file.name, file)

    soup = BeautifulSoup('', 'html.parser')
    soup.append(msg_area := soup.new_tag("div", id="div_id_card_message_area_event_details"))
    if models.FileError.objects.filter(file_name=file.name).exists():
        attrs = {
            'component_id': "div_id_card_message_area_event_details_alert",
            'message': _("Issues Processing File"),
            'alert_type': 'danger'
        }
        msg_area.append(core_forms.blank_alert(**attrs))

    # we have to clear the file input or when the user clicks the button to load the same file, nothing will happen
    input_html = (f'<input id="btn_id_filter_log_event_details" type="file" name="filter_log" accept=".xlsx" '
                  f'multiple="false" hx-get="{request.path}" hx-trigger="change" hx-swap="none" '
                  f'hx-swap-oob="true" class="invisible"/>')
    soup.append(BeautifulSoup(input_html))

    response = HttpResponse(soup)
    response['Hx-Trigger'] = "event_selected"
    return response


def load_bottle_file(request, event_id):
    soup = BeautifulSoup('', 'html.parser')

    if request.method == 'GET':
        attrs = {
            'alert_area_id': "div_id_card_message_area_event_details",
            # make sure not to use _ as gettext*_lazy*, only use _ as django.utils.translation.gettext
            'message': _("Loading"),
            'logger': FilterLogParser.logger_notifications.name,
            'hx-post': request.path,
            'hx-trigger': 'load',
            'hx-target': "#div_id_card_message_area_event_details"
        }
        return HttpResponse(core_forms.websocket_post_request_alert(**attrs))

    event = models.Event.objects.get(pk=event_id)
    time.sleep(2)
    files = request.FILES.getlist('bottle_files')

    trigger = None
    soup = BeautifulSoup('', 'html.parser')
    soup.append(msg_area := soup.new_tag("div", id="div_id_card_message_area_event_details"))
    if len(files) != 2:
        attrs = {
            'component_id': "div_id_card_message_area_event_details_alert",
            'message': _("Must select two files, one being the BTL file and the other being the ROS file"),
            'alert_type': 'danger'
        }
        msg_area.append(core_forms.blank_alert(**attrs))
    else:
        btl_file = files[0] if files[0].name.lower().endswith('.btl') else files[1]
        ros_file = files[0] if files[0].name.lower().endswith('.ros') else files[1]

        try:
            btl_input = io.StringIO(btl_file.read().decode('cp1252'))
            ros_input = io.StringIO(ros_file.read().decode('cp1252'))
            parser = FixStationParser(event=event, btl_filename=btl_file.name,
                                      btl_stream=btl_input, ros_stream=ros_input)
            parser.parse()
            trigger = "event_selected"
        except Exception as ex:
            logger.exception(ex)
            message = _("There was an issue reading the file") + f" : '{btl_file.name}' - {str(ex)}"
            attrs = {
                'component_id': "div_id_card_message_area_event_details_alert",
                'message': message,
                'alert_type': 'danger'
            }
            msg_area.append(core_forms.blank_alert(**attrs))
            err = models.FileError(mission=event.mission, file_name=btl_file, line=-1, message=message,
                                        type=models.ErrorType.event)
            err.save()
            trigger = "event_updated"

    # we have to clear the file input or when the user clicks the button to load the same file, nothing will happen
    input_html = (f'<input id="btn_id_filter_log_event_details" type="file" name="filter_log" accept=".xlsx" '
                  f'multiple="false" hx-get="{request.path}" hx-trigger="change" hx-swap="none" '
                  f'hx-swap-oob="true" class="invisible"/>')
    soup.append(BeautifulSoup(input_html))

    response = HttpResponse(soup)
    response['Hx-Trigger'] = trigger
    return response


def import_elog_events(request, mission_id, **kwargs):
    mission = models.Mission.objects.get(pk=mission_id)

    if request.method == 'GET':
        if 'csv_event' in request.GET:
            logger = event_csv.logger_notifications.name
            message = _("Processing CSV Report")
        elif 'andes_event' in request.GET:
            logger = andes.logger_notifications.name
            message = _("Processing Andes Report")
        else:
            logger = elog.logger_notifications.name
            message = _("Processing Elog")

        attrs = {
            'alert_area_id': "div_id_event_alert",
            'logger': logger,
            'hx-post': request.path,
            'hx-trigger': 'load',
            'message': message,
        }
        return HttpResponse(core_forms.websocket_post_request_alert(**attrs))


    if 'csv_event' in request.FILES:
        file = request.FILES.get('csv_event')
        event_csv.parse(mission, file.name, file)
    elif 'andes_event' in request.FILES:
        file = request.FILES.get('andes_event')
        andes.parse(mission, file.name, file)
    else:
        files = request.FILES.getlist('elog_event')
        elog.parse_files(mission, files)

    # validation.validate_mission(mission)

    # When a file is first loaded it triggers a 'selection changed' event for the forms "input" element.
    # If we don't clear the input element here and the user tries to reload the same file, nothing will happen
    # and the user will be left clicking the button endlessly wondering why it won't load the file
    event_form = render_block_to_string('core/partials/card_event_row.html', 'event_import_form',
                                        context={'mission': mission})

    soup = BeautifulSoup('', 'html.parser')

    event_form_soup = BeautifulSoup(event_form, 'html.parser')

    # Now that events are reloaded we should trigger a validation of the events
    msg_div = event_form_soup.find(id="div_id_event_message_area")
    alert_area = msg_div.find(id="div_id_event_alert")
    alert_area.attrs['hx-get'] = reverse_lazy("core:mission_events_revalidate", args=(mission.pk,))
    alert_area.attrs['hx-trigger'] = 'load'
    msg_div.attrs['hx-swap-oob'] = 'true'

    soup.append(event_form_soup)

    response = HttpResponse(soup)
    response['HX-Trigger'] = 'event_updated'
    return response


def list_events(request, mission_id, **kwargs):
    mission = models.Mission.objects.get(pk=mission_id)

    tr_html = render_to_string('core/partials/table_event.html', context={'mission': mission})

    return HttpResponse(tr_html)


event_detail_urls = [
    path(f'event/selected/<int:event_id>/', selected_details, name="form_event_selected_event"),
    path(f'event/selected/', get_selected_event, name="form_event_get_selected_event"),

    path(f'event/station/new/', update_stations, name="form_event_update_stations"),
    path(f'event/instrument/new/', update_instruments, name="form_event_update_instruments"),

    path(f'event/event/import/<int:mission_id>/', import_elog_events, name="form_event_import_events_elog"),
    path(f'event/event/list/<int:mission_id>/', list_events, name="form_event_get_events"),
    path(f'event/new/<int:mission_id>/', add_event, name="form_event_add_event"),
    path(f'event/new/<int:mission_id>/<int:event>/', add_event, name="form_event_add_event"),
    path(f'event/edit/<int:event_id>/', edit_event, name="form_event_edit_event"),
    path(f'event/delete/<int:event_id>/', delete_details, name="form_event_delete_event"),

    path(f'event/action/list/<int:event_id>/', list_action, name="form_event_list_action"),
    path(f'event/action/list/<int:event_id>/<str:editable>/', list_action, name="form_event_list_action"),
    path(f'event/action/new/<int:event_id>/', add_action, name="form_event_add_action"),
    path(f'event/action/edit/<int:action_id>/', edit_action, name="form_event_edit_action"),
    path(f'event/action/delete/<int:action_id>/', delete_action, name="form_event_delete_action"),

    path(f'event/attachment/list/<int:event_id>/', list_attachment, name="form_event_list_attachment"),
    path(f'event/attachment/list/<int:event_id>/<str:editable>/', list_attachment, name="form_event_list_attachment"),
    path(f'event/attachment/new/<int:event_id>/', add_attachment, name="form_event_add_attachment"),
    path(f'event/attachment/edit/<int:attachment_id>/', edit_attachment, name="form_event_edit_attachment"),
    path(f'event/attachment/delete/<int:attachment_id>/', delete_attachment, name="form_event_delete_attachment"),

    path(f'event/fixstation/<int:event_id>/', load_filter_log, name="form_event_fix_station_filter_log"),
    path(f'event/fixstation/btl/<int:event_id>/', load_bottle_file, name="form_event_fix_station_bottle"),
]
