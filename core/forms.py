import datetime
import re
import csv

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Hidden, Row, Column, Submit, Field, Div, HTML, Button
from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.urls import reverse_lazy
from django.utils.translation import gettext as _

import bio_tables.models
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
        if 'initial' in kwargs and 'geographic_region' in kwargs['initial']:
            self.fields['geographic_region'].initial = kwargs['initial']['geographic_region']

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

        # This button depends on a separate section being on the page with the ID 'geographic_region_dialog'
        button_geo_add = HTML('<button class="btn btn-primary" data-bs-toggle="modal" data-bs-target="#geographic_region_dialog">+</button>')

        submit = Submit('submit', 'Submit')
        if hasattr(self, 'instance') and self.instance.pk and len(self.instance.events.all()):
            submit = Submit('submit', 'Submit', hx_on="click: notify_of_event_validation()")

        self.helper.layout = Layout(
            Row(
                Column(Field('name')),
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
                        Column(button_geo_add, css_class="col-auto"),
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


# Form for loading a file, connecting sample, value, flag and replica fields to the SampleType so a user
# doesn't have to constantly re-enter columns. Ultimately the user will select a file, the file type with the
# expected headers for sample and value fields will be used to determine what SampleTypes the file contains
# which will be automatically loaded if they've been previously seen. Otherwise a user will be able to add
# new sample types to the file configuration and load multiple columns instead of having to use the same file
# multiple times to load different samples from the same file.
#
# If a sample_name argument is supplied then the ids for this form will be post fixed with the sample_name
# so that this form can be embedded in a larger form
class SampleFileConfigurationForm(forms.ModelForm):
    sample_field = forms.CharField(help_text=_("Column that contains the bottle ids"))
    value_field = forms.CharField(help_text=_("Column that contains the value data"))
    replicate_field = forms.CharField(required=False, help_text=_("Column indicating a replicate ids, if it exists"))
    flag_field = forms.CharField(required=False, help_text=_("Column that contains quality flags, if it exists"))
    comment_field = forms.CharField(required=False, help_text=_("Column containing comments, if it exists"))

    NONE_CHOICE = [(None, "------")]

    class Meta:
        model = models.SampleFileSettings
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        # at the very least an initial file_type will be expected to determine if this
        # form should show a tab field or not
        # if 'initial' not in kwargs:
        #     raise KeyError({'message': 'missing "initial" dictionary in form creation'})
        #
        # if 'file_type' not in kwargs['initial']:
        #     raise KeyError({'message': 'missing initial "file_type"'})
        #
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

        # if no post_url is supplied then it's expected the form is posting to whatever
        # view (and it's url) that created the form
        post_url = "."
        if 'post_url' in kwargs:
            post_url = kwargs.pop('post_url')

        sample_name = None
        if 'sample_name' in kwargs:
            sample_name = kwargs.pop('sample_name')

        file_type = None
        if args and 'file_type' in args[0]:
            file_type = args[0]['file_type']
        elif 'initial' in kwargs and 'file_type' in kwargs['initial']:
            file_type = kwargs['initial']['file_type']

        sample_type = None
        if args and 'sample_type' in args[0]:
            sample_type = args[0]['sample_type']
        elif 'initial' in kwargs and 'sample_type' in kwargs['initial']:
            sample_type = kwargs['initial']['sample_type']

        if file_type is None:
            raise KeyError({'message': 'missing initial "file_type"'})

        super().__init__(*args, **kwargs)

        self.helper = FormHelper(self)
        self.helper.form_tag = False

        self.helper.layout = Layout()

        div = Div(
            Field('sample_type', id=f"id_sample_type" + (f"_{sample_name}" if sample_name else ""),
                  type="hidden"),
            Field('file_type', id=f"id_file_type" + (f"_{sample_name}" if sample_name else ""),
                  type="hidden"),
            Row(
                Column(Field('file_config_name',
                             id=f"id_file_config_name" + (f"_{sample_name}" if sample_name else ""))),
                # file type is hidden because it's taken care of by the form creation and
                # the type of file a user is loading
                Column(Field('header',
                             id=f"id_header" + (f"_{sample_name}" if sample_name else ""))),
                css_class="flex-fill"
            ),
            Row(
                Column(Field('sample_field',
                             id=f"id_sample_field" + (f"_{sample_name}" if sample_name else ""))),
                Column(Field('replicate_field',
                             id=f"id_replicate_field" + (f"_{sample_name}" if sample_name else ""))),
                Column(Field('value_field',
                             id=f"id_value_field" + (f"_{sample_name}" if sample_name else ""))),
                Column(Field('flag_field',
                             id=f"id_flag_field" + (f"_{sample_name}" if sample_name else ""))),
                Column(Field('comment_field',
                             id=f"id_comment_field" + (f"_{sample_name}" if sample_name else ""))),
                css_class="flex-fill"
            ),
            id="div_id_file_attributes" + (f"_{sample_name}" if sample_name else ""),
            css_class="form-control input-group mt-2"
        )

        if file_type.startswith('xls'):
            tab_col = Column(Field('tab'),
                             id=f"id_tab" + (f"_{sample_name}" if sample_name else ""))

            div.fields[1].insert(1, tab_col)

        root_div = Div(div, id=f"id_form_file_configuration" + (f"_{sample_name}" if sample_name else ""))
        self.helper[0].layout.fields.append(root_div)


class SampleTypeForm(forms.ModelForm):
    datatype_filter = forms.CharField(label=_("Filter Datatype"), required=False,
                                      help_text=_("Filter the Datatype field on key terms"))

    class Meta:
        model = models.SampleType
        fields = "__all__"

    def __init__(self, *args, **kwargs):

        # if no post_url is supplied then it's expected the form is posting to whatever
        # view (and it's url) that created the form
        post_url = "."
        if "post_url" in kwargs:
            post_url = kwargs.pop("post_url")

        sample_name = None
        if 'sample_name' in kwargs:
            sample_name = kwargs.pop('sample_name')

        super().__init__(*args, **kwargs)

        if 'initial' in kwargs and 'datatype_filter' in kwargs['initial']:
            filter = kwargs['initial']['datatype_filter'].split(" ")
            queryset = bio_tables.models.BCDataType.objects.all()
            for term in filter:
                queryset = queryset.filter(description__icontains=term)

            queryset = queryset.order_by('priority')
            self.fields['datatype'].choices = [(dt.data_type_seq, dt) for dt in queryset]

        self.helper = FormHelper(self)
        self.helper.form_tag = False

        datatype_filter = Field('datatype_filter')
        datatype_filter.attrs = {
            "hx-get": post_url,
            "hx-target": "#div_id_datatype",
            "hx-select": "#div_id_datatype",  # natural id that crispy-forms assigns to the datatype div
            "hx-trigger": "keyup changed delay:2s",
            "hx-swap": 'outerHTML',
            'class': "form-control form-control-sm"
        }

        self.helper.layout = Layout(
            Div(
                Row(
                    Column(Field('short_name', css_class='form-control form-control-sm',
                                 id="id_short_name" + (f"_{sample_name}" if sample_name else "")),
                           css_class='col'),
                    Column(Field('long_name', css_class='form-control form-control-sm',
                                 id="id_long_name" + (f"_{sample_name}" if sample_name else "")),
                           css_class='col'),
                    Column(Field('priority', css_class='form-control form-control-sm',
                                 id="id_priority" + (f"_{sample_name}" if sample_name else "")),
                           css_class='col'),
                    css_class='flex-fill ms-1'
                ),
                Row(
                    Column(Field('comments', css_class='form-control form-control-sm',
                                 id="id_comments" + (f"_{sample_name}" if sample_name else "")),
                           css_class='col-12'),
                    css_class=''
                ),
                Row(
                    Column(datatype_filter, css_class='col-12'),
                    css_class=''
                ),
                Row(
                    Column(Field('datatype', css_class='form-control form-select-sm',
                                 id="id_datatype" + (f"_{sample_name}" if sample_name else "")),
                           css_class='col-12'),
                    css_class="flex-fill"
                ),
                css_class="form-control mt-2", id="div_id_sample_type_form"
            )
        )


class NewSampleForm(forms.ModelForm):
    datatype_filter = forms.CharField(label=_("Filter Datatype"), required=False,
                                      help_text=_("Filter the Datatype field on key terms"))

    sample_id_col = forms.ChoiceField(label=_("Sample ID"),
                                      help_text=_("Choose the column to use for the sample/bottle id"))
    sample_value_col = forms.ChoiceField(label=_("Sample Value"),
                                         help_text=_("Choose the column to use for the value of the sample"))

    skip_lines = forms.IntegerField(label=_("Skip Lines"),
                                    help_text=_("Number of lines to skip to find the header column"))
    file = forms.FileField(label=_("Data File"), required=False)

    class Meta:
        model = models.SampleType
        fields = ['short_name', 'long_name', 'priority', 'datatype', 'datatype_filter', 'file', 'sample_id_col',
                  'sample_value_col', 'skip_lines']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        mission_id = kwargs['initial']['mission']
        self.helper = FormHelper(self)
        self.helper.attrs = {
            "hx_post": reverse_lazy("core:hx_sample_form", args=(mission_id,)),
            "hx_encoding": "multipart/form-data",
            "hx_target": "this",
            "hx_swap": "outerHTML"
        }

        if 'datatype_filter' in kwargs['initial'] and kwargs['initial']['datatype_filter']:
            filter = kwargs['initial']['datatype_filter'].split(" ")
            queryset = bio_tables.models.BCDataType.objects.all()
            for term in filter:
                queryset = queryset.filter(description__icontains=term)

            queryset = queryset.order_by('priority')
            self.fields['datatype'].choices = [(dt.data_type_seq, dt) for dt in queryset]

        datatype_filter = Field('datatype_filter', css_class='form-control form-control-sm')
        datatype_filter.attrs = {
            "hx-get": reverse_lazy('core:hx_sample_form', args=(mission_id,)),
            "hx-target": "#div_id_datatype",
            "hx-select": "#div_id_datatype",
            "hx-trigger": "keyup changed delay:2s",
            "hx-swap": 'outerHTML'
        }

        file_field = Field('file')
        file_field.attrs = {
            "hx-trigger": "change",
            "hx-post": reverse_lazy('core:hx_sample_form', args=(mission_id,)),
            "hx-target": "#file_properties_id",
            "hx-select": "#file_properties_id",
            "hx-swap": "outerHTML"
        }

        file_properties = Div(id="file_properties_id")
        if 'file_name' in kwargs['initial'] and 'file_data' in kwargs['initial']:
            file_name = kwargs['initial']['file_name']
            if kwargs['initial']['file_name'].endswith(".csv"):
                # we don't want to read the file if we already have the values we're looking for
                data = kwargs['initial']['file_data'].split("\r\n")
                csv_reader = csv.reader(data, delimiter=',')
                skip = 0
                lineone = next(csv_reader)
                while '' in lineone:
                    skip += 1
                    lineone = next(csv_reader)

                self.fields['skip_lines'].initial = skip
                self.fields['sample_id_col'].choices = [(i, col) for i, col in enumerate(lineone)]
                self.fields['sample_value_col'].choices = [(i, col) for i, col in enumerate(lineone)]

                file_properties = Row(
                    Column('skip_lines', css_class="col"),
                    Column('sample_id_col', css_class="col"),
                    Column('sample_value_col', css_class="col"),
                    id="file_properties_id"
                )
            elif file_name.endswith(".xls") or file_name.endswith("xlsx"):
                file_properties = Row(HTML("<p>xls detected</p>"), id="file_properties_id")
            else:
                file_properties = Row(HTML(f"<p>{_('Unexpected file type')}</p>"), id="file_properties_id")

        self.helper.layout = Layout(
            Row(
                Column(Field('short_name', css_class='form-control form-control-sm'), css_class="col"),
                Column(Field('sample_type_name', css_class='form-control form-control-sm'), css_class="col"),
                Column(Field('priority', css_class='form-control form-control-sm'), css_class="col"),
            ),
            Row(
                Column(datatype_filter, css_class="col")
            ),
            Row(
                Column(Field('datatype', css_class='form-control form-select-sm'), css_class="col"),
            ),
            Row(
                Column(file_field, css_class="col")
            ),
            file_properties
        )

        self.helper.add_input(Submit('submit', _("Submit")))


class BottleSelection(forms.Form):
    bottle_dir = forms.FileField(label=_("Bottle Directory"), required=True)
    file_name = forms.MultipleChoiceField(label=_("File"), required=False)

    class Meta:
        fields = ['bottle_dir', 'file_name']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if 'initial' in kwargs and 'file_name' in kwargs['initial']:
            self.fields['file_name'].choices = ((f, f,) for f in kwargs['initial']['file_name'])

        self.helper = FormHelper(self)
        # self.helper.form_tag = False
        self.helper.attrs = {
            "hx_post": reverse_lazy("core:hx_sample_upload_ctd", args=(kwargs['initial']['mission'],))
        }

        self.helper.layout = Layout(
            Hidden('bottle_dir', kwargs['initial']['bottle_dir']),
            Row(Column('file_name')),
        )

        self.helper.add_input(Submit('submit', _("Submit")))
