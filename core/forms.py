import datetime
import re

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Hidden, Row, Column, Submit, Button
from django import forms
from django.core.exceptions import ValidationError
from django.db.models.expressions import Col
from django.forms import inlineformset_factory, DateField
from django.urls import reverse_lazy


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

    start_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date', 'value': datetime.datetime.now().strftime("%Y-%m-%d")}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date', 'value': datetime.datetime.now().strftime("%Y-%m-%d")}))

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
        self.fields['geographic_region'].widget.attrs["hx-target"] ='#div_id_geographic_region'
        self.fields['geographic_region'].widget.attrs["hx-trigger"] ='region_added from:body'
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

    date_time = forms.DateTimeField(widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'value': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}))

    class Meta:
        model = models.Action
        fields = ['event', 'type', 'date_time', 'latitude', 'longitude']
        widgets = {
            'event': forms.HiddenInput()
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper(self)
        self.helper.form_tag = False

        event_pk = self.initial['event'] if 'event' in self.initial else args[0]['event']
        self.helper.layout = Layout(
            Hidden('event', event_pk),
            Row(
                Column('type'),
                Column('date_time'),
                Column('latitude'),
                Column('longitude'),
                Column(Submit('submit', '+', hx_target="#actions_form_id",
                              hx_post=reverse_lazy('core:action_new', args=(event_pk,)),
                              ))
            )
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
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Hidden('mission', self.initial['mission'] if 'mission' in self.initial else kwargs['initial']['mission']),
            Hidden('event_id', self.initial['event_id']) if 'event_id' in self.initial else 'event_id',
            'station',
            'instrument',
            Row(
                Column('sample_id'),
                Column('end_sample_id')
            )
        )
        if 'event_id' in self.initial:
           submit = Submit('submit', 'Update', css_id='event_form_button_id',
                           hx_post=reverse_lazy('core:event_update', args=(self.initial['event_id'],)),
                           hx_swap="outerHTML", hx_target="#event_form_id")
        else:
            submit = Submit('submit', 'Submit', css_id='event_form_button_id',
                            hx_post=reverse_lazy('core:event_new', args=(kwargs['initial']['mission'],)),
                            hx_swap="outerHTML", hx_target="#event_form_id")

        self.helper.add_input(submit)


ActionFormSet = inlineformset_factory(
    models.Event, models.Action, form=ActionForm, extra=1, can_delete=False,
)
