import datetime
import re

from bs4 import BeautifulSoup
from crispy_forms.bootstrap import StrictButton
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Hidden, Row, Column, Submit, Field, Div, HTML, Button
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q, Min, Max
from django.urls import reverse_lazy
from django.utils.translation import gettext as _

from dart2.utils import load_svg

from . import models
from bio_tables import models as bio_models


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
        self.fields['geographic_region'].widget.attrs["hx-target"] = '#id_geographic_region'
        self.fields['geographic_region'].widget.attrs["hx-swap"] = 'outerHTML'
        self.fields['geographic_region'].widget.attrs["hx-trigger"] = 'change'
        self.fields['geographic_region'].widget.attrs["hx-get"] = reverse_lazy('core:hx_update_regions')

        self.fields['geographic_region'].choices = [(None, '------'), (-1, _('New Region')), (-2, _(''))]
        self.fields['geographic_region'].choices += [(gr.id, gr) for gr in models.GeographicRegion.objects.all()]
        self.fields['geographic_region'].initial = None
        self.fields['protocol'].required = False
        self.fields['lead_scientist'].required = False
        self.fields['mission_descriptor'].required = False
        self.fields['biochem_table'].required = False
        self.fields['data_center'].required = False
        self.fields['geographic_region'].required = False
        self.fields['collector_comments'].required = False
        self.fields['data_manager_comments'].required = False
        self.fields['more_comments'].required = False
        self.fields['platform'].required = False

        submit = Submit('submit', 'Submit')
        if hasattr(self, 'instance') and self.instance.pk and len(self.instance.events.all()):
            submit = Submit('submit', 'Submit', hx_on="click: notify_of_event_validation()")

        self.helper.layout = Layout(
            Row(
                Column(Field('name', autocomplete='true')),
            ),
            Row(
                Column(Field('start_date')),
                Column(Field('end_date'))
            ),
            Row(
                Column(
                    Row(
                        HTML(f'<label for="id_geographic_region" class=form-label">{_("Geographic Region")}</label>'),
                        css_class="mb-2"
                    ),
                    Row(
                        Column(Field('geographic_region'), css_class="col"),
                    )
                )
            ),
            Div(
                Div(
                    Div(
                        HTML(f"<h4>{_('Optional')}</h4>"),
                        css_class="card-title"
                    ),
                    css_class="card-header"
                ),
                Div(
                    Row(
                        HTML(f"{_('The following can be automatically acquired from elog files or entered later')}"),
                        css_class="alert alert-info ms-1 me-1"
                    ),
                    Row(
                        Column(Field('platform')),
                        Column(Field('protocol')),
                    ),
                    Row(
                        Column(Field('lead_scientist')),
                        Column(Field('mission_descriptor')),
                    ),
                    Row(
                        Column(Field('data_center')),
                        Column(Field('biochem_table')),
                    ),
                    Row(
                        Column(Field('collector_comments')),
                    ),
                    Row(
                        Column(Field('data_manager_comments')),
                    ),
                    Row(
                        Column(Field('more_comments')),
                    ),
                    css_class="card-body"
                ),
                css_class="card"
            ),
            Row(
                Column(
                    submit,
                    css_class='col-auto mt-2'
                ),
                css_class='justify-content-end'
            )
        )

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
            Row(Column(Field('comment', css_class='form-control-sm', placeholder=_('Comment'))),
                css_class='input-group')
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
        model = models.SampleType
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if 'initial' in kwargs and 'datatype_filter' in kwargs['initial']:
            filter = kwargs['initial']['datatype_filter'].split(" ")
            queryset = bio_models.BCDataType.objects.all()
            for term in filter:
                queryset = queryset.filter(description__icontains=term)

            self.fields['datatype'].choices = [(dt.data_type_seq, dt) for dt in queryset]

        self.helper = FormHelper(self)
        self.helper.form_tag = False

        datatype_filter = Field('datatype_filter')
        datatype_filter.attrs = {
            "hx-get": reverse_lazy('core:new_sample_type'),
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
                    Column(Field('comments', css_class='form-control form-control-sm'), css_class='col-12'),
                    css_class=''
                ),
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


class BioChemUpload(forms.Form):
    sample_type_id = forms.IntegerField(label=_("Sample Type"),
                                        help_text=_("The Sample Type to apply the BioChem datatype to"))
    mission_id = forms.IntegerField(label=_("Mission"),
                                    help_text=_("The mission to apply the BioChem datatype to"))
    data_type_filter = forms.CharField(label=_("Filter Datatype"), required=False)
    data_type_code = forms.IntegerField(label=_("Datatype Code"), required=False)
    data_type_description = forms.ChoiceField(label=_("Datatype Description"), required=False)

    start_sample = forms.IntegerField(label=_("Start"))
    end_sample = forms.IntegerField(label=_("End"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        data_type_choices_qs = bio_models.BCDataType.objects.all()
        if 'data_type_filter' in kwargs['initial']:
            filter = kwargs['initial']['data_type_filter'].split(" ")
            q_set = Q()
            for f in filter:
                q_set = Q(description__icontains=f) & q_set
            data_type_choices_qs = data_type_choices_qs.filter(q_set)

            if data_type_choices_qs.exists():
                data_type_choices = [(st.pk, st) for st in data_type_choices_qs]

                self.fields['data_type_description'].choices = data_type_choices
                self.fields['data_type_description'].initial = data_type_choices[0][0]
                self.fields['data_type_code'].initial = data_type_choices[0][0]
            else:
                self.fields['data_type_description'].choices = [(None, '---------')]
                self.fields['data_type_description'].initial = None
                self.fields['data_type_code'].initial = None
        else:
            data_type_choices = [(st.pk, st) for st in data_type_choices_qs]
            data_type_choices.insert(0, (None, '---------'))
            self.fields['data_type_description'].choices = data_type_choices
            self.fields['data_type_description'].initial = None

            if 'data_type_code' in kwargs['initial']:
                self.fields['data_type_description'].initial = kwargs['initial']['data_type_code']

        if 'mission_id' in self.initial and 'sample_type_id' in self.initial:
            mission_id = self.initial['mission_id']
            min_max = models.Bottle.objects.filter(event__mission_id=mission_id).aggregate(
                Min('bottle_id'), Max('bottle_id'))
            if 'start_sample' not in kwargs['initial']:
                self.fields['start_sample'].initial = min_max['bottle_id__min']

            if 'end_sample' not in kwargs['initial']:
                self.fields['end_sample'].initial = min_max['bottle_id__max']

        self.helper = FormHelper(self)

        data_type_filter = Field('data_type_filter', css_class="form-control form-control-sm")
        data_type_filter.attrs['hx-get'] = reverse_lazy('core:hx_update_sample_type')
        data_type_filter.attrs['hx-trigger'] = 'keyup changed delay:500ms, change'
        data_type_filter.attrs['hx-target'] = "#div_id_data_type_row"
        data_type_filter.attrs['hx-select'] = "#div_id_data_type_row"

        data_type_code = Field('data_type_code', id='id_data_type_code', css_class="form-control-sm")
        data_type_code.attrs['hx-get'] = reverse_lazy('core:hx_update_sample_type')
        data_type_code.attrs['hx-trigger'] = 'keyup changed delay:500ms, change'
        data_type_code.attrs['hx-target'] = "#id_data_type_description"
        data_type_code.attrs['hx-select-oob'] = "#id_data_type_description"

        data_type_description = Field('data_type_description', id='id_data_type_description',
                                      css_class='form-control form-select-sm')
        data_type_description.attrs['hx-get'] = reverse_lazy('core:hx_update_sample_type')
        data_type_description.attrs['hx-trigger'] = 'change'
        data_type_description.attrs['hx-target'] = "#id_data_type_code"
        data_type_description.attrs['hx-select'] = "#id_data_type_code"

        apply_attrs = {
            'name': 'apply_data_type',
            'title': _('Apply Datatype to Samples'),
            'hx-get': reverse_lazy('core:hx_update_sample_type'),
            'hx-target': "#div_id_data_type_message",
            'hx-swap': 'innerHTML'
        }
        apply_button = StrictButton(load_svg('arrow-down-square'), css_class="btn btn-primary btn-sm ms-2",
                                    **apply_attrs)

        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                Field('sample_type_id', type='hidden'),
                Field('mission_id', type='hidden'),
                Row(
                    Column(data_type_filter, css_class='col'),
                ),
                Row(
                    Column(data_type_code, css_class='col-auto'),
                    Column(data_type_description, css_class="col"),
                    id="div_id_data_type_row"
                ),
                Row(
                    Column(Field('start_sample', css_class="form-control-sm"), css_class='col-auto'),
                    Column(Field('end_sample', css_class="form-control-sm"), css_class="col-auto"),
                    Column(apply_button, css_class="col-auto align-self-end mb-3"),
                    id="div_id_sample_range"
                ),
                Row(
                    Column(id="div_id_data_type_message")
                ), css_class="alert alert-secondary mt-2", id="div_id_data_type_form"
            )
        )


# Form for loading a file, connecting sample, value, flag and replica fields to the SampleType so a user
# doesn't have to constantly re-enter columns. Ultimately the user will select a file, the file type with the
# expected headers for sample and value fields will be used to determine what SampleTypes the file contains
# which will be automatically loaded if they've been previously seen. Otherwise a user will be able to add
# new configurations for sample types.
class SampleTypeConfigForm(forms.ModelForm):
    sample_field = forms.CharField(help_text=_("Column that contains the bottle ids"))
    value_field = forms.CharField(help_text=_("Column that contains the value data"))
    replicate_field = forms.CharField(required=False, help_text=_("Column indicating replicate ids, if it exists"))
    flag_field = forms.CharField(required=False, help_text=_("Column that contains quality flags, if it exists"))
    comment_field = forms.CharField(required=False, help_text=_("Column containing comments, if it exists"))

    NONE_CHOICE = [(None, "------")]

    datatype_filter = forms.CharField(label=_("Filter Datatype"), required=False,
                                      help_text=_("Filter the Datatype field on key terms"))

    class Meta:
        model = models.SampleTypeConfig
        fields = "__all__"

    def __init__(self, *args, **kwargs):

        # To use this form 'field_choices', a list of options the user can select from for the
        # header row, must be passed in to populate the dropdowns. For some reason after the
        # form has been created and populated the 'declared_fields' variable maintains the list
        # of options and can be used when passing a request.GET or request.POST in
        choice_fields = ['sample_field', 'replicate_field', 'value_field', 'flag_field', 'comment_field']
        if 'field_choices' in kwargs:
            field_choices: list = kwargs.pop('field_choices')

            for field in choice_fields:
                s_field: forms.CharField = self.base_fields[field]
                self.base_fields[field] = forms.ChoiceField(help_text=s_field.help_text, required=s_field.required)
                if not self.base_fields[field].required:
                    self.base_fields[field].choices = self.NONE_CHOICE
                self.base_fields[field].choices += field_choices
        else:
            for field in choice_fields:
                self.base_fields[field] = self.declared_fields[field]

        file_type = None
        if 'instance' in kwargs and kwargs['instance']:
            file_type = kwargs['instance'].file_type
        elif args and 'file_type' in args[0]:
            file_type = args[0]['file_type']
        elif 'initial' in kwargs and 'file_type' in kwargs['initial']:
            file_type = kwargs['initial']['file_type']
        elif 'file_type' in kwargs:
            file_type = kwargs.pop('file_type')

        if file_type is None:
            raise KeyError({'message': 'missing initial "file_type"'})

        super().__init__(*args, **kwargs)

        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout()

        sample_type_choices = [(st.pk, st) for st in models.SampleType.objects.all()]
        sample_type_choices.insert(0, (None, ""))
        sample_type_choices.insert(0, (-1, "New Sample Type"))
        sample_type_choices.insert(0, (None, '---------'))
        self.fields['sample_type'].choices = sample_type_choices

        hx_relaod_form_attributes = {
            'hx-post': reverse_lazy('core:new_sample_config'),
            'hx-select': "#div_id_fields_row",
            'hx-target': "#div_id_fields_row",
            'hx-swap': "outerHTML",
            'hx-trigger': "keyup changed delay:500ms, change"
        }

        # if the tab field is updated the form should reload looking for headers on the updated tab index
        if file_type.startswith('xls'):
            tab_field = Field('tab')
            tab_field.attrs = hx_relaod_form_attributes
            tab_col = Column(tab_field)
        else:
            tab_col = Hidden('tab', "0")

        # if the header field is updated the form should reload looking for headers on the updated row
        header_row_field = Field('skip')
        header_row_field.attrs = hx_relaod_form_attributes

        config_name_row = Row(
            tab_col,
            Column(header_row_field),
            Column(Field('allow_blank', css_class='checkbox-primary')),
            Column(Field('allow_replicate', css_class='checkbox-primary')),
            css_class="flex-fill"
        )

        if self.instance.pk:
            config_name_row.fields.insert(0, Hidden('id', self.instance.pk))

        url = reverse_lazy('core:new_sample_config')
        hx_sample_type_attrs = {
            'hx_get': url,
            'hx_trigger': 'change',
            'hx_target': '#div_id_sample_type',
            'hx_select': '#div_id_sample_type',
            'hx_swap': 'outerHTML'
        }
        sample_type_row = Div(
            Field('sample_type', **hx_sample_type_attrs, wrapper_class="col-auto"),
            css_class="row flex-fill mt-2"
        )

        div = Div(
            # file type is hidden because it's taken care of by the form creation and
            # the type of file a user is loading
            Field('file_type', type="hidden"),
            config_name_row,

            Row(
                Column(Field('sample_field')),
                Column(Field('value_field')),
                Column(Field('replicate_field')),
                Column(Field('flag_field', )),
                Column(Field('comment_field')),
                css_class="flex-fill", id="div_id_fields_row"
            ),
            id="div_id_file_attributes",
            css_class="form-control input-group mt-2"
        )

        self.helper[0].layout.fields.append(sample_type_row)
        self.helper[0].layout.fields.append(div)

        button_row = Row(
            Column(css_class='col text-end'), css_class="mt-2", id="button_row"
        )

        attrs = {
            'css_class': "btn btn-primary btn-sm ms-2",
            'name': "add_sample_type",
            'hx_get': reverse_lazy("core:save_sample_config"),
            'hx_target': "#button_row",
            'hx_select': "#div_id_loaded_sample_type_message",
        }

        button_new = StrictButton(load_svg('plus-square'), **attrs)
        button_row.fields[0].insert(0, button_new)

        if self.instance.pk:
            attrs['hx_get'] = reverse_lazy("core:save_sample_config", args=(self.instance.pk,))
            attrs['name'] = "update_sample_type"

            attrs['css_class'] = 'btn btn-secondary btn-sm ms-2'
            button_update = StrictButton(load_svg('arrow-clockwise'), **attrs)
            button_row.fields[0].insert(0, button_update)

        self.helper[0].layout.fields.append(button_row)


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
            "hx_get": reverse_lazy("core:hx_sample_upload_ctd", args=(kwargs['initial']['mission'],)),
            "hx_swap": 'beforeend'
        }

        url = reverse_lazy("core:hx_sample_upload_ctd", args=(kwargs['initial']['mission'],))
        url += f"?bottle_dir={kwargs['initial']['bottle_dir']}"
        all_attrs = {
            'title': _('Show Unloaded') if 'show_all' in kwargs['initial'] else _('Show All'),
            'name': 'show_some' if 'show_all' in kwargs['initial'] else 'show_all',
            'hx_get': url,
            'hx_target': "#form_id_ctd_bottle_upload",
            'hx_swap': 'outerHTML'
        }
        icon = load_svg('eye-slash') if 'show_all' in kwargs['initial'] else load_svg('eye')
        all_button = StrictButton(icon, css_class="btn btn-primary btn-sm", **all_attrs)

        submit_button = StrictButton(load_svg('plus-square'), css_class="btn btn-primary btn-sm", type='input',
                                     title=_("Load Selected"))
        self.helper.layout = Layout(
            Row(Column(all_button)),
            Hidden('bottle_dir', kwargs['initial']['bottle_dir']),
            Row(Column(Field('file_name')), css_class='mt-2'),
            submit_button
        )
        self.helper.form_show_labels = False


def save_load_component(component_id, message, **kwargs):

    alert_type = kwargs.pop('alert_type') if 'alert_type' in kwargs else 'info'

    # return a loading alert that calls this methods post request
    # Let's make some soup
    soup = BeautifulSoup('', "html.parser")

    root_div = soup.new_tag("div")
    soup.append(root_div)

    # creates an alert dialog with an animated progress bar to let the user know we're saving or loading something
    # type should be a bootstrap css type, (danger, info, warning, success, etc.)

    # create an alert area saying we're loading
    alert_div = soup.new_tag("div", attrs={'class': f"alert alert-{alert_type} mt-2"})
    alert_msg = soup.new_tag('div', attrs={'id': f'{component_id}_message'})
    alert_msg.string = message

    alert_div.append(alert_msg)

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

    root_div.attrs = {
        'id': component_id,
    }

    for attr, val in kwargs.items():
        root_div.attrs[attr] = val

    root_div.append(alert_div)
    soup.append(root_div)

    return soup
