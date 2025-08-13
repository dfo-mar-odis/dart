import os

from bs4 import BeautifulSoup
from crispy_forms.bootstrap import StrictButton
from crispy_forms.layout import Hidden, Field, Column, Div, Row, HTML
from crispy_forms.utils import render_crispy_form
from django import forms
from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils.translation import gettext as _

from config.utils import load_svg
from core import forms as core_forms

SAMPLES_CARD_NAME = "samples"
SAMPLES_CARD_ID = f"div_id_card_{SAMPLES_CARD_NAME}"

class SampleFilterForm(core_forms.CollapsableCardForm):
    class SampleFilterIdBuilder(core_forms.CollapsableCardForm.CollapsableCardIDBuilder):
        def get_input_hidden_refresh_id(self):
            return f"input_id_hidden_refresh_{self.card_name}"

        def get_input_event_id(self):
            return f"input_id_event_{self.card_name}"

        def get_input_sample_id_start_id(self):
            return f"input_id_sample_id_start_{self.card_name}"

        def get_input_sample_id_end_id(self):
            return f"input_id_sample_id_end_{self.card_name}"

        def get_button_clear_filters_id(self):
            return f"btn_id_clear_filters_{self.card_name}"

    @staticmethod
    def get_id_builder_class():
        return SampleFilterForm.SampleFilterIdBuilder

    help_text = _("This form allows samples to be filtered.\n\n"
                  "When filtered, opperations will only be applied to the visible set of samples.\n"
                  "When unfiltered, opperations will be applied to all samples.")

    event = forms.ChoiceField(required=False)

    sample_id_start = forms.IntegerField(label=_("Start ID"), required=False)
    sample_id_end = forms.IntegerField(label=_("End ID"), required=False)

    # Using this to remove large gaps around input fields crispy forms puts in
    field_template = os.path.join(settings.TEMPLATE_DIR, "field.html")

    def get_input_hidden_refresh_id(self):
        return self.get_id_builder().get_input_hidden_refresh_id()

    def get_input_event_id(self):
        return self.get_id_builder().get_input_event_id()

    def get_input_sample_id_start_id(self):
        return self.get_id_builder().get_input_sample_id_start_id()

    def get_input_sample_id_end_id(self):
        return self.get_id_builder().get_input_sample_id_end_id()

    def get_button_clear_filters_id(self):
        return self.get_id_builder().get_button_clear_filters_id()

    def get_input_hidden_refresh_input(self):
        attrs = self.htmx_attributes.copy()
        attrs['hx-trigger'] = "reload_samples from:body"
        input =  Hidden(value='', name='refresh_samples', id=self.get_input_hidden_refresh_id(), **attrs)
        return input

    def get_input_event(self):
        attrs = self.htmx_attributes.copy()
        attrs['hx-trigger'] = "change"
        return Field('event', name='event', id=self.get_input_event_id(),
                     css_class="form-select-sm", template=self.field_template, **attrs)

    def get_input_sample_id_start(self):
        attrs = self.htmx_attributes.copy()
        attrs['hx-trigger'] = "keyup changed delay:500ms"
        return Field('sample_id_start', name='sample_id_start', id=self.get_input_sample_id_start_id(),
                     css_class="form-control-sm", template=self.field_template, **attrs)

    def get_input_sample_id_end(self):
        attrs = self.htmx_attributes.copy()
        attrs['hx-trigger'] = "keyup changed delay:500ms"
        return Field('sample_id_end', name='sample_id_end', id=self.get_input_sample_id_end_id(),
                     css_class="form-control-sm", template=self.field_template, **attrs)

    def get_button_clear_filters(self):
        attrs = {
            'title': _("Clear Filters"),
            'hx-swap': "none",
            'hx-get': self.get_clear_filters_url()
        }
        button = StrictButton(
            load_svg('eraser'),
            css_class='btn btn-sm btn-secondary',
            id=self.get_button_clear_filters_id(),
            **attrs
        )
        return button

    def get_card_header(self):
        header = super().get_card_header()
        spacer_row = Column(
            css_class="col"
        )

        button_row = Column(
            self.get_button_clear_filters(),
            css_class="col-auto"
        )

        header.fields[0].fields.append(spacer_row)
        header.fields[0].fields.append(button_row)

        return header

    def get_card_body(self) -> Div:
        body = super().get_card_body()

        body.append(self.get_input_hidden_refresh_input())

        helptext = _("Select an event for its range of samples if they exist for this mission sample type or use"
                     "the start and end ID fields for a custom range of the samples. If no ending ID is provided only "
                     "samples matching the start ID field will be returned.")
        sample_row = Row(
            Row(
                Column(self.get_input_event()),
                Column(self.get_input_sample_id_start()),
                Column(self.get_input_sample_id_end())
            ),
            Row(
                HTML(f'<small class="form-text">{helptext}</small>')
            ),
            css_class='mb-3'
        )
        body.append(sample_row)

        return body

    def get_samples_card_update_url(self):
        return None

    def get_clear_filters_url(self):
        return None

    # the samples_card_id is the card that gets updated whenever the filter form changes
    def __init__(self, *args, **kwargs):
        self.htmx_attributes = {
            # The target is a card that's expected to be returned by the url
            'hx-target': f"#{SAMPLES_CARD_ID}",
            'hx-post': self.get_samples_card_update_url(),
            'hx-swap': 'outerHTML'
        }
        super().__init__(*args, card_title=_("Sample Filter"), **kwargs)

        self.fields['event'].choices = [(None, "------")]
        if hasattr(self, 'events') and self.events:
            self.fields['event'].choices += [(event.pk, f'{event.event_id} : {event.station} [{event.sample_id} - {event.end_sample_id}]') for event in self.events]


def get_samples_card(card_title, show_scrollbar=True) -> BeautifulSoup:
    """
    Creates a card layout for displaying samples with optional vertical scrolling.

    Args:
        card_title (str): The title of the card to display.
        show_scrollbar (bool): Whether to include a vertical scrollbar in the card body. Defaults to True.

    Returns:
        BeautifulSoup: A BeautifulSoup object representing the card layout.

    Behavior:
        - Renders a card placeholder template with the given title.
        - Modifies the card body to remove default margins and optionally adds a vertical scrollbar.
        - Ensures the card is styled consistently with the rest of the application.
    """

    context = {
        'card_title': card_title,
        'card_name': SAMPLES_CARD_NAME
    }
    card_html = render_to_string('core/partials/card_placeholder.html', context)
    card_soup = BeautifulSoup(card_html, 'html.parser')

    card_body = card_soup.find(id=f"div_id_card_body_{context['card_name']}")
    card_body.attrs['class'] = ''  # We're clearing the class to get rid of the card-body class' margins
    if show_scrollbar:
        card_body.attrs['class'] = 'vertical-scrollbar'

    return card_soup

def clear_filters(form: SampleFilterForm):
    """
    Clears the filters applied to the sample filter form and updates the corresponding card layout.

    Args:
        form (SampleFilterForm): The form instance containing the filter fields and card configuration.

    Returns:
        HttpResponse: An HTTP response containing the updated HTML for the filter card.

    Behavior:
        - Renders the form using crispy forms and parses it into a BeautifulSoup object.
        - Updates the card attributes to enable HTMX-based asynchronous updates.
        - Sets the card to reload a samples from the `get_samples_card_update_url` method when swapped into the DOM.
        - Ensures the card is swapped in the DOM using HTMX's `outerHTML` swap strategy.
    """
    crispy = render_crispy_form(form)
    soup = BeautifulSoup(crispy, 'html.parser')

    card = soup.find(id=form.get_card_id())
    card.attrs['hx-swap'] = 'outerHTML'
    card.attrs['hx-swap-oob'] = 'true'
    card.attrs['hx-get'] = form.get_samples_card_update_url()
    card.attrs['hx-trigger'] = 'load'
    card.attrs['hx-target'] = f"#{SAMPLES_CARD_ID}"

    response = HttpResponse(soup)
    return response


def list_samples(request, queryset, card_title, delete_samples_url, process_samples_func, **kwargs) -> BeautifulSoup:
    """
    Generates a paginated list of samples and renders them inside a card layout.

    Args:
        request (HttpRequest): The HTTP request object containing GET parameters for pagination.
        queryset (QuerySet): A Django QuerySet containing the samples to be listed.
        card_title (str): The title of the card to display the samples.
        delete_samples_url (str): The URL to handle the deletion of visible samples.
        process_samples_func (callable): A function to process the queryset and return a BeautifulSoup object representing the table rows.
        **kwargs: Additional keyword arguments to pass to the `process_samples_func`.

    Returns:
        The Samples card or table rows.

    Behavior:
        - Paginates the `queryset` based on the `page` parameter in the request.
        - If the `queryset` is empty, returns a card with a "No Samples found" message.
        - If `page` is greater than 0, returns only the new rows for infinite scrolling.
        - Adds styles and attributes to the table for consistency and interactivity.
        - Includes a delete button for visible samples if the page is the first one.
    """

    if not queryset.exists():
        return empty_sample_card(card_title)

    page = int(request.GET.get('page', 0) or 0)
    page_limit = 100
    page_start = page_limit * page

    pages = queryset.count()/page_limit

    queryset = queryset[page_start:(page_start + page_limit)]
    table_soup = process_samples_func(queryset, **kwargs)

    # add styles to the table so it's consistent with the rest of the application
    table = table_soup.find('table')
    table.attrs['class'] = 'table table-striped table-sm horizontal-scrollbar'

    # we don't need the head of the table, just the body. It's a waste of bandwidth to send it.
    header = table.find('thead')
    header.attrs['class'] = 'sticky-top'

    tr = header.find("tr")
    tr.attrs['style'] = 'text-align: center;'

    table_body = table.find('tbody')

    if pages > 1 and queryset.count() >= page_limit:
        last_tr = table_body.find_all('tr')[-1]

        last_tr.attrs['hx-target'] = 'this'
        last_tr.attrs['hx-trigger'] = 'intersect once'
        last_tr.attrs['hx-get'] = request.path + f"?page={page + 1}"
        last_tr.attrs['hx-swap'] = "afterend"

    # finally, align all text in each column to the center of the cell
    tds = table.find_all('td')
    for td in tds:
        td['class'] = 'text-center text-nowrap'

    # If the page is <= zero then we're constructing the table for the first time and we'll want to encapsulate
    # the whole table in a card with the mission sample type details as the cart title.
    #
    # if page is > 0 then the user is scrolling down and we only want to return new rows to be swapped into
    # the table.
    if page > 0:
        return table_soup.find('tbody').findAll('tr', recursive=False)

    card_soup = get_samples_card(card_title, show_scrollbar=(pages > 1 or queryset.count() > 11))

    card_body = card_soup.find(id=f"div_id_card_body_{SAMPLES_CARD_NAME}")
    card_body.append(table)

    attrs = {
        'id': f'btn_id_delete_samples_{SAMPLES_CARD_NAME}',
        'class': 'btn btn-sm btn-danger',
        'title': _("Delete Visible Samples"),
        'name': 'delete_samples',
        'hx-confirm': _("Are you sure?"),
        'hx-swap': "none",
        'hx-post': delete_samples_url
    }

    button_row = card_soup.find(id=f"div_id_card_title_buttons_{SAMPLES_CARD_NAME}")
    button_row.append(btn_delete := card_soup.new_tag('button', attrs=attrs))

    icon = BeautifulSoup(load_svg('dash-square'), 'html.parser').svg
    btn_delete.append(icon)

    return card_soup


def empty_sample_card(card_title) -> BeautifulSoup:
    # if there are no more bottles then we stop loading, otherwise weird things happen
    card_soup = get_samples_card(card_title, show_scrollbar=False)

    card_body = card_soup.find(id=SAMPLES_CARD_ID)
    card_body.append(info := card_soup.new_tag('div', attrs={'class': 'alert alert-info'}))
    info.string = _("No Samples found")
    return card_soup