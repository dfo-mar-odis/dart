import datetime
import re
import csv

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Hidden, Row, Column, Submit, Field, Div, HTML, Button
from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse_lazy
from django.utils.translation import gettext as _

import bio_tables.models
from dart2.utils import load_svg
import dart2.utils
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
        button_geo_add = HTML(
            '<button class="btn btn-primary" type="button" data-bs-toggle="modal" '
            'data-bs-target="#geographic_region_dialog">+</button>')

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
# new sample types.
class SampleTypeForm(forms.ModelForm):
    sample_field = forms.CharField(help_text=_("Column that contains the bottle ids"))
    value_field = forms.CharField(help_text=_("Column that contains the value data"))
    replicate_field = forms.CharField(required=False, help_text=_("Column indicating replicate ids, if it exists"))
    flag_field = forms.CharField(required=False, help_text=_("Column that contains quality flags, if it exists"))
    comment_field = forms.CharField(required=False, help_text=_("Column containing comments, if it exists"))

    NONE_CHOICE = [(None, "------")]

    datatype_filter = forms.CharField(label=_("Filter Datatype"), required=False,
                                      help_text=_("Filter the Datatype field on key terms"))

    class Meta:
        model = models.SampleType
        fields = "__all__"

    def __init__(self, *args, **kwargs):

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
        sample_name = None
        if 'sample_name' in kwargs:
            sample_name = kwargs.pop('sample_name')

        file_type = None
        if 'instance' in kwargs:
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

        if 'initial' in kwargs and 'datatype_filter' in kwargs['initial']:
            filter = kwargs['initial']['datatype_filter'].split(" ")
            queryset = bio_tables.models.BCDataType.objects.all()
            for term in filter:
                queryset = queryset.filter(description__icontains=term)

            self.fields['datatype'].choices = [(dt.data_type_seq, dt) for dt in queryset]

        self.helper = FormHelper(self)
        self.helper.form_tag = False

        datatype_filter = Field('datatype_filter')
        datatype_filter.attrs = {
            "hx-get": reverse_lazy('core:load_sample_type'),
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
                    Column(datatype_filter, css_class='col-12'),  css_class=''
                ),
                Row(
                    Column(Field('datatype', css_class='form-control form-select-sm'), css_class='col-12'),
                    css_class="flex-fill"
                ),
                css_class="form-control mt-2", id="div_id_sample_type_form"
            )
        )

        hx_relaod_form_attributes = {
            'hx-post': reverse_lazy('core:load_sample_type'),
            'hx-select': "#div_id_file_attributes",
            'hx-target': "#div_id_file_attributes",
            'hx-swap': "outerHTML",
            'hx-trigger': "keyup changed delay:1s, change"
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

        div = Div(
            # file type is hidden because it's taken care of by the form creation and
            # the type of file a user is loading
            Field('file_type', type="hidden"),

            config_name_row,

            Row(
                Column(Field('sample_field')),
                Column(Field('value_field')),
                Column(Field('replicate_field')),
                Column(Field('flag_field',)),
                Column(Field('comment_field')),
                css_class="flex-fill"
            ),
            id="div_id_file_attributes",
            css_class="form-control input-group mt-2"
        )

        self.helper[0].layout.fields.append(div)

        if self.instance.pk:
            url = reverse_lazy("core:save_sample_type", args=(self.instance.pk,))
        else:
            url = reverse_lazy("core:save_sample_type")

        button = '<button type="button" class="btn btn-primary btn-sm" name="add_sample_type"'
        button += f' hx-get="{url}"'
        button += f' hx-target="#button_row"'
        button += f' hx-select="#div_id_loaded_sample_type_message"'
        button += ">"
        button += load_svg('plus-square')
        button += "</button>"
        submit = HTML(button)
        button_row = Row(
            Column(submit, css_class='col text-end'), css_class="mt-2", id="button_row"
        )
        self.helper[0].layout.fields.append(button_row)


# This form is used after sample types have been created and sample file configs have been assigned.
# It's not a modifiable form, rather it lists information for the user to decide if this is what
# they want to load.
class SampleTypeLoadForm(forms.ModelForm):
    class Meta:
        model = models.SampleType
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper(self)
        self.helper.form_tag = False

        card_id = f"div_id_{self.instance.pk}"
        body = Div(
            Row(
                Column(HTML(f'{_("Header Row")} : {self.instance.skip}'), css_class="col-auto")
            ),
            Row(
                Column(HTML(f'<div class="h6 mt-2">{_("Columns")}</div>'))
            ),
            Row(
                Column(HTML(f'{_("Bottle ID")} : "{self.instance.sample_field}"')),
                Column(HTML(f'{_("Value")} : "{self.instance.value_field}"')),
            ),
            Row(id=f"{card_id}_message")
        )

        if self.instance.replicate_field:
            body[2].fields.append(Column(HTML(f'{_("Replicate")} : "{self.instance.replicate_field}"')))

        if self.instance.flag_field:
            body[2].fields.append(Column(HTML(f'{_("Data Quality Flag")} : {self.instance.flag_field}')))

        if self.instance.comment_field:
            body[2].fields.append(Column(HTML(f'{_("Comment")} : "{self.instance.comment_field}"')))

        if self.instance.file_type.startswith('xls'):
            body[0].fields.insert(0, Column(HTML(f'{_("Tab #")} : {self.instance.tab}'), css_class="col-auto"))

        # upon successfully loading the content the 'core:load_samples' function should return the button
        # as a 'btn btn-success btn-sm' button
        load_url = reverse_lazy('core:load_samples', args=(self.instance.pk,))
        load_button = HTML(
            f'<button id="{card_id}_load_button" class="btn btn-primary btn-sm" type="button" name="load" '
            f'hx-get="{load_url}" hx-target="#{card_id}_message"'
            f'>{load_svg("folder-check")}</button>')

        edit_url = reverse_lazy('core:new_sample_type', args=(self.instance.pk,))
        edit_button = HTML(
            f'<button class="btn btn-primary btn-sm me-1" type="button" name="edit" '
            f'hx-post="{edit_url}" hx-target="#div_id_sample_type">{load_svg("pencil-square")}</button>')

        delete_url = reverse_lazy('core:delete_sample_type', args=(self.instance.pk,))
        delete_button = HTML(
            f'<button class="btn btn-danger btn-sm" type="button" name="delete" '
            f'hx-post="{delete_url}" hx-target="#{card_id}" hx-swap="delete" '
            f'hx-confirm="{_("Are you sure?")}">{load_svg("dash-square")}</button>')

        title_label = f'{self.instance.file_type} - {self.instance.short_name}'
        title_label += f' : {self.instance.long_name}' if self.instance.long_name else ''

        title = Div(
            Column(
                HTML(f'<div class="h6">{title_label}</div>'),
                css_class='col'
            ),
            Column(
                delete_button,
                css_class='col-auto'
            ),
            Column(
                edit_button,
                load_button,
                css_class='col-auto'
            ),
            css_class='card-title row'
        )

        self.helper.layout = Layout(
            Div(
                Div(title, css_class='card-header'),
                Div(body, css_class='card-body'),
                css_class='card mt-2',
                id=f"{card_id}"
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
            "hx_post": reverse_lazy("core:hx_sample_upload_ctd", args=(kwargs['initial']['mission'],)),
            "hx_swap": 'outerHTML'
        }

        self.helper.layout = Layout(
            Hidden('bottle_dir', kwargs['initial']['bottle_dir']),
            Row(Column(Field('file_name'))),
        )

        self.helper.add_input(Submit('submit', _("Submit")))
