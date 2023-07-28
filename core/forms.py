import datetime
import re

from crispy_forms.helper import FormHelper
from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse_lazy

from dynamic_forms import DynamicField, DynamicFormMixin

from django.utils.translation import gettext as _

from . import models


class NoWhiteSpaceCharField(forms.CharField):
    def validate(self, value):
        super().validate(value)
        if re.search(r"\s", value):
            raise ValidationError("Field may not contain whitespaces")


class MissionSettingsForm(forms.ModelForm):

    name = NoWhiteSpaceCharField(max_length=50, label="Mission Name", required=True)
    elog_dir = forms.CharField(max_length=255, label="Elog Directory", required=False,
                               help_text="Folder location of Elog *.log files")
    bottle_dir = forms.CharField(max_length=255, label="CTD Bottle Directory", required=False,
                                 help_text="Folder location of Elog *.BTL files")
    mission_descriptor = NoWhiteSpaceCharField(max_length=50, required=False)

    start_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date', 'value': datetime.datetime.now().strftime("%Y-%m-%d")}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date', 'value': datetime.datetime.now().strftime("%Y-%m-%d")}))

    class Meta:
        model = models.Mission
        fields = ['name', 'start_date', 'end_date', 'elog_dir', 'bottle_dir', 'lead_scientist',
                  'protocol', 'platform', 'geographic_region', 'mission_descriptor', 'collector_comments',
                  'more_comments', 'data_manager_comments', 'biochem_table', 'data_center']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_show_labels = True
        self.fields['geographic_region'].label = False
        self.fields['geographic_region'].widget.attrs["hx-target"] ='#div_id_geographic_region'
        self.fields['geographic_region'].widget.attrs["hx-trigger"] ='region_added from:body'
        self.fields['geographic_region'].widget.attrs["hx-get"] = reverse_lazy('core:update_regions')

    def geographic_region_choices(form):
        regions = models.GeographicRegion.objects.all()
        return regions

    def clean_end_date(self):
        end_date = self.cleaned_data['end_date']
        start_date = self.cleaned_data['start_date']
        if end_date < start_date:
            raise forms.ValidationError("The end date must occur after the start date")

        return end_date
