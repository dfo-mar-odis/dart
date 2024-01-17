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
            'hx-post': reverse_lazy("core:form_event_delete_event", args=(self.event.pk,)),
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
            'hx-get': reverse_lazy("core:form_event_edit_event", args=(self.event.pk,)),
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
            'hx-get': reverse_lazy("core:form_event_add_event", args=(self.trip.pk,)),
            'hx-swap': 'none'
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
        div_content = Div(
            id=self.get_card_content_id(),
            hx_get=reverse_lazy("core:form_event_selected_event"),
            hx_trigger="update_selected from:body"
        )
        content_frame = Div(div_content, css_class="vertical-scrollbar")

        body.fields.append(content_frame)
        return body

    def __init__(self, trip=None, event=None, *args, **kwargs):
        self.trip = trip
        self.event = event
        if event:
            self.trip = event.trip

        super().__init__(card_name='event_details', card_title=_("Event Details"), *args, **kwargs)


class EventForm(forms.ModelForm):
    class Meta:
        model = models.Event
        fields = ['trip', 'event_id', 'station', 'instrument', 'sample_id', 'end_sample_id']

    def __init__(self, trip_id, *args, **kwargs):
        super().__init__(*args, **kwargs)

        trip = models.Trip.objects.get(pk=trip_id)
        event = trip.events.order_by('event_id').last()

        self.fields['event_id'].initial = event.event_id + 1 if event else 1

        self.helper = FormHelper(self)

        # Have to disable the form tag in crispy forms because by default cirspy will add a method to the form tag #
        # that can't be removed and that plays havoc with htmx calls where the post action is on the input buttons #
        # the form tag has to surround the {% crispy <form name> %} tag and have an id matching the hx_target
        self.helper.form_tag = False

        if self.instance.pk:
            submit_url = reverse_lazy('core:form_event_edit_event', args=(self.instance.pk,))
        else:
            submit_url = reverse_lazy('core:form_event_add_event', args=(trip_id,))

        event_element = Column(Field('event_id', css_class='form-control-sm'))
        if self.instance.pk:
            event_element = Hidden('event_id', self.instance.event_id)

        apply_attrs = {
            'name': 'add_event',
            'title': _('Submit'),
            'hx-post': submit_url,
            'hx-swap': 'none'
        }
        submit_button = StrictButton(load_svg('plus-square'), css_class="btn btn-primary btn-sm ms-2",
                                     **apply_attrs)

        self.helper.layout = Layout(
            Hidden('trip', trip_id),
            Row(
                event_element,
                Column(Field('station', css_class='form-control form-select-sm'), css_class='col-sm-12 col-md-6'),
                Column(Field('instrument', css_class='form-control form-select-sm'), css_class='col-sm-12 col-md-6'),
                Column(Field('sample_id', css_class='form-control form-control-sm'), css_class='col-sm-6 col-md-6'),
                Column(Field('end_sample_id', css_class='form-control form-control-sm'), css_class='col-sm-6 col-md-6'),
                Column(submit_button, css_class='col-sm-12 col-md align-self-center mt-3'),
                css_class="input-group input-group-sm"
            )
        )


class ActionForm(forms.ModelForm):
    date_time = forms.DateTimeField(widget=forms.DateTimeInput(
        attrs={'type': 'datetime-local', 'value': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}))

    class Meta:
        model = models.Action
        fields = ['id', 'event', 'type', 'date_time', 'latitude', 'longitude', 'comment']
        widgets = {
            'event': forms.HiddenInput()
        }

    def __init__(self, event_id, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper(self)

        # Have to disable the form tag in crispy forms because by default cirspy will add a method to the form tag #
        # that can't be removed and that plays havoc with htmx calls where the post action is on the input buttons #
        # the form tag has to surround the {% crispy <form name> %} tag and have an id matching the hx_target
        self.helper.form_tag = False

        if self.instance.pk:
            url = reverse_lazy('core:form_event_edit_action', kwargs={"action_id": self.instance.pk})
        else:
            url = reverse_lazy('core:form_event_add_action', kwargs={"event_id": event_id})

        apply_attrs = {
            'name': 'add_action',
            'title': _('Submit'),
            'hx-post': url,
            'hx-target': "#actions_form_id",
            'hx-swap': "outerHTML"
        }
        submit_button = StrictButton(load_svg('plus-square'), css_class="btn btn-primary btn-sm",
                                     **apply_attrs)
        clear_attrs = {
            'name': 'clear_action',
            'title': _('Clear'),
            'hx-get': reverse_lazy('core:form_event_add_action', args=(event_id,)),
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
            Hidden('event', event_id),
            Row(
                Column(Field('type', css_class='form-control-sm form-select-sm'), css_class='col-sm'),
                Column(Field('date_time', css_class='form-control-sm'), css_class='col-sm'),
                css_class="input-group"
            ),
            Row(
                Column(Field('latitude', css_class='form-control-sm', placeholder=_('Latitude')), css_class='col-sm'),
                Column(Field('longitude', css_class='form-control-sm', placeholder=_('Longitude')), css_class='col-sm'),
                css_class="input-group"
            ),
            Row(Column(Field('comment', css_class='form-control-sm', placeholder=_('Comment'))),
                Column(clear_button, submit_button, css_class='col-auto'),
                css_class='input-group')
        )
        self.helper.form_show_labels = False


class AttachmentForm(forms.ModelForm):
    class Meta:
        model = models.Attachment
        fields = ['id', 'event', 'name']
        widgets = {
            'event': forms.HiddenInput()
        }

    def __init__(self, event_id, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper(self)

        # Have to disable the form tag in crispy forms because by default cirspy will add a method to the form tag #
        # that can't be removed and that plays havoc with htmx calls where the post action is on the input buttons #
        # the form tag has to surround the {% crispy <form name> %} tag and have an id matching the hx_target
        self.helper.form_tag = False

        if self.instance.pk:
            url = reverse_lazy('core:form_event_edit_attachment', kwargs={"attachment_id": self.instance.pk})
        else:
            url = reverse_lazy('core:form_event_add_attachment', kwargs={"event_id": event_id})

        apply_attrs = {
            'name': 'add_attachment',
            'title': _('Submit'),
            'hx-post': url,
            'hx-target': "#attachments_form_id",
            'hx-swap': "outerHTML"
        }
        submit_button = StrictButton(load_svg('plus-square'), css_class="btn btn-primary btn-sm",
                                     **apply_attrs)
        clear_attrs = {
            'name': 'clear_attachment',
            'title': _('Clear'),
            'hx-get': reverse_lazy('core:form_event_add_attachment', args=(event_id,)),
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
            Hidden('event', event_id),
            Row(
                Column(Field('name', css_class='form-control-sm'), css_class='col-sm'),
                Column(clear_button, submit_button, css_class='col-sm'),
                css_class="input-group"
            ),
        )
        self.helper.form_show_labels = False


def make_event_row(soup, event: models.Event, selected=False):
    tr = soup.new_tag('tr')
    tr.attrs['id'] = f"event-{event.pk}"
    tr.attrs['hx-trigger'] = 'click'
    tr.attrs['hx-get'] = reverse_lazy("core:form_trip_get_events", args=(event.trip.pk, event.pk))
    tr.attrs['class'] = ""

    if selected:
        tr.attrs['class'] = tr.attrs['class'] + " selectedBg"

    if event.validation_errors.exists():
        tr.attrs['class'] = tr.attrs['class'] + " eventErr"

    td_event = soup.new_tag('td')
    td_event.string = f"{event.event_id:2d}"
    tr.append(td_event)

    td_station = soup.new_tag('td')
    td_station.string = event.station.name
    tr.append(td_station)

    td_instrument = soup.new_tag('td')
    td_instrument.string = event.instrument.name
    tr.append(td_instrument)

    return tr


def edit_event(request, **kwargs):
    event_id = kwargs['event_id']
    event = models.Event.objects.get(pk=event_id)

    soup = BeautifulSoup("", "html.parser")

    card_form = EventDetails(event=event)
    card_html = render_crispy_form(card_form)
    card_soup = BeautifulSoup(card_html, 'html.parser')

    content = card_soup.find(id=card_form.get_card_content_id())
    content.attrs['hx-swap-oob'] = 'true'

    if request.method == "GET":
        form = EventForm(trip_id=event.trip.pk, instance=event)
    if request.method == "POST":
        form = EventForm(trip_id=event.trip.pk, instance=event, data=request.POST)
        if form.is_valid():
            form.save()

    action_form = ActionForm(event_id=event.pk)
    attachments_form = AttachmentForm(event_id=event.pk)

    form_html = render_block_to_string('core/partials/event_edit_form.html', 'event_content',
                                       context={"form": form,
                                                "event": event,
                                                "actionform": action_form,
                                                "attachmentform": attachments_form})
    form_soup = BeautifulSoup(form_html, 'html.parser')

    content.append(form_soup)
    soup.append(content)

    response = HttpResponse(soup)
    response['HX-Trigger'] = "event_updated"
    return response


def add_event(request, **kwargs):
    trip_id = kwargs['trip_id']
    trip = models.Trip.objects.get(pk=trip_id)

    soup = BeautifulSoup("", "html.parser")

    card_form = EventDetails(trip=trip)
    card_html = render_crispy_form(card_form)
    card_soup = BeautifulSoup(card_html, 'html.parser')

    content = card_soup.find(id=card_form.get_card_content_id())
    content.attrs['hx-swap-oob'] = 'true'

    if request.method == "GET":

        # called with no event id to create a blank instance of the event_edit_form
        form = EventForm(trip_id=trip_id)
        form_html = render_block_to_string('core/partials/event_edit_form.html', 'event_content', context={"form": form})
        form_soup = BeautifulSoup(form_html, 'html.parser')

        content.append(form_soup)
        soup.append(content)

        response = HttpResponse(soup)
        return response
    elif request.method == "POST":
        form = EventForm(trip_id=trip_id, data=request.POST)

        if form.is_valid():
            event = form.save()

            caches['default'].set("selected_event", event.pk, 3600)

            tr = make_event_row(soup, event, True)
            tbody = soup.new_tag("tbody")
            tbody.attrs['hx-swap-oob'] = "beforeend:#event_table_body"
            tbody.append(tr)

            tr.attrs['hx-trigger'] = 'load'
            tr.attrs['hx-get'] = reverse_lazy("core:form_event_edit_event", args=(event.pk,))
            tr.attrs['hx-swap'] = "none"

            soup.append(tbody)

            response = HttpResponse(soup)
            return response

        form_html = render_block_to_string('core/partials/event_edit_form.html', 'event_content', context={"form": form})
        form_soup = BeautifulSoup(form_html, 'html.parser')
        content.append(form_soup)
        soup.append(content)

        response = HttpResponse(soup)
        return response

    return HttpResponse()


def selected_details(request, **kwargs):
    soup = BeautifulSoup('', 'html.parser')

    if not caches['default'].touch("selected_event"):
        html = render_crispy_form(EventDetails())

        return HttpResponse(html)

    event_id = caches['default'].get("selected_event")
    event = models.Event.objects.get(pk=event_id)

    details_html = render_to_string("core/partials/event_details.html", context={"event": event})
    details_soup = BeautifulSoup(details_html, 'html.parser')

    card_details = EventDetails(event=event)
    card_details_html = render_crispy_form(card_details)
    card_details_soup = BeautifulSoup(card_details_html, 'html.parser')

    button_row = card_details_soup.find(id=card_details.get_card_header_id())
    button_row.attrs['hx-swap-oob'] = 'true'

    div_content = card_details_soup.find(id=card_details.get_card_content_id())
    div_content.append(details_soup.find(id='div_event_content_id'))

    soup.append(button_row)
    soup.append(div_content)

    return HttpResponse(soup)


def event_details(request, **kwargs):
    trip_id = kwargs['trip_id']

    event_id = None
    if 'event_id' in kwargs:
        event_id = kwargs['event_id']
        event = models.Event.objects.get(pk=event_id)
        card = EventDetails(event=event)
    else:
        trip = models.Trip.objects.get(pk=trip_id)
        card = EventDetails(trip=trip)

    html = render_crispy_form(card)

    return HttpResponse(html)


def delete_details(request, **kwargs):
    event_id = kwargs['event_id']
    event = models.Event.objects.get(pk=event_id)
    trip = event.trip

    if caches['default'].touch('selected_event'):
        caches['default'].delete('selected_event')

    event.delete()

    card = EventDetails(trip=trip)
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
    response = HttpResponse(render_block_to_string('core/partials/table_action.html', 'action_table', context=context))
    return response


def render_action_form(action_form, update_actions):

    soup = BeautifulSoup('', 'html.parser')

    # the action form isn't wrapped in a form tag so it has to have that added
    action_form_html = render_crispy_form(action_form)
    action_form_soup = BeautifulSoup(action_form_html, 'html.parser')

    form = soup.new_tag('form')
    form.attrs['id'] = 'actions_form_id'
    form.append(action_form_soup)
    soup.append(form)

    response = HttpResponse(soup)
    if update_actions:
        response['HX-Trigger'] = "update_actions"
    return response


def add_action(request, **kwargs):
    event_id = kwargs['event_id']

    update_actions = False
    if request.method == "POST":
        action_form = ActionForm(event_id=event_id, data=request.POST)

        if action_form.is_valid():
            action = action_form.save()

            action_form = ActionForm(event_id=event_id)
            update_actions = True
    else:
        # if this is a get request we'll just send back a blank form
        action_form = ActionForm(event_id=event_id)

    return render_action_form(action_form, update_actions)


def edit_action(request, **kwargs):
    action_id = kwargs['action_id']
    action = models.Action.objects.get(pk=action_id)

    update_actions = False
    if request.method == "POST":
        action_form = ActionForm(event_id=action.event.pk, instance=action, data=request.POST)

        if action_form.is_valid():
            action = action_form.save()

            action_form = ActionForm(event_id=action.event.pk)
            update_actions = True
    else:
        # if this is a get request we'll just send back form populated with the object
        action_form = ActionForm(event_id=action.event.pk, instance=action)

    return render_action_form(action_form, update_actions)


def delete_action(request, **kwargs):
    action_id = kwargs['action_id']
    models.Action.objects.get(pk=action_id).delete()

    response = HttpResponse()
    response['HX-Trigger'] = "update_actions"
    return response


def list_attachment(request, event_id, editable=False, **kwargs):
    event = models.Event.objects.get(pk=event_id)
    context = {'event': event, 'editable': editable}
    response = HttpResponse(render_block_to_string('core/partials/table_attachment.html', 'attachments_table',
                                                   context=context))
    return response


def render_attachment_form(attachment_form, update_attachments):
    soup = BeautifulSoup('', 'html.parser')

    # the attachment form isn't wrapped in a form tag so it has to have that added
    attachment_form_html = render_crispy_form(attachment_form)
    attachment_form_soup = BeautifulSoup(attachment_form_html, 'html.parser')

    form = soup.new_tag('form')
    form.attrs['id'] = 'attachments_form_id'
    form.append(attachment_form_soup)
    soup.append(form)

    response = HttpResponse(soup)
    if update_attachments:
        response['HX-Trigger'] = "update_attachments"
    return response


def add_attachment(request, **kwargs):
    event_id = kwargs['event_id']

    update_attachments = False
    if request.method == "POST":
        attachment_form = AttachmentForm(event_id=event_id, data=request.POST)

        if attachment_form.is_valid():
            attachment = attachment_form.save()

            attachment_form = AttachmentForm(event_id=event_id)
            update_attachments = True
    else:
        # if this is a get request we'll just send back a blank form
        attachment_form = AttachmentForm(event_id=event_id)

    return render_attachment_form(attachment_form, update_attachments)


def edit_attachment(request, **kwargs):
    attachment_id = kwargs['attachment_id']
    attachment = models.Attachment.objects.get(pk=attachment_id)

    update_attachments = False
    if request.method == "POST":
        attachment_form = AttachmentForm(event_id=attachment.event.pk, instance=attachment, data=request.POST)

        if attachment_form.is_valid():
            attachment = attachment_form.save()

            attachment_form = AttachmentForm(event_id=attachment.event.pk)
            update_attachments = True
    else:
        # if this is a get request we'll just send back form populated with the object
        attachment_form = AttachmentForm(event_id=attachment.event.pk, instance=attachment)

    return render_attachment_form(attachment_form, update_attachments)


def delete_attachment(request, **kwargs):
    attachment_id = kwargs['attachment_id']
    models.Attachment.objects.get(pk=attachment_id).delete()

    response = HttpResponse()
    response['HX-Trigger'] = "update_attachments"
    return response


event_detail_urls = [
    path('event/details/<int:trip_id>/', event_details, name="form_event_get_details_card"),
    path('event/details/selected/', selected_details, name="form_event_selected_event"),

    path('event/details/new/<int:trip_id>/', add_event, name="form_event_add_event"),
    path('event/details/edit/<int:event_id>/', edit_event, name="form_event_edit_event"),
    path('event/details/delete/<int:event_id>/', delete_details, name="form_event_delete_event"),

    path('event/details/action/list/<int:event_id>/', list_action, name="form_event_list_action"),
    path('event/details/action/list/<int:event_id>/<str:editable>/', list_action, name="form_event_list_action"),
    path('event/details/action/new/<int:event_id>/', add_action, name="form_event_add_action"),
    path('event/details/action/edit/<int:action_id>/', edit_action, name="form_event_edit_action"),
    path('event/details/action/delete/<int:action_id>/', delete_action, name="form_event_delete_action"),

    path('event/details/attachment/list/<int:event_id>/', list_attachment, name="form_event_list_attachment"),
    path('event/details/attachment/list/<int:event_id>/<str:editable>/', list_attachment, name="form_event_list_attachment"),
    path('event/details/attachment/new/<int:event_id>/', add_attachment, name="form_event_add_attachment"),
    path('event/details/attachment/edit/<int:attachment_id>/', edit_attachment, name="form_event_edit_attachment"),
    path('event/details/attachment/delete/<int:attachment_id>/', delete_attachment, name="form_event_delete_attachment"),

]
