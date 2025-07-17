import os

from crispy_forms.bootstrap import StrictButton
from crispy_forms.layout import Hidden, Field, Column, Div, Row, HTML
from django import forms
from django.conf import settings
from django.utils.translation import gettext as _

from config.utils import load_svg
from core import forms as core_forms


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

    help_text = _("This form allows samples to be filtered. By default all samples are shown and any operations, "
                  "like delete, will be applied to all samples.\n\nWhen filtered, opperations will only be applied to "
                  "the visible set of samples.")

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
    def __init__(self, samples_card_id, *args, **kwargs):
        self.htmx_attributes = {
            # The target is a card that's expected to be returned by the url
            'hx-target': f"#{samples_card_id}",
            'hx-post': self.get_samples_card_update_url(),
            'hx-swap': 'outerHTML'
        }
        super().__init__(*args, **kwargs)

        self.fields['event'].choices = [(None, "------")]
        if hasattr(self, 'events') and self.events:
            self.fields['event'].choices += [(event.pk, f'{event.event_id} : {event.station} [{event.sample_id} - {event.end_sample_id}]') for event in self.events]
