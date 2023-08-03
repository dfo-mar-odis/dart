import datetime
import re

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Row, Column
from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory, DateField
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

        event_id = None
        if 'instance' in kwargs:
            event = kwargs['instance']
            self.fields['event'].initial = event
            event_id = event.pk
        elif 'event' in args[0]:
            event_id = args[0]['event']

        self.helper = FormHelper()
        # self.form_method = 'post'
        # self.template = 'core/partials/action_formset.html'
        self.helper.form_id = 'form_action_id'
        self.helper.attrs = {
            'hx-post': reverse_lazy("core:hx_add_action", args=(event_id,)),
        }
        self.helper.layout = Layout(
            Row(
                Column('event'),
                Column('type'),
                Column('date_time'),
                Column('latitude'),
                Column('longitude'),
                Column(Submit('submit', "+"), css_class='align-self-end mb-3')
            )
        )


class EventForm(forms.ModelForm):

    class Meta:
        model = models.Event
        fields = ['mission', 'event_id', 'station', 'instrument', 'sample_id', 'end_sample_id']
        widgets = {
            'mission': forms.HiddenInput()
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.layout = Layout(
            'mission',
            'event_id',
            'station',
            'instrument',
            Row(Column('sample_id'), Column('end_sample_id')),
        )
        self.helper.add_input(Submit('submit', _("Submit")))

    def is_valid(self):
        valid = super().is_valid()
        return valid


ActionFormSet = inlineformset_factory(
    models.Event, models.Action, form=ActionForm, extra=1, can_delete=False,
)
