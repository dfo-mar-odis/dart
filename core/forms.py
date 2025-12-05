import re

import time

from bs4 import BeautifulSoup
from crispy_forms.bootstrap import StrictButton
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, LayoutObject, Hidden, Row, Column, Field, Div, HTML, flatatt

from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse_lazy
from django.utils.translation import gettext as _

from config.utils import load_svg

from . import models

from bio_tables import models as bio_models
from settingsdb import models as settings_models
from .consumer import LoggerConsumer


class NoWhiteSpaceCharField(forms.CharField):
    def validate(self, value):
        super().validate(value)
        if re.search(r"\s", value):
            raise ValidationError("Field may not contain whitespaces")


class AlertArea(Div):
    """
    A crispy_forms Div subclass for rendering Bootstrap alert areas with dynamic content and HTMX attributes.
    Usage: alert = AlertArea(id='my_alert').set_status('success').set_message('Operation successful')
    """

    def __init__(self, *args, css_id=None, css_class=None, **kwargs):
        """
        Initialize the AlertArea with an optional ID and CSS class.

        Args:
            id (str, optional): Base ID for the alert and message elements.
            css_class (str, optional): Additional CSS classes for the alert.
            *args: Additional positional arguments for the parent Div.
            **kwargs: Additional keyword arguments for the parent Div.
        """
        css_class = css_class or 'visibility-hidden'
        super().__init__(*args, css_id=css_id, css_class=css_class, **kwargs)

    def get_attributes(self):
        """
        Parse flat_attrs string into a dictionary, splitting on spaces but ignoring those inside quotes.

        Returns:
            dict: Dictionary of attribute key-value pairs.
        """
        # Split on spaces not inside quotes (handles both " and ')
        parts = re.split(r'\s+(?=(?:[^\'"]*[\'"][^\'"]*[\'"])*[^\'"]*$)', self.flat_attrs.strip())
        attrs = {v[0]: re.sub(r'["\']', '', v[1]) for v in [p.split('=', 1) for p in parts if '=' in p]}
        return attrs

    def get_attribute(self, key, default=None) -> str|None:
        """
        Retrieve a specific attribute value from the parsed attributes dictionary.

        Args:
            key (str): The attribute key to retrieve.
            default (str, optional): Default value if key is not found.

        Returns:
            str or None: The attribute value or default.
        """
        return self.get_attributes().get(key, default)

    def set_attribute(self, key, value) -> "AlertArea":
        """
        Set or update an attribute in flat_attrs and return self for chaining.

        Args:
            key (str): The attribute key.
            value (str): The attribute value.

        Returns:
            AlertArea: Self for method chaining.
        """
        attrs = self.get_attributes()
        attrs[key] = value
        self.flat_attrs = flatatt(attrs)
        return self

    def append_attribute(self, key, value) -> "AlertArea":
        """
        Append a value to an existing attribute (comma-separated) or set it if not present.

        Args:
            key (str): The attribute key.
            value (str): The value to append.

        Returns:
            AlertArea: Self for method chaining.
        """
        attrs = self.get_attributes()
        if key in attrs:
            attrs[key] = ", ".join([value, attrs[key].split(', ')])
        else:
            attrs[key] = value
        self.flat_attrs = flatatt(attrs)
        return self

    def set_status(self, status: str) -> "AlertArea":
        """
        Set bootstrap alert status (e.g. 'danger', 'success') and return self for chaining.

        Args:
            status (str): The Bootstrap status (e.g., 'danger', 'success').

        Returns:
            AlertArea: Self for method chaining.
        """
        existing = (self.css_class or "").strip()
        # Remove any previous 'bg-...' tokens then add the new one
        parts = [p for p in existing.split() if not p.startswith("bg-")]
        parts.extend([f"bg-{status}-subtle"])
        self.css_class = " ".join(parts)
        return self


class StatusAlert(BeautifulSoup):
    component_id = None
    alert_container = None

    def set_type(self, alert_type):
        self.alert_container.attrs["class"] = f"alert alert-{alert_type}"

    def set_socket(self, socket_name):
        self.alert_container.attrs["hx-ext"] = "ws"
        self.alert_container.attrs["ws-connect"] = f'/ws/notifications/{socket_name}/{self.component_id}/'

    def get_message_container(self):
        return self.alert_message

    def set_message(self, message):
        self.alert_message.string = message

    def include_close_button(self):
        self.message_row.append(col:=self.new_tag("div", attrs={"class": "col-auto"}))
        col.append(remove_btn:=self.new_tag("button", attrs={"class": "btn btn-sm btn-secondary", "type": "button"}))
        remove_btn.attrs['onclick'] = f"document.getElementById(`{self.component_id}_container`).remove();"
        icon = BeautifulSoup(load_svg('x-square'), 'html.parser').svg
        remove_btn.append(icon)

    def include_progress_bar(self):
        # create a progress bar to give the user something to stare at while they wait.
        progress_bar = self.new_tag("div")
        progress_bar.attrs = {
            'class': "progress-bar progress-bar-striped progress-bar-animated",
            'role': "progressbar",
            'style': "width: 100%"
        }
        progress_bar_div = self.new_tag("div", attrs={'class': "progress", 'id': 'progress_bar'})
        progress_bar_div.append(progress_bar)

        self.alert_container.append(progress_bar_div)

    def is_socket_connected(self, socket_name):
        is_open = False
        for count in range(5):
            if is_open := LoggerConsumer.is_socket_open(socket_name, self.component_id):
                break
            time.sleep(0.5)

        return is_open

    def __init__(self, component_id, message="connecting...", alert_type="info"):
        super().__init__("", "html.parser")

        self.component_id = component_id

        self.alert_container = self.new_tag("div", attrs={"id": f"{component_id}_container"})
        self.message_row = self.new_tag("div", attrs={"class": "row"})

        self.alert_message = self.new_tag("div", attrs={"id": component_id})

        self.alert_container.append(self.message_row)
        self.message_row.append(col:=self.new_tag("div", attrs={"class": "col"}))
        col.append(self.alert_message)

        self.append(self.alert_container)
        self.set_message(message)
        self.set_type(alert_type)


class CardForm(forms.Form):

    class CardFormIdBuilder:
        def get_card_id(self):
            return f'div_id_card_{self.card_name}'

        def get_card_header_id(self):
            return f'div_id_card_header_{self.card_name}'

        def get_card_title_id(self):
            return f'div_id_card_title_{self.card_name}'

        def get_alert_area_id(self):
            return f"div_id_card_alert_{self.card_name}"

        def get_card_body_id(self):
            return f'div_id_card_body_{self.card_name}'

        def __init__(self, card_name, *args, **kwargs):
            self.card_name = card_name

    alert_area_class = AlertArea
    id_builder = None

    card_title = None
    card_title_class = None
    card_header_class = None
    card_name = None
    help_text = None

    alert_area = None

    @staticmethod
    def get_id_builder_class():
        return CardForm.CardFormIdBuilder

    def get_id_builder(self):
        if self.id_builder is None:
            self.id_builder = self.get_id_builder_class()(self.card_name)

        return self.id_builder

    # the card name is frequently used in uniquely naming elements for a card
    def get_card_name(self):
        return self.card_name

    def get_card_id(self):
        return self.get_id_builder().get_card_id()

    def get_card_header_id(self):
        return self.get_id_builder().get_card_header_id()

    def get_card_title_id(self):
        return self.get_id_builder().get_card_title_id()

    def get_alert_area_id(self):
        return self.get_id_builder().get_alert_area_id()

    def get_card_body_id(self):
        return self.get_id_builder().get_card_body_id()

    def get_card_title_class(self):
        return 'card-title' + (f" {self.card_title_class}" if self.card_title_class else "")

    def get_help_text(self):
        return self.help_text

    def get_card_title(self):
        title_string = ""
        if (help_text:=self.get_help_text()) is not None:
            svg = BeautifulSoup(load_svg('question-circle'), 'html.parser').svg
            title_string = f'<span title="{help_text}" class="me-2">{svg}</span>'

        title_string += f'<span id="{self.get_card_title_id()}" class="h6">{self.card_title}</span>'
        title = HTML(title_string) if self.card_title else None
        return Div(title, css_class=self.get_card_title_class())

    def get_alert_area(self) -> AlertArea:
        if self.alert_area:
            return self.alert_area

        self.alert_area = self.alert_area_class(css_id=self.get_alert_area_id())
        return self.alert_area

    def get_card_header_class(self):
        return "card-header" + (f" {self.card_header_class}" if self.card_header_class else "")

    def get_card_header(self, header_attributes=None) -> Div:
        if header_attributes is None:
            header_attributes = {}

        header_row = Row(**header_attributes)

        header = Div(header_row, id=self.get_card_header_id(), css_class=self.get_card_header_class())
        title_column = Div(self.get_card_title(), css_class="col-auto align-self-end")
        header_row.append(title_column)

        return header

    def get_card_body(self) -> Div:
        body = Div(css_class='card-body', id=self.get_card_body_id())
        return body

    def get_card_class(self):
        return f'card mb-2'

    def get_card(self, attrs: dict = None) -> Div:

        card = Div(css_class=self.get_card_class(), id=self.get_card_id())
        if attrs:
            card = Div(css_class=self.get_card_class(), id=self.get_card_id(), **attrs)

        card.fields.append(self.get_card_header())
        card.fields.append(self.get_alert_area())
        card.fields.append(self.get_card_body())
        return card

    def __init__(self, *args, **kwargs):
        if 'card_name' not in kwargs:
            raise IndexError("Missing 'card_name' required to identify form components")

        self.card_name = kwargs.pop('card_name')

        if 'card_title' in kwargs:
            self.card_title = kwargs.pop('card_title')

        if 'card_class' in kwargs:
            self.card_header_class = kwargs.pop('card_class')

        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False

        self.helper.layout = Layout(self.get_card())

    def set_title(self, title):
        self.card_title = title


class CollapsableCardForm(CardForm):

    class CollapsableCardIDBuilder(CardForm.CardFormIdBuilder):

        def get_collapsable_card_body_id(self):
            return f"div_id_card_collapse_{self.card_name}"

    collapsed = False

    @staticmethod
    def get_id_builder_class():
        return CollapsableCardForm.CollapsableCardIDBuilder

    def get_collapsable_card_body_id(self):
        return self.get_id_builder().get_collapsable_card_body_id()

    def get_card_header(self, header_attributes: dict = None) -> Div:

        header = super().get_card_header(header_attributes)

        button_id = f'button_id_collapse_{self.card_name}'
        button_attrs = {
            'id': button_id,
            'data_bs_toggle': "collapse",
            'href': f"#{self.get_id_builder().get_collapsable_card_body_id()}",
            'aria_expanded': 'false' if self.collapsed else 'true'
        }
        icon = load_svg('caret-down')
        button = StrictButton(icon, css_class="btn btn-light btn-sm collapsed col-auto", **button_attrs)

        header.fields[0].fields.insert(0, button)

        return header

    def get_collapsable_card_body(self):
        inner_body = self.get_card_body()
        css = "collapse" + ("" if self.collapsed else " show")
        body = Div(inner_body, css_class=css, id=self.get_collapsable_card_body_id())
        return body

    def get_card(self):
        card = Div(
            self.get_card_header(),
            self.get_alert_area(),
            self.get_collapsable_card_body(),
            css_class='card mb-2',
            id=self.get_card_id()
        )

        return card

    def __init__(self, collapsed=True, *args, **kwargs):
        self.collapsed = collapsed

        super().__init__(*args, **kwargs)


class MissionSearchForm(forms.Form):
    mission = forms.IntegerField(label=_("Mission"), required=True)
    event_start = forms.IntegerField(label=_("Event Start"), required=False,
                                     help_text=_("Finds a single event unless Event End is specified"))
    event_end = forms.IntegerField(label=_("Event End"), required=False)

    station = forms.ChoiceField(label=_("Station"), required=False)
    instrument = forms.ChoiceField(label=_("Instrument"), required=False)
    action_type = forms.ChoiceField(label=_("Action"), required=False)

    sample_start = forms.IntegerField(label=_("Sample Start"), help_text=_("Finds events containing a single "
                                                                           "Sample ID"), required=False)
    sample_end = forms.IntegerField(label=_("Sample end"), required=False,
                                    help_text=_("Used with Sample start to Find events containing a range of "
                                                "Sample IDs"))

    class Meta:
        model = models.Event
        fields = ['mission', 'event_start', 'event_end', 'station', 'instrument', 'action_type',
                  'sample_start', 'sample_end']

    def __init__(self, *args, **kwargs):
        STATION_CHOICES = [(None, '--------')] + [(s.pk, s) for s in models.Station.objects.all()]
        INSTRUMENT_CHOICES = [(None, '--------')] + [(i.pk, i) for i in models.Instrument.objects.all()]
        ACTION_TYPE_CHOICES = [(None, '--------')] + [(a[0], a[1]) for a in models.ActionType.choices]

        super().__init__(*args, **kwargs)

        self.fields['station'].choices = STATION_CHOICES
        self.fields['instrument'].choices = INSTRUMENT_CHOICES
        self.fields['action_type'].choices = ACTION_TYPE_CHOICES

        if 'initial' in kwargs and 'mission' in kwargs['initial']:
            self.fields['mission'].initial = kwargs['initial']['mission']

        self.helper = FormHelper(self)
        self.helper.form_tag = False

        self.helper.layout = Layout(
            Hidden('mission', 'mission'),
            Div(
                Row(
                    Column(Field('event_start', css_class='form-control form-control-sm')),
                    Column(Field('event_end', css_class='form-control form-control-sm')),
                    css_class="justify-content-between"
                ),
                Row(
                    Column(Field('sample_start', css_class='form-control form-control-sm'), css_class="col-6"),
                    Column(Field('sample_end', css_class='form-control form-control-sm'), css_class="col-6"),
                ),
                Row(
                    Column(Field('station', css_class='form-control form-select-sm'), css_class="col-4"),
                    Column(Field('instrument', css_class='form-control form-select-sm'), css_class="col-4"),
                    Column(Field('action_type', css_class='form-control form-select-sm'), css_class="col-4"),
                )
            )
        )


class SampleTypeForm(forms.ModelForm):

    datatype_filter = forms.CharField(label=_("Datatype Filter"), required=False,
                                      help_text=_("Filter the Datatype dropdown based on key terms"))

    class Meta:
        model = settings_models.GlobalSampleType
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if 'initial' in kwargs and 'datatype_filter' in kwargs['initial']:
            data_type_filter = kwargs['initial']['datatype_filter'].split(" ")
            queryset = bio_models.BCDataType.objects.all()
            for term in data_type_filter:
                queryset = queryset.filter(description__icontains=term)

            self.fields['datatype'].choices = [(dt.data_type_seq, dt) for dt in queryset]

        self.helper = FormHelper(self)
        self.helper.form_tag = False

        datatype_filter = Field('datatype_filter')
        datatype_filter.attrs = {
            "hx-get": reverse_lazy('core:sample_type_new'),
            "hx-target": "#div_id_datatype",
            "hx-select": "#div_id_datatype",  # natural id that crispy-forms assigns to the datatype div
            "hx-trigger": "keyup changed delay:1s",
            "hx-swap": 'outerHTML',
            'class': "form-control form-control-sm"
        }

        name_row = Row(
            Hidden('priority', '1'),
            Column(Field('short_name', css_class='form-control form-control-sm'), css_class='col'),
            Column(Field('long_name', css_class='form-control form-control-sm'), css_class='col'),
            css_class='flex-fill'
        )
        if self.instance.pk:
            name_row.fields.insert(0, Hidden('id', self.instance.pk))

        self.helper.layout = Layout(
            Div(
                name_row,
                Row(
                    Column(datatype_filter, css_class='col-12'), css_class=''
                ),
                Row(
                    Column(Field('datatype', css_class='form-control form-select-sm'), css_class='col-12'),
                    css_class="flex-fill"
                ),
                id="div_id_sample_type_holder_form"
            )
        )


class BottleSelection(forms.Form):
    bottle_dir = forms.FileField(label=_("Bottle Directory"), required=True)
    file_name = forms.MultipleChoiceField(label=_("File"), required=False)

    class Meta:
        fields = ['bottle_dir', 'file_name']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if 'initial' in kwargs and 'file_name' in kwargs['initial']:
            self.fields['file_name'].choices = ((f, f,) for f in kwargs['initial']['file_name'])

        self.fields['file_name'].widget.attrs = {'size': 12}
        self.helper = FormHelper(self)
        # self.helper.form_tag = False
        self.helper.attrs = {
            "id": "form_id_ctd_bottle_upload",
            "hx_get": reverse_lazy("core:mission_samples_sample_upload_ctd", args=(kwargs['initial']['mission'],)),
            'hx_target': '#div_id_bottle_upload_btn_row',
        }

        url = reverse_lazy("core:mission_samples_sample_upload_ctd", args=(kwargs['initial']['mission'],))
        url += f"?bottle_dir={kwargs['initial']['bottle_dir']}"
        all_attrs = {
            'title':  _('Show Unloaded'),
            'name': 'show_some',
            'hx_get': url,
            'hx_target': "#form_id_ctd_bottle_upload",
            'hx_swap': 'outerHTML'
        }
        icon = load_svg('eye-slash')

        if 'show_some' in kwargs['initial'] and kwargs['initial']['show_some']:
            all_attrs['title'] = _('Show All')
            all_attrs['name'] = 'show_all'
            icon = load_svg('eye')

        all_button = StrictButton(icon, css_class="btn btn-primary btn-sm", **all_attrs)

        submit_button = StrictButton(load_svg('arrow-up-square'), css_class="btn btn-primary btn-sm", type='input',
                                     title=_("Load Selected"))
        self.helper.layout = Layout(
            Row(Column(submit_button, css_class='col'), Column(all_button, css_class='col-auto'),
                id='div_id_bottle_upload_btn_row'),
            Hidden('bottle_dir', kwargs['initial']['bottle_dir']),
            Row(Column(Field('file_name')), css_class='mt-2'),
        )
        self.helper.form_show_labels = False


def blank_alert(component_id, message, **kwargs):
    alert_type = kwargs.pop('alert_type') if 'alert_type' in kwargs else 'info'

    # return a loading alert that calls this methods post request
    # Let's make some soup
    soup = BeautifulSoup('', "html.parser")

    root_div = soup.new_tag("div", attrs={'id': component_id})
    soup.append(root_div)

    # creates an alert dialog with an animated progress bar to let the user know we're saving or loading something
    # type should be a bootstrap css type, (danger, info, warning, success, etc.)

    # create an alert area saying we're loading
    alert_div = soup.new_tag("div", attrs={'id': f'{component_id}_alert', 'class': f"alert alert-{alert_type}"})
    alert_msg = soup.new_tag("div", attrs={'id': f'{component_id}_message'})
    lines = message.split('\n')
    for line in lines:
        alert_msg.append(msg_div := soup.new_tag("div"))
        msg_div.string = line
    # alert_msg.string = message

    alert_div.append(alert_msg)

    root_div.attrs = {
        'id': component_id,
    }

    root_div.append(alert_div)

    for attr, val in kwargs.items():
        root_div.attrs[attr] = val

    soup.append(root_div)

    return soup


def save_load_component(component_id, message, progress_bar=True, **kwargs):

    soup = blank_alert(component_id, message, **kwargs)
    root_div = soup.find(id=component_id)

    if progress_bar:
        alert_div = root_div.find(id=f'{component_id}_alert')
        # create a progress bar to give the user something to stare at while they wait.
        progress_bar = soup.new_tag("div")
        progress_bar.attrs = {
            'class': "progress-bar progress-bar-striped progress-bar-animated",
            'role': "progressbar",
            'style': "width: 100%"
        }
        progress_bar_div = soup.new_tag("div", attrs={'class': "progress", 'id': 'progress_bar'})
        progress_bar_div.append(progress_bar)

        alert_div.append(progress_bar_div)

    return soup


# attrs = {
#     'alert_area_id': "",
#     # make sure not to use _ as gettext*_lazy*, only use _ as django.utils.translation.gettext
#     'message': '',
#     'logger': '',
#     'hx-post': url,
#     'hx-trigger': 'load'
# }
def websocket_post_request_alert(alert_area_id, logger, message, swap_oob=True, **kwargs):
    """
    Generates a Bootstrap alert HTML component with a progress bar and websocket live status updates.

    Args:
        alert_area_id (str): The HTML element ID where the alert will be rendered.
        logger (str): Logger or identifier for the websocket notification channel.
        message (str): The initial message to display in the alert.
        swap_oob (bool): indicate if this should be an out-of-band swap into an existing element
        **kwargs: Additional HTML attributes for the alert component.

    Returns:
        BeautifulSoup: A soup object containing the alert HTML, ready for rendering.

    The alert includes a websocket connection for real-time status updates and is designed
    to be swapped into the page using HTMX out-of-band swapping.

    You CANNOT use django.utils.translation.gettext_lazy() here because it provides a reference
    to a translation, not the actual translation string.
    """
    component_id = f"{alert_area_id}_alert"
    soup = BeautifulSoup("", 'html.parser')
    attrs = {}
    if swap_oob:
        attrs['hx-swap-oob'] = 'true'

    soup.append(div := soup.new_tag('div', id=alert_area_id, attrs=attrs))

    ext_args = {
        'hx-ext': 'ws',
        'ws-connect': f"/ws/notifications/{logger}/{component_id}_status/"
    }
    alert_soup = save_load_component(component_id, message, **ext_args, **kwargs)

    # add a message area for websockets
    msg_div = alert_soup.find(id=f"{component_id}_message")
    msg_div.string = ""

    msg_div_status = soup.new_tag('div')
    msg_div_status['id'] = f'{component_id}_status'
    msg_div_status.string = message
    msg_div.append(msg_div_status)

    div.append(alert_soup)

    return soup


# convenience method to convert html attributes from a string into a dictionary
def get_crispy_element_attributes(element):
    attr_dict = {k: v.replace("\"", "") for k, v in [attr.split('=') for attr in element.flat_attrs.strip().split(" ")]}
    return attr_dict
