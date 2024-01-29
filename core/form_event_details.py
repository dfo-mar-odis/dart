import datetime

from bs4 import BeautifulSoup
from crispy_forms.bootstrap import StrictButton
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Column, Row, Hidden, Submit, Field, Layout
from crispy_forms.utils import render_crispy_form
from django import forms
from django.core.cache import caches
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import path, reverse_lazy
from django.utils.translation import gettext as _

from render_block import render_block_to_string

from core import forms as core_forms, models
from dart2.utils import load_svg


class EventDetails(core_forms.CardForm):

    event = None
    # when creating a new event a trip is required to attach the event too
    trip = None

    def get_delete_button(self):
        # url = reverse_lazy('core:mission_samples_upload_bio_chem', args=(self.mission_id,))
        button_icon = load_svg('dash-square')
        button_id = f'btn_id_delete_{self.card_name}'
        button_attrs = {
            'id': button_id,
            'name': 'delete_event',
            'title': _("Delete Event"),
            'hx-post': reverse_lazy("core:form_event_delete_event", args=(self.database, self.event.pk,)),
            'hx-confirm': _("Are you sure?"),
            'hx-swap': 'none'
        }
        button = StrictButton(button_icon, css_class='btn btn-sm btn-danger', **button_attrs)

        return button

    def get_edit_button(self):
        # url = reverse_lazy('core:mission_samples_upload_bio_chem', args=(self.mission_id,))
        button_icon = load_svg('pencil-square')
        button_id = f'btn_id_edit_{self.card_name}'
        button_attrs = {
            'id': button_id,
            'name': 'edit_event',
            'title': _("Edit Event"),
            'hx-get': reverse_lazy("core:form_event_edit_event", args=(self.database, self.event.pk,)),
            'hx-swap': 'none'
        }
        button = StrictButton(button_icon, css_class='btn btn-sm btn-secondary', **button_attrs)

        return button

    def get_add_button(self):
        # url = reverse_lazy('core:mission_samples_upload_bio_chem', args=(self.mission_id,))
        button_icon = load_svg('plus-square')
        button_id = f'btn_id_add_{self.card_name}'
        button_attrs = {
            'id': button_id,
            'name': 'new_event',
            'title': _("New Event"),
            'hx-get': reverse_lazy("core:form_event_add_event", args=(self.database, self.trip.pk,)),
            'hx-swap': 'outerHTML',
            'hx-target': f"#{self.get_card_id()}"
        }
        button = StrictButton(button_icon, css_class='btn btn-sm btn-primary', **button_attrs)

        return button

    def get_card_header(self) -> Div:
        header = super().get_card_header()

        spacer = Column(Row())

        button_row = Row(css_class="align-self-end")

        button_column = Column()
        if self.event and not self.event.files:
            button_column.fields.append(self.get_delete_button())
            spacer.fields.append(self.get_edit_button())

        if self.trip:
            spacer.fields.append(self.get_add_button())

        button_row.fields.append(button_column)
        input_column = Column(button_row, css_class="col-auto")

        header.fields[0].fields.append(spacer)
        header.fields[0].fields.append(input_column)

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

    def __init__(self, event=None, trip=None, database=None, *args, **kwargs):
        self.event = event
        self.trip = trip if trip else event.trip

        self.database = database if database else self.trip.mission.name

        super().__init__(card_name='event_details', card_title=_("Event Details"), *args, **kwargs)


class EventForm(forms.ModelForm):

    class Meta:
        model = models.Event
        fields = ['trip', 'event_id', 'station', 'instrument', 'sample_id', 'end_sample_id']

    def __init__(self, trip, database=None, *args, **kwargs):

        event = trip.events.order_by('event_id').last()
        self.database = database if database else trip.mission.name

        super().__init__(*args, **kwargs)

        self.fields['event_id'].initial = event.event_id + 1 if event else 1
        self.fields['trip'].queryset = trip.mission.trips.all()
        self.helper = FormHelper(self)

        # Have to disable the form tag in crispy forms because by default cirspy will add a method to the form tag #
        # that can't be removed and that plays havoc with htmx calls where the post action is on the input buttons #
        # the form tag has to surround the {% crispy <form name> %} tag and have an id matching the hx_target
        self.helper.form_tag = False

        apply_attrs = {
            'name': 'add_event',
            'title': _('Submit'),
            'hx-swap': 'none'
        }
        if self.instance.pk:
            submit_url = reverse_lazy('core:form_event_edit_event', args=(self.database, self.instance.pk,))
            apply_attrs['hx-post'] = submit_url
        else:
            # When adding an event we'll swap the whole card the form appears on.
            submit_url = reverse_lazy('core:form_event_add_event', args=(self.database, trip.pk,))
            apply_attrs['hx-post'] = submit_url
            apply_attrs['hx-swap'] = "outerHTML"
            apply_attrs['hx-target'] = "#div_id_card_event_details"

        event_element = Column(Field('event_id', css_class='form-control-sm'))
        if self.instance.pk:
            event_element = Hidden('event_id', self.instance.event_id)

        submit_button = StrictButton(load_svg('plus-square'), css_class="btn btn-primary btn-sm ms-2",
                                     **apply_attrs)

        stations = models.Station.objects.using(self.database).all().order_by("name")
        self.fields['station'].queryset = stations

        self.fields['station'].choices = [(None, '--------')]
        self.fields['station'].choices += [(st.id, st) for st in stations]
        self.fields['station'].choices.append((-1, '-- New --'))

        self.fields['station'].widget.attrs["hx-swap"] = 'outerHTML'
        self.fields['station'].widget.attrs["hx-trigger"] = 'change'
        self.fields['station'].widget.attrs["hx-get"] = reverse_lazy('core:form_event_update_stations',
                                                                     args=(self.database,))

        instruments = models.Instrument.objects.using(self.database).all().order_by("name")
        self.fields['instrument'].queryset = instruments

        self.fields['instrument'].choices = [(None, '--------')]
        self.fields['instrument'].choices += [(ins.id, ins) for ins in instruments]
        self.fields['instrument'].choices.append((-1, '-- New --'))

        self.fields['instrument'].widget.attrs["hx-swap"] = 'outerHTML'
        self.fields['instrument'].widget.attrs["hx-trigger"] = 'change'
        self.fields['instrument'].widget.attrs["hx-get"] = reverse_lazy('core:form_event_update_instruments',
                                                                        args=(self.database,))

        self.helper.layout = Layout(
            Hidden('trip', trip.pk),
            Row(
                event_element,
                Column(Field('station', css_class='form-control form-select-sm', id="id_event_station_field"),
                       css_class='col-sm-12 col-md-6'),
                Column(Field('instrument', css_class='form-control form-select-sm', id="id_event_instrument_field"),
                       css_class='col-sm-12 col-md-6'),
                Column(Field('sample_id', css_class='form-control form-control-sm', id="id_event_sample_id_field"),
                       css_class='col-sm-6 col-md-6'),
                Column(Field('end_sample_id', css_class='form-control form-control-sm',
                             id="id_event_end_sample_id_field"), css_class='col-sm-6 col-md-6'),
                Column(submit_button, css_class='col-sm-12 col-md align-self-center mt-3'),
                css_class="input-group input-group-sm"
            )
        )

    def save(self, commit=True):
        instance = super().save(False)
        instance.save(using=self.database)

        return instance


class ActionForm(forms.ModelForm):
    date_time = forms.DateTimeField(widget=forms.DateTimeInput(
        attrs={'type': 'datetime-local', 'value': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}))

    class Meta:
        model = models.Action
        fields = ['id', 'event', 'type', 'date_time', 'latitude', 'longitude', 'comment']
        widgets = {
            'event': forms.HiddenInput()
        }

    def __init__(self, event, database=None, *args, **kwargs):
        self.database = database if database else event.trip.mission.name

        super().__init__(*args, **kwargs)

        self.helper = FormHelper(self)
        self.fields['event'].queryset = event.trip.events.all()

        # Have to disable the form tag in crispy forms because by default cirspy will add a method to the form tag #
        # that can't be removed and that plays havoc with htmx calls where the post action is on the input buttons #
        # the form tag has to surround the {% crispy <form name> %} tag and have an id matching the hx_target
        self.helper.form_tag = False

        if self.instance.pk:
            url = reverse_lazy('core:form_event_edit_action', args=(self.database, self.instance.pk))
        else:
            url = reverse_lazy('core:form_event_add_action', args=(self.database, event.pk))

        apply_attrs = {
            'name': 'add_action',
            'title': _('Submit'),
            'hx-post': url,
            'hx-swap': 'none'
            # 'hx-target': "#actions_form_id",
            # 'hx-swap': "outerHTML"
        }
        submit_button = StrictButton(load_svg('plus-square'), css_class="btn btn-primary btn-sm",
                                     **apply_attrs)
        clear_attrs = {
            'name': 'clear_action',
            'title': _('Clear'),
            'hx-get': reverse_lazy('core:form_event_add_action', args=(self.database, event.pk,)),
            'hx-target': "#actions_form_id",
            'hx-swap': "outerHTML"
        }
        clear_button = StrictButton(load_svg('eraser'), css_class="btn btn-secondary btn-sm",
                                    **clear_attrs)

        action_id_element = None
        if self.instance.pk:
            action_id_element = Hidden('id', self.instance.pk)

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
                             id="id_action_latitude_field"), css_class='col-sm'),
                Column(Field('longitude', css_class='form-control-sm', placeholder=_('Longitude'),
                             id="id_action_longitude_field"), css_class='col-sm'),
                css_class="input-group"
            ),
            Row(Column(Field('comment', css_class='form-control-sm', placeholder=_('Comment'),
                             id="id_action_comment_field")),
                Column(clear_button, submit_button, css_class='col-auto'),
                css_class='input-group')
        )
        self.helper.form_show_labels = False

    def save(self, commit=True):
        instance = super().save(False)
        instance.save(using=self.database)
        return instance


class AttachmentForm(forms.ModelForm):
    class Meta:
        model = models.Attachment
        fields = ['id', 'event', 'name']
        widgets = {
            'event': forms.HiddenInput()
        }

    def __init__(self, event, database=None, *args, **kwargs):

        self.database = database if database else event.trip.mission.name

        super().__init__(*args, **kwargs)

        self.fields['event'].queryset = event.trip.events.all()

        self.helper = FormHelper(self)

        # Have to disable the form tag in crispy forms because by default cirspy will add a method to the form tag #
        # that can't be removed and that plays havoc with htmx calls where the post action is on the input buttons #
        # the form tag has to surround the {% crispy <form name> %} tag and have an id matching the hx_target
        self.helper.form_tag = False

        if self.instance.pk:
            url = reverse_lazy('core:form_event_edit_attachment', args=(self.database, self.instance.pk))
        else:
            url = reverse_lazy('core:form_event_add_attachment', args=(self.database, event.pk,))

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
            'hx-get': reverse_lazy('core:form_event_add_attachment', args=(self.database, event.pk,)),
            'hx-target': "#attachments_form_id",
            'hx-swap': "outerHTML"
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

    def save(self, commit=True):
        instance = super().save(False)
        instance.save(using=self.database)
        return instance


def update_stations(request, database, **kwargs):
    mission = models.Mission.objects.using(database).first()
    soup = BeautifulSoup('', 'html.parser')

    if request.method == "GET":
        if 'station' in request.GET and request.GET['station'] == '-1':

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
            submit.attrs['hx-target'] = '#div_id_station'
            submit.attrs['hx-select'] = '#div_id_station'
            submit.attrs['hx-swap'] = 'outerHTML'
            submit.append(BeautifulSoup(load_svg('plus-square'), 'html.parser').svg)

            row.append(station_input)
            row.append(submit)

            soup.append(row)

            return HttpResponse(soup)

        event_form = EventForm(trip=mission.trips.first(), data=request.GET)
        html = render_crispy_form(event_form)
        form_soup = BeautifulSoup(html, "html.parser")
        station_soup = form_soup.find(id="id_event_station_field")
        soup.append(station_soup)

        return HttpResponse(soup)

    elif request.method == "POST":
        mission_dict = request.POST.copy()
        if 'station' in request.POST and (new_station_name := request.POST['station'].strip()):
            if (station := models.Station.objects.using(database).filter(mission=mission, name=new_station_name)).exists():
                mission_dict['station'] = station[0].id
            else:
                new_station = models.Station(mission=mission, name=new_station_name)
                new_station.save(using=database)
                mission_dict['station'] = models.Station.objects.using(database).get(mission=mission,
                                                                                     name=new_station_name)

        mission_form = EventForm(trip=mission.trips.first(), data=mission_dict)
        html = render_crispy_form(mission_form)

        form_soup = BeautifulSoup(html, 'html.parser')
        station_select = form_soup.find(id="div_id_station")

        soup.append(station_select)
        return HttpResponse(soup)


def update_instruments(request, database, **kwargs):
    mission = models.Mission.objects.using(database).first()
    soup = BeautifulSoup('', 'html.parser')

    if request.method == "GET":
        if 'instrument' in request.GET and request.GET['instrument'] == '-1':

            row = soup.new_tag('div')
            row.attrs['class'] = 'container-fluid row'

            station_input = soup.new_tag('input')
            station_input.attrs['name'] = 'instrument'
            station_input.attrs['id'] = 'id_instrument'
            station_input.attrs['type'] = 'text'
            station_input.attrs['class'] = 'textinput form-control form-control-sm col'

            station_type_select = soup.new_tag('select')
            station_type_select.attrs['name'] = 'instrument_type'
            station_type_select.attrs['id'] = 'id_instrument_type'
            station_type_select.attrs['class'] = 'form-select form-select-sm col'

            for type in models.InstrumentType:
                station_type_option = soup.new_tag('option')
                station_type_option.attrs['value'] = type
                station_type_option.string = type.label
                station_type_select.append(station_type_option)

            submit = soup.new_tag('button')
            submit.attrs['class'] = 'btn btn-primary btn-sm ms-2 col-auto'
            submit.attrs['hx-post'] = request.path
            submit.attrs['hx-target'] = '#div_id_instrument'
            submit.attrs['hx-select'] = '#div_id_instrument'
            submit.attrs['hx-swap'] = 'outerHTML'
            submit.append(BeautifulSoup(load_svg('plus-square'), 'html.parser').svg)

            row.append(station_input)
            row.append(station_type_select)
            row.append(submit)

            soup.append(row)

            return HttpResponse(soup)

        event_form = EventForm(trip=mission.trips.first(), data=request.GET)
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
            instruments = models.Instrument.objects.using(database).filter(
                mission=mission,
                name=instrument_name,
                type=instrument_type
            )
            if instruments.exists():
                mission_dict['instrument'] = instruments[0].id
            else:
                new_instrument = models.Instrument(mission=mission, name=instrument_name, type=instrument_type)
                new_instrument.save(using=database)
                mission_dict['instrument'] = models.Instrument.objects.using(database).get(
                    mission=mission,
                    name=instrument_name,
                    type=instrument_type
                )

        mission_form = EventForm(trip=mission.trips.first(), data=mission_dict)
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


def deselect_event(soup, database):
    if caches['default'].touch("selected_event"):
        old_event_id = caches['default'].get('selected_event')
        old_event = models.Event.objects.using(database).get(pk=old_event_id)
        tr_html = render_block_to_string('core/partials/table_event.html', 'event_table_row',
                                         context={"database": database, "event": old_event})
        table = create_replace_table(soup, tr_html)
        soup.append(table)


def add_event(request, database, trip_id, **kwargs):
    trip = models.Trip.objects.using(database).get(pk=trip_id)

    soup = BeautifulSoup("", "html.parser")

    card_form = EventDetails(trip=trip)
    card_html = render_crispy_form(card_form)
    card_soup = BeautifulSoup(card_html, 'html.parser')

    content = card_soup.find(id=card_form.get_card_content_id())

    context = {"database": database}

    if request.method == "POST":
        event_form = EventForm(trip=trip, database=database, data=request.POST)

        if event_form.is_valid():
            # if the form is valid create the new event and return blank Action, Attachment *and* Event forms
            # otherwise return the event form with it's issues
            event = event_form.save()
            action_form = ActionForm(event=event)
            attachments_form = AttachmentForm(event=event)
            event_form = EventForm(trip=trip, database=database, instance=event)
            context = {
                "database": database,
                "event": event,
                "actionform": action_form,
                "attachmentform": attachments_form
            }

            # deselected the old event from the event selection table, select the newly created event
            deselect_event(soup, database)
            caches['default'].set("selected_event", event.pk, 3600)

            # create an out of band swap for the newly added event to put it in the page's event selection table
            tr_html = render_block_to_string('core/partials/table_event.html', 'event_table_row',
                                             context={'database': database, 'event': event, 'selected': 'true'})
            table = create_append_table(soup, 'event_table_body', tr_html)
            soup.append(table)
    else:
        # return a new Event card with a blank Event form
        # called with no event id to create a blank instance of the event_edit_form
        event_form = EventForm(trip=trip, database=database)

    context['event_form'] = event_form
    form_html = render_to_string('core/partials/event_edit_form.html', context=context)
    form_soup = BeautifulSoup(form_html, 'html.parser')
    content.append(form_soup)
    soup.append(card_soup)

    return HttpResponse(soup)


def edit_event(request, database, event_id, **kwargs):
    event = models.Event.objects.using(database).get(pk=event_id)

    soup = BeautifulSoup("", "html.parser")

    card_form = EventDetails(event=event, database=database)
    card_html = render_crispy_form(card_form)
    card_soup = BeautifulSoup(card_html, 'html.parser')

    content = card_soup.find(id=card_form.get_card_content_id())
    content.attrs['hx-swap-oob'] = 'true'

    event_form = None
    if request.method == "GET":
        event_form = EventForm(trip=event.trip, database=database, instance=event)
    elif request.method == "POST":
        event_form = EventForm(trip=event.trip, database=database, instance=event, data=request.POST)
        if event_form.is_valid():
            event_form.save()

    action_form = ActionForm(event=event, database=database)
    attachments_form = AttachmentForm(event=event, database=database)

    form_html = render_to_string('core/partials/event_edit_form.html',
                                 context={'database': database, "event_form": event_form, "event": event,
                                          "actionform": action_form, "attachmentform": attachments_form})

    form_soup = BeautifulSoup(form_html, 'html.parser')

    content.append(form_soup)
    soup.append(content)

    return HttpResponse(soup)


def selected_details(request, database, event_id, **kwargs):
    soup = BeautifulSoup('', 'html.parser')

    deselect_event(soup, database)

    caches['default'].set('selected_event', event_id, 3600)

    event = models.Event.objects.using(database).get(pk=event_id)
    tr_html = render_block_to_string('core/partials/table_event.html', 'event_table_row',
                                     context={"database": database, "event": event, 'selected': 'true'})
    # table = create_replace_table(soup, tr_html)
    soup.append(BeautifulSoup("<table><tbody>" + tr_html + "</tbody></table>", 'html.parser'))

    details_html = render_to_string("core/partials/event_details.html", context={"database": database, "event": event})
    details_soup = BeautifulSoup(details_html, 'html.parser')

    card_details = EventDetails(event=event, database=database)
    card_details_html = render_crispy_form(card_details)
    card_details_soup = BeautifulSoup(card_details_html, 'html.parser')
    card = card_details_soup.find(id=card_details.get_card_id())

    card.find(id=card_details.get_card_content_id()).append(details_soup.find(id='div_event_content_id'))
    card.attrs['hx-swap-oob'] = 'true'

    soup.append(card)

    return HttpResponse(soup)


def delete_details(request, database, event_id, **kwargs):
    event = models.Event.objects.using(database).get(pk=event_id)
    trip = event.trip

    if caches['default'].touch('selected_event'):
        caches['default'].delete('selected_event')

    event.delete()

    card = EventDetails(trip=trip, database=database)
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


def list_action(request, database, event_id, editable=False):
    event = models.Event.objects.get(pk=event_id)
    context = {'database': database, 'event': event, 'editable': editable}
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


def add_action(request, database, event_id, **kwargs):
    event = models.Event.objects.using(database).get(pk=event_id)

    soup = BeautifulSoup('', 'html.parser')
    if request.method == "POST":
        action_form = ActionForm(event=event, database=database, data=request.POST)

        if action_form.is_valid():
            action = action_form.save()
            tr_html = render_block_to_string('core/partials/table_action.html', 'action_row_block',
                                             context={'database': database, 'action': action, "editable": "true"})
            soup.append(create_append_table(soup, "tbody_id_action_table", tr_html))

            action_form = ActionForm(event=event, database=database)
    else:
        # if this is a get request we'll just send back a blank form
        action_form = ActionForm(event=event, database=database)

    return render_action_form(soup, action_form)


def edit_action(request, database, action_id, **kwargs):
    action = models.Action.objects.using(database).get(pk=action_id)

    soup = BeautifulSoup('', 'html.parser')
    if request.method == "POST":
        action_form = ActionForm(event=action.event, database=database, instance=action, data=request.POST)

        if action_form.is_valid():
            action = action_form.save()

            tr_html = render_block_to_string('core/partials/table_action.html', 'action_row_block',
                                             context={'database': database, 'action': action, "editable": "true"})
            soup.append(create_replace_table(soup, tr_html))

            action_form = ActionForm(event=action.event, database=database)
    else:
        # if this is a get request we'll just send back form populated with the object
        action_form = ActionForm(event=action.event, database=database, instance=action)

    return render_action_form(soup, action_form)


def delete_action(request, database, action_id, **kwargs):
    models.Action.objects.using(database).get(pk=action_id).delete()
    return HttpResponse()


def list_attachment(request, database, event_id, editable=False, **kwargs):
    event = models.Event.objects.get(pk=event_id)
    context = {'database': database, 'event': event, 'editable': editable}
    return HttpResponse(render_to_string('core/partials/table_attachment.html', context=context))


def render_attachment_form(soup, attachment_form):
    # the attachment form isn't wrapped in a form tag so it has to have that added
    attachment_form_html = render_crispy_form(attachment_form)
    attachment_form_soup = BeautifulSoup(attachment_form_html, 'html.parser')

    form = soup.new_tag('form', attrs={'id': 'attachments_form_id', 'hx-swap-oob': 'true'})
    form.append(attachment_form_soup)
    soup.append(form)

    return HttpResponse(soup)


def add_attachment(request, database, event_id, **kwargs):
    event = models.Event.objects.using(database).get(pk=event_id)
    soup = BeautifulSoup('', 'html.parser')

    if request.method == "POST":
        attachment_form = AttachmentForm(event=event, database=database, data=request.POST)

        if attachment_form.is_valid():
            attachment = attachment_form.save()

            tr_html = render_block_to_string('core/partials/table_attachment.html', 'attachments_row_block',
                                             context={"database": database, "atta": attachment, "editable": "true"})
            soup.append(create_append_table(soup, "tbody_attachment_table_id", tr_html))

            attachment_form = AttachmentForm(event=event, database=database)
    else:
        # if this is a get request we'll just send back a blank form
        attachment_form = AttachmentForm(event=event, database=database)

    return render_attachment_form(soup, attachment_form)


def edit_attachment(request, database, attachment_id, **kwargs):
    attachment = models.Attachment.objects.using(database).get(pk=attachment_id)
    soup = BeautifulSoup('', 'html.parser')

    if request.method == "POST":
        attachment_form = AttachmentForm(event=attachment.event, database=database,
                                         instance=attachment, data=request.POST)

        if attachment_form.is_valid():
            attachment = attachment_form.save()

            tr_html = render_block_to_string('core/partials/table_attachment.html', 'attachments_row_block',
                                             context={"database": database, "atta": attachment, "editable": "true"})
            soup.append(create_replace_table(soup, tr_html))

            attachment_form = AttachmentForm(event=attachment.event, database=database)
    else:
        # if this is a get request we'll just send back a blank form
        attachment_form = AttachmentForm(event=attachment.event, database=database, instance=attachment)

    return render_attachment_form(soup, attachment_form)


def delete_attachment(request, database, attachment_id, **kwargs):
    models.Attachment.objects.using(database).get(pk=attachment_id).delete()
    return HttpResponse()


url_prefix = "<str:database>/event"
event_detail_urls = [
    path(f'{url_prefix}/selected/<int:event_id>/', selected_details, name="form_event_selected_event"),

    path(f'{url_prefix}/station/new/', update_stations, name="form_event_update_stations"),
    path(f'{url_prefix}/instrument/new/', update_instruments, name="form_event_update_instruments"),

    path(f'{url_prefix}/new/<int:trip_id>/', add_event, name="form_event_add_event"),
    path(f'{url_prefix}/edit/<int:event_id>/', edit_event, name="form_event_edit_event"),
    path(f'{url_prefix}/delete/<int:event_id>/', delete_details, name="form_event_delete_event"),

    path(f'{url_prefix}/action/list/<int:event_id>/', list_action, name="form_event_list_action"),
    path(f'{url_prefix}/action/list/<int:event_id>/<str:editable>/', list_action, name="form_event_list_action"),
    path(f'{url_prefix}/action/new/<int:event_id>/', add_action, name="form_event_add_action"),
    path(f'{url_prefix}/action/edit/<int:action_id>/', edit_action, name="form_event_edit_action"),
    path(f'{url_prefix}/action/delete/<int:action_id>/', delete_action, name="form_event_delete_action"),

    path(f'{url_prefix}/attachment/list/<int:event_id>/', list_attachment, name="form_event_list_attachment"),
    path(f'{url_prefix}/attachment/list/<int:event_id>/<str:editable>/', list_attachment, name="form_event_list_attachment"),
    path(f'{url_prefix}/attachment/new/<int:event_id>/', add_attachment, name="form_event_add_attachment"),
    path(f'{url_prefix}/attachment/edit/<int:attachment_id>/', edit_attachment, name="form_event_edit_attachment"),
    path(f'{url_prefix}/attachment/delete/<int:attachment_id>/', delete_attachment, name="form_event_delete_attachment"),

]
