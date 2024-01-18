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

    def __init__(self, trip, *args, **kwargs):
        super().__init__(*args, **kwargs)

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
            submit_url = reverse_lazy('core:form_event_add_event', args=(trip.pk,))

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
            Hidden('trip', trip.pk),
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
            'hx-swap': 'none'
            # 'hx-target': "#actions_form_id",
            # 'hx-swap': "outerHTML"
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
            'hx-swap': 'none'
            # 'hx-target': "#attachments_form_id",
            # 'hx-swap': "outerHTML"
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
        tr_html = render_block_to_string('core/partials/table_event.html', 'event_table_row',
                                         context={"event": old_event})
        table = create_replace_table(soup, tr_html)
        soup.append(table)


def add_event(request, **kwargs):
    trip_id = kwargs['trip_id']
    trip = models.Trip.objects.get(pk=trip_id)

    soup = BeautifulSoup("", "html.parser")

    card_form = EventDetails(trip=trip)
    card_html = render_crispy_form(card_form)
    card_soup = BeautifulSoup(card_html, 'html.parser')

    content = card_soup.find(id=card_form.get_card_content_id())
    content.attrs['hx-swap-oob'] = 'true'

    context = {}
    if request.method == "POST":
        form = EventForm(trip=trip, data=request.POST)

        if form.is_valid():
            event = form.save()
            action_form = ActionForm(event_id=event.pk)
            attachments_form = AttachmentForm(event_id=event.pk)

            context = {"event": event, "actionform": action_form, "attachmentform": attachments_form}
            deselect_event(soup)

            caches['default'].set("selected_event", event.pk, 3600)
            tr_html = render_block_to_string('core/partials/table_event.html', 'event_table_row',
                                             context={'event': event, 'selected': 'true'})
            table = create_append_table(soup, 'event_table_body', tr_html)

            form = EventForm(trip=trip, instance=event)

            soup.append(table)
    else:
        # called with no event id to create a blank instance of the event_edit_form
        form = EventForm(trip=trip)

    context['form'] = form
    form_html = render_block_to_string('core/partials/event_edit_form.html', 'event_content',
                                       context=context)
    form_soup = BeautifulSoup(form_html, 'html.parser')
    content.append(form_soup)
    soup.append(content)

    return HttpResponse(soup)


def edit_event(request, **kwargs):
    event_id = kwargs['event_id']
    event = models.Event.objects.get(pk=event_id)

    soup = BeautifulSoup("", "html.parser")

    card_form = EventDetails(event=event)
    card_html = render_crispy_form(card_form)
    card_soup = BeautifulSoup(card_html, 'html.parser')

    content = card_soup.find(id=card_form.get_card_content_id())
    content.attrs['hx-swap-oob'] = 'true'

    form = None
    if request.method == "GET":
        form = EventForm(trip=event.trip, instance=event)
    elif request.method == "POST":
        form = EventForm(trip=event.trip, instance=event, data=request.POST)
        if form.is_valid():
            form.save()

    action_form = ActionForm(event_id=event.pk)
    attachments_form = AttachmentForm(event_id=event.pk)

    form_html = render_block_to_string('core/partials/event_edit_form.html', 'event_content',
                                       context={"form": form, "event": event, "actionform": action_form,
                                                "attachmentform": attachments_form})

    form_soup = BeautifulSoup(form_html, 'html.parser')

    content.append(form_soup)
    soup.append(content)

    return HttpResponse(soup)


def selected_details(request, **kwargs):
    event_id = kwargs['event_id']
    soup = BeautifulSoup('', 'html.parser')

    deselect_event(soup)

    caches['default'].set('selected_event', event_id, 3600)

    event = models.Event.objects.get(pk=event_id)
    tr_html = render_block_to_string('core/partials/table_event.html', 'event_table_row',
                                     context={"event": event, 'selected': 'true'})
    # table = create_replace_table(soup, tr_html)
    soup.append(BeautifulSoup("<table><tbody>" + tr_html + "</tbody></table>", 'html.parser'))

    details_html = render_to_string("core/partials/event_details.html", context={"event": event})
    details_soup = BeautifulSoup(details_html, 'html.parser')

    card_details = EventDetails(event=event)
    card_details_html = render_crispy_form(card_details)
    card_details_soup = BeautifulSoup(card_details_html, 'html.parser')
    card = card_details_soup.find(id=card_details.get_card_id())

    card.find(id=card_details.get_card_content_id()).append(details_soup.find(id='div_event_content_id'))
    card.attrs['hx-swap-oob'] = 'true'

    soup.append(card)

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


def render_action_form(soup, action_form):

    # the action form isn't wrapped in a form tag so it has to have that added
    action_form_html = render_crispy_form(action_form)
    action_form_soup = BeautifulSoup(action_form_html, 'html.parser')

    form = soup.new_tag('form', attrs={'id': 'actions_form_id', 'hx-swap-oob': 'true'})
    form.append(action_form_soup)
    soup.append(form)

    return HttpResponse(soup)


def add_action(request, **kwargs):
    event_id = kwargs['event_id']

    soup = BeautifulSoup('', 'html.parser')
    if request.method == "POST":
        action_form = ActionForm(event_id=event_id, data=request.POST)

        if action_form.is_valid():
            action = action_form.save()
            tr_html = render_block_to_string('core/partials/table_action.html', 'action_row_block',
                                             context={'action': action, "editable": "true"})
            soup.append(create_append_table(soup, "tbody_id_action_table", tr_html))

            action_form = ActionForm(event_id=event_id)
    else:
        # if this is a get request we'll just send back a blank form
        action_form = ActionForm(event_id=event_id)

    return render_action_form(soup, action_form)


def edit_action(request, **kwargs):
    action_id = kwargs['action_id']
    action = models.Action.objects.get(pk=action_id)

    soup = BeautifulSoup('', 'html.parser')
    if request.method == "POST":
        action_form = ActionForm(event_id=action.event.pk, instance=action, data=request.POST)

        if action_form.is_valid():
            action = action_form.save()

            tr_html = render_block_to_string('core/partials/table_action.html', 'action_row_block',
                                             context={'action': action, "editable": "true"})
            soup.append(create_replace_table(soup, tr_html))

            action_form = ActionForm(event_id=action.event.pk)
    else:
        # if this is a get request we'll just send back form populated with the object
        action_form = ActionForm(event_id=action.event.pk, instance=action)

    return render_action_form(soup, action_form)


def delete_action(request, **kwargs):
    action_id = kwargs['action_id']
    models.Action.objects.get(pk=action_id).delete()
    return HttpResponse()


def list_attachment(request, event_id, editable=False, **kwargs):
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


def add_attachment(request, **kwargs):
    event_id = kwargs['event_id']
    soup = BeautifulSoup('', 'html.parser')

    if request.method == "POST":
        attachment_form = AttachmentForm(event_id=event_id, data=request.POST)

        if attachment_form.is_valid():
            attachment = attachment_form.save()

            tr_html = render_block_to_string('core/partials/table_attachment.html', 'attachments_row_block',
                                             context={"atta": attachment, "editable": "true"})
            soup.append(create_append_table(soup, "tbody_attachment_table_id", tr_html))

            attachment_form = AttachmentForm(event_id=event_id)
    else:
        # if this is a get request we'll just send back a blank form
        attachment_form = AttachmentForm(event_id=event_id)

    return render_attachment_form(soup, attachment_form)


def edit_attachment(request, **kwargs):
    attachment_id = kwargs['attachment_id']
    attachment = models.Attachment.objects.get(pk=attachment_id)
    soup = BeautifulSoup('', 'html.parser')

    if request.method == "POST":
        attachment_form = AttachmentForm(event_id=attachment.event.pk, instance=attachment, data=request.POST)

        if attachment_form.is_valid():
            attachment = attachment_form.save()

            tr_html = render_block_to_string('core/partials/table_attachment.html', 'attachments_row_block',
                                             context={"atta": attachment, "editable": "true"})
            soup.append(create_replace_table(soup, tr_html))

            attachment_form = AttachmentForm(event_id=attachment.event.pk)
    else:
        # if this is a get request we'll just send back a blank form
        attachment_form = AttachmentForm(event_id=attachment.event.pk, instance=attachment)

    return render_attachment_form(soup, attachment_form)


def delete_attachment(request, **kwargs):
    attachment_id = kwargs['attachment_id']
    models.Attachment.objects.get(pk=attachment_id).delete()
    return HttpResponse()


event_detail_urls = [
    path('event/details/<int:trip_id>/', event_details, name="form_event_get_details_card"),
    path('event/details/selected/<int:event_id>/', selected_details, name="form_event_selected_event"),

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
