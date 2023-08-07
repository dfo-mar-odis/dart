import datetime
import re

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Hidden, Row, Column, Submit, Button, Field, Reset, HTML
from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from django.urls import reverse_lazy
from django.utils.translation import gettext as _

from . import models


class NoWhiteSpaceCharField(forms.CharField):
    def validate(self, value):
        super().validate(value)
        if re.search(r"\s", value):
            raise ValidationError("Field may not contain whitespaces")


class MissionSettingsForm(forms.ModelForm):
    name = NoWhiteSpaceCharField(max_length=50, label="Mission Name", required=True)
    # elog_dir = forms.CharField(max_length=255, label="Elog Directory", required=False,
    #                            help_text="Folder location of Elog *.log files")
    # bottle_dir = forms.CharField(max_length=255, label="CTD Bottle Directory", required=False,
    #                              help_text="Folder location of Elog *.BTL files")
    mission_descriptor = NoWhiteSpaceCharField(max_length=50, required=False)

    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'value': datetime.datetime.now().strftime("%Y-%m-%d")}))
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'value': datetime.datetime.now().strftime("%Y-%m-%d")}))

    class Meta:
        model = models.Mission
        fields = ['name', 'start_date', 'end_date', 'lead_scientist',
                  'protocol', 'platform', 'geographic_region', 'mission_descriptor', 'collector_comments',
                  'more_comments', 'data_manager_comments', 'biochem_table', 'data_center']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_show_labels = True
        self.fields['geographic_region'].label = False
        self.fields['geographic_region'].widget.attrs["hx-target"] = '#div_id_geographic_region'
        self.fields['geographic_region'].widget.attrs["hx-trigger"] = 'region_added from:body'
        self.fields['geographic_region'].widget.attrs["hx-get"] = reverse_lazy('core:hx_update_regions')

    def geographic_region_choices(form):
        regions = models.GeographicRegion.objects.all()
        return regions

    def clean_end_date(self):
        end_date = self.cleaned_data['end_date']
        start_date = self.cleaned_data['start_date']
        if end_date < start_date:
            raise forms.ValidationError("The end date must occur after the start date")

        return end_date


class ActionForm(forms.ModelForm):
    date_time = forms.DateTimeField(widget=forms.DateTimeInput(
        attrs={'type': 'datetime-local', 'value': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}))

    class Meta:
        model = models.Action
        fields = ['id', 'event', 'type', 'date_time', 'latitude', 'longitude', 'comment']
        widgets = {
            'event': forms.HiddenInput()
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper(self)

        # Have to disable the form tag in crispy forms because by default cirspy will add a method to the form tag #
        # that can't be removed and that plays havoc with htmx calls where the post action is on the input buttons #
        # the form tag has to surround the {% crispy <form name> %} tag and have an id matching the hx_target
        self.helper.form_tag = False

        event_pk = self.initial['event'] if 'event' in self.initial else args[0]['event']
        submit_button = Submit('submit', '+', css_class='btn-sm', hx_target="#actions_form_id",
                               hx_post=reverse_lazy('core:hx_action_new'),
                               )
        clear_button = Submit('reset', '0', css_class='btn btn-sm btn-secondary', hx_target='#actions_form_id',
                              hx_get=reverse_lazy('core:hx_action_update', args=(event_pk,)))
        action_id_element = None
        if self.instance.pk:
            action_id_element = Hidden('id', self.instance.pk)

        self.helper.layout = Layout(
            action_id_element,
            Hidden('event', event_pk),
            Row(
                Column(Field('type', css_class='form-control-sm'), css_class='col-sm'),
                Column(Field('date_time', css_class='form-control-sm'), css_class='col-sm'),
                Column(Field('latitude', css_class='form-control-sm', placeholder=_('Latitude')), css_class='col-sm'),
                Column(Field('longitude', css_class='form-control-sm', placeholder=_('Longitude')), css_class='col-sm'),
                Column(submit_button, clear_button, css_class='col-sm'),
                css_class="input-group"
            ),
            Row(Column(Field('comment', css_class='form-control-sm', placeholder=_('Comment'))), css_class='input-group')
        )
        self.helper.form_show_labels = False


class AttachmentForm(forms.ModelForm):

    class Meta:
        model = models.InstrumentSensor
        fields = ['id', 'event', 'name']
        widgets = {
            'event': forms.HiddenInput()
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper(self)

        # Have to disable the form tag in crispy forms because by default cirspy will add a method to the form tag #
        # that can't be removed and that plays havoc with htmx calls where the post action is on the input buttons #
        # the form tag has to surround the {% crispy <form name> %} tag and have an id matching the hx_target
        self.helper.form_tag = False

        event_pk = self.initial['event'] if 'event' in self.initial else args[0]['event']
        submit_button = Submit('submit', '+', css_class='btn-sm', hx_target="#attachments_form_id",
                               hx_post=reverse_lazy('core:hx_attachment_new'),
                               )
        clear_button = Submit('reset', '0', css_class='btn btn-sm btn-secondary', hx_target='#attachments_form_id',
                              hx_get=reverse_lazy('core:hx_attachment_update', args=(event_pk,)))
        attachment_id_element = None
        if self.instance.pk:
            attachment_id_element = Hidden('id', self.instance.pk)

        self.helper.layout = Layout(
            attachment_id_element,
            Hidden('event', event_pk),
            Row(
                Column(Field('name', css_class='form-control-sm'), css_class='col-sm'),
                Column(submit_button, clear_button, css_class='col-sm'),
                css_class="input-group"
            ),
        )
        self.helper.form_show_labels = False


class EventForm(forms.ModelForm):
    initial_fields = ['mission', 'event_id', 'station', 'instrument', 'sample_id', 'end_sample_id']

    class Meta:
        model = models.Event
        fields = ['mission', 'event_id', 'station', 'instrument', 'sample_id', 'end_sample_id']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if 'initial' in kwargs and 'mission' in kwargs['initial']:
            mission_id = kwargs['initial']['mission']
            mission = models.Mission.objects.get(pk=mission_id)
            event = mission.events.order_by('event_id').last()
            self.fields['event_id'].initial = event.event_id + 1 if event else 1

        self.helper = FormHelper(self)

        # Have to disable the form tag in crispy forms because by default cirspy will add a method to the form tag #
        # that can't be removed and that plays havoc with htmx calls where the post action is on the input buttons #
        # the form tag has to surround the {% crispy <form name> %} tag and have an id matching the hx_target
        self.helper.form_tag = False

        submit_label = 'Submit'
        submit_url = reverse_lazy('core:hx_event_update')
        target_id = "#div_event_content_id"

        event_element = Column(Field('event_id', css_class='form-control-sm'))
        if self.instance.pk:
            event_element = Hidden('event_id', self.instance.event_id)
            submit_label = 'Update'
            target_id = "#event_form_id"

        submit = Submit('submit', submit_label, css_id='event_form_button_id', css_class='btn-sm input-group-append',
                        hx_post=submit_url, hx_target=target_id)
        self.helper.layout = Layout(
            Hidden('mission', self.initial['mission'] if 'mission' in self.initial else kwargs['initial']['mission']),
            Row(
                event_element,
                Column(Field('station', css_class='form-control form-select-sm'), css_class='col-sm-12 col-md-6'),
                Column(Field('instrument', css_class='form-control form-select-sm'), css_class='col-sm-12 col-md-6'),
                Column(Field('sample_id', css_class='form-control form-control-sm'), css_class='col-sm-6 col-md-6'),
                Column(Field('end_sample_id', css_class='form-control form-control-sm'), css_class='col-sm-6 col-md-6'),
                Column(submit, css_class='col-sm-12 col-md align-self-center mt-3'),
                css_class="input-group input-group-sm"
            )
        )