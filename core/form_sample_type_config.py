from bs4 import BeautifulSoup

from crispy_forms.bootstrap import StrictButton
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Column, Hidden, Row, Div
from crispy_forms.utils import render_crispy_form

from django import forms
from django.http import HttpResponse, Http404
from django.template.loader import render_to_string
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _
from render_block import render_block_to_string

from core import forms as core_forms
from core import models
from core.parsers import SampleParser

from dart.utils import load_svg
from settingsdb import models as settings_models

import logging

logger = logging.getLogger('dart')
user_logger = logger.getChild('user')


# Form for loading a file, connecting sample, value, flag and replica fields to the SampleType so a user
# doesn't have to constantly re-enter columns. Ultimately the user will select a file, the file type with the
# expected headers for sample and value fields will be used to determine what SampleTypes the file contains
# which will be automatically loaded if they've been previously seen. Otherwise a user will be able to add
# new configurations for sample types.
class SampleTypeConfigForm(forms.ModelForm):
    sample_field = forms.CharField(help_text=_("Column that contains the bottle ids"))
    value_field = forms.CharField(help_text=_("Column that contains the value data"))
    flag_field = forms.CharField(required=False, help_text=_("Column that contains quality flags, if it exists"))
    comment_field = forms.CharField(required=False, help_text=_("Column containing comments, if it exists"))

    NONE_CHOICE = [(None, "------")]

    datatype_filter = forms.CharField(label=_("Filter Datatype"), required=False,
                                      help_text=_("Filter the Datatype field on key terms"))

    class Meta:
        model = settings_models.SampleTypeConfig
        fields = "__all__"

    def __init__(self, database, file_type, field_choices: list = None, *args, **kwargs):

        # To use this form 'field_choices', a list of options the user can select from for the
        # header row, must be passed in to populate the dropdowns. For some reason after the
        # form has been created and populated the 'declared_fields' variable maintains the list
        # of options and can be used when passing a request.GET or request.POST in
        choice_fields = ['sample_field', 'value_field', 'flag_field', 'comment_field']
        if field_choices:
            for field in choice_fields:
                s_field: forms.CharField = self.base_fields[field]
                self.base_fields[field] = forms.ChoiceField(help_text=s_field.help_text, required=s_field.required)
                if not self.base_fields[field].required:
                    self.base_fields[field].choices = self.NONE_CHOICE
                self.base_fields[field].choices += field_choices
        else:
            for field in choice_fields:
                self.base_fields[field] = self.declared_fields[field]

        super().__init__(*args, **kwargs)

        self.helper = FormHelper(self)
        self.helper.form_tag = False
        self.helper.layout = Layout()

        sample_type_choices = [(st.pk, st) for st in settings_models.GlobalSampleType.objects.all().order_by(
            'short_name')]
        sample_type_choices.insert(0, (None, ""))
        sample_type_choices.insert(0, (-1, "New Sample Type"))
        sample_type_choices.insert(0, (None, '---------'))
        self.fields['sample_type'].choices = sample_type_choices

        hx_relaod_form_attributes = {
            'hx-post': reverse_lazy('core:form_sample_config_new', args=(database,)),
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

        url = reverse_lazy('core:form_sample_config_new', args=(database,))
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
            Hidden('file_type', file_type),
            config_name_row,

            Row(
                Column(Field('sample_field')),
                Column(Field('value_field')),
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
            'title': _("Add as new configuration"),
            'hx_get': reverse_lazy("core:form_sample_config_save", args=(database,)),
            'hx_target': "#button_row",
            'hx_select': "#div_id_loaded_sample_type_message",
        }

        button_new = StrictButton(load_svg('plus-square'), **attrs)
        button_row.fields[0].insert(0, button_new)

        if self.instance.pk:
            attrs['hx_get'] = reverse_lazy("core:form_sample_config_save", args=(database, self.instance.pk,))
            attrs['name'] = "update_sample_type"
            attrs['title'] = _("Update existing configuration")
            attrs['css_class'] = 'btn btn-secondary btn-sm ms-2'
            button_update = StrictButton(load_svg('arrow-clockwise'), **attrs)
            button_row.fields[0].insert(0, button_update)

        attrs['hx_get'] = reverse_lazy("core:form_sample_config_load", args=(database,))
        attrs['name'] = "reload"
        attrs['title'] = _("Cancel")
        attrs['css_class'] = 'btn btn-secondary btn-sm ms-2'
        button_cancel = StrictButton(load_svg('x-square'), **attrs)
        button_row.fields[0].insert(0, button_cancel)

        self.helper[0].layout.fields.append(button_row)


def get_upload_button(database):
    soup = BeautifulSoup("", "html.parser")
    load_button = soup.new_tag("button", attrs={'id': 'button_id_load_samples', 'class': "btn btn-primary",
                                                'name': 'upload_samples'})
    icon = BeautifulSoup(load_svg('check-square'), "html.parser").svg
    load_button.append(icon)
    load_button.attrs['hx-get'] = reverse_lazy("core:mission_samples_load_samples", args=(database,))
    load_button.attrs['hx-swap'] = "none"

    return load_button


def get_sample_config_form(database, sample_type, **kwargs):
    if sample_type == -1:
        config_form = render_crispy_form(SampleTypeConfigForm(database=database, file_type="", field_choices=[]))
        soup = BeautifulSoup(config_form, 'html.parser')

        # Drop the current existing dropdown from the form and replace it with a new sample type form
        sample_drop_div = soup.find(id='div_id_sample_type')
        sample_drop_div.attrs['class'] = 'col'

        children = sample_drop_div.findChildren()
        for child in children:
            child.decompose()

        sample_type_form = kwargs['sample_type_form'] if 'sample_type_form' in kwargs else core_forms.SampleTypeForm
        context = {'sample_type_form': sample_type_form, "expanded": True}
        new_sample_form = render_to_string('core/partials/form_sample_type.html', context=context)

        new_form_div = BeautifulSoup(new_sample_form, 'html.parser')
        sample_drop_div.append(new_form_div)

        # add a back button to the forms button_row/button_column
        url = reverse_lazy('core:form_sample_config_new', args=(database,)) + "?sample_type="
        back_button = soup.new_tag('button')
        back_button.attrs = {
            'id': 'id_new_sample_back',
            'class': 'btn btn-primary btn-sm ms-2',
            'name': 'back_sample',
            'hx-target': '#div_id_sample_type',
            'hx-select': '#div_id_sample_type',
            'hx-swap': 'outerHTML',
            'hx-get': url
        }
        icon = BeautifulSoup(load_svg('arrow-left-square'), 'html.parser').svg
        back_button.append(icon)
        sample_drop_div.find(id="div_id_sample_type_button_col").insert(0, back_button)

        # redirect the submit button to this forms save function
        submit_button = sample_drop_div.find(id="button_id_new_sample_type_submit")

        url = reverse_lazy('core:form_sample_config_save', args=(database,))
        submit_button.attrs['hx-target'] = '#div_id_sample_type'
        submit_button.attrs['hx-select'] = '#div_id_sample_type'
        submit_button.attrs['hx-swap'] = 'outerHTML'
        submit_button.attrs['hx-post'] = url
    else:
        config_form = render_crispy_form(SampleTypeConfigForm(database=database, file_type="", field_choices=[],
                                                              initial={'sample_type': sample_type}))
        soup = BeautifulSoup(config_form, 'html.parser')

    return soup


def save_sample_config(request, database, **kwargs):
    # Validate and save the mission form once the user has filled out the details
    #
    # Template: 'core/partials/form_sample_type.html template
    #
    # return the sample_type_block if the sample_type or the file configuration forms fail
    # returns the loaded_samples_block if the forms validate and the objects are created

    if request.method == "GET":
        if 'config_id' in kwargs and 'update_sample_type' in request.GET:
            sample_type = settings_models.SampleTypeConfig.objects.get(pk=kwargs['config_id'])
            url = reverse_lazy("core:form_sample_config_save", args=(database, sample_type.pk,))
            oob_select = f"#div_id_sample_type_holder"
        else:
            url = reverse_lazy("core:form_sample_config_save", args=(database,))
            oob_select = "#div_id_sample_type_holder, #div_id_loaded_samples_list:beforeend"

        attrs = {
            'component_id': "div_id_loaded_sample_type_message",
            'message': _('Saving'),
            'alert_type': 'info',
            'hx-trigger': "load",
            'hx-target': "#div_id_sample_type_holder",
            'hx-post': url,
            'hx-select-oob': oob_select
        }
        soup = core_forms.save_load_component(**attrs)

        return HttpResponse(soup)
    elif request.method == "POST":

        if 'new_sample' in request.POST:
            # if the new_sample_config method requires the user to create a new sample type we'll
            # save the sample_type form here and return the whole sample_config_form with either the
            # new sample type or the config form with the invalid sample_type_form
            sample_form = core_forms.SampleTypeForm(request.POST)
            if sample_form.is_valid():
                sample_type = sample_form.save()
                soup = get_sample_config_form(database, sample_type=sample_type.pk)
                return HttpResponse(soup)

            soup = get_sample_config_form(database, sample_type=-1, sample_type_form=sample_form)
            return HttpResponse(soup)

        # mission_id is a hidden field in the 'core/partials/form_sample_type.html' template, if it's needed
        # mission_id = request.POST['mission_id']

        # I don't know how to tell the user what is going on here if no sample_file has been chosen
        # They shouldn't even be able to view the rest of the form with out it.
        file = request.FILES['sample_file']
        file_name, file_type, data = process_file(file)

        tab = int(request.POST['tab']) if 'tab' in request.POST else 0
        skip = int(request.POST['skip']) if 'skip' in request.POST else 0

        tab, skip, field_choices = SampleParser.get_headers(data, file_type, tab, skip)

        if 'config_id' in kwargs:
            config = settings_models.SampleTypeConfig.objects.get(pk=kwargs['config_id'])
            sample_type_config_form = SampleTypeConfigForm(database, file_type=file_type, field_choices=field_choices,
                                                           data=request.POST, instance=config)
        else:
            sample_type_config_form = SampleTypeConfigForm(database, file_type=file_type, field_choices=field_choices,
                                                           data=request.POST)

        if sample_type_config_form.is_valid():
            sample_config: settings_models.SampleTypeConfig = sample_type_config_form.save()
            # the load form is immutable to the user it just allows them the delete, send for edit or load the
            # sample into the mission
            html = render_to_string('core/partials/card_sample_config.html',
                                    context={'database': database, 'sample_config': sample_config})
            soup = BeautifulSoup(html, 'html.parser')

            div_id = f"div_id_sample_config_card_{sample_config.id}"
            div = soup.find(id=div_id)
            if 'config_id' in kwargs:
                div.attrs['hx-swap-oob'] = f"#{div_id}"
            else:
                new_root = soup.new_tag('div')
                new_root.attrs['id'] = "div_id_loaded_samples_list"
                new_root.attrs['hx-swap-oob'] = 'true'
                new_root.append(div)
                soup.append(new_root)

                upload_btn = get_upload_button(database)
                upload_btn.attrs['hx-swap-oob'] = 'true'
                soup.append(upload_btn)

            return HttpResponse(soup)

        html = render_crispy_form(sample_type_config_form)
        return HttpResponse(html)


def new_sample_config(request, database, **kwargs):
    if request.method == "GET":

        if 'sample_type' in request.GET:
            sample_type = int(request.GET['sample_type']) if request.GET['sample_type'] else 0
            soup = get_sample_config_form(database, sample_type, **kwargs)
            return HttpResponse(soup)

        # return a loading alert that calls this methods post request
        # Let's make some soup
        url = reverse_lazy("core:form_sample_config_new", args=(database,))

        attrs = {
            'component_id': "div_id_loaded_sample_type_message",
            'message': _("Loading"),
            'alert_type': 'info',
            'hx-post': url,
            'hx-target': "#div_id_sample_type_holder",
            'hx-trigger': "load"
        }
        soup = core_forms.save_load_component(**attrs)

        return HttpResponse(soup)
    elif request.method == "POST":

        if 'sample_file' not in request.FILES:
            soup = BeautifulSoup('<div id="div_id_sample_type_holder"></div>', 'html.parser')

            div = soup.new_tag('div')
            div.attrs['class'] = 'alert alert-warning mt-2'
            div.string = _("File is required before adding sample")
            soup.find(id="div_id_sample_type_holder").append(div)
            return HttpResponse(soup)

        file = request.FILES['sample_file']
        file_name, file_type, data = process_file(file)

        if 'config_id' in kwargs:
            config = settings_models.SampleTypeConfig.objects.get(pk=kwargs['config_id'])
            tab, skip, field_choices = SampleParser.get_headers(data, config.file_type, config.tab, config.skip)
            sample_config_form = SampleTypeConfigForm(database, file_type=file_type, field_choices=field_choices,
                                                      instance=config)
        else:
            tab = int(request.POST['tab']) if 'tab' in request.POST else 0
            skip = int(request.POST['skip']) if 'skip' in request.POST else -1
            field_choices = []

            try:
                tab, skip, field_choices = SampleParser.get_headers(data, file_type, tab, skip)
            except Exception as ex:
                logger.exception(ex)
                if isinstance(ex, ValueError):
                    logger.error("Likely chosen tab or header line is outside of the workbook")
                pass

            file_initial = {"skip": skip, "tab": tab}
            if 'sample_type' in kwargs:
                file_initial['sample_type'] = kwargs['sample_type']
            sample_config_form = SampleTypeConfigForm(database, file_type=file_type, field_choices=field_choices,
                                                      initial=file_initial)

        html = render_crispy_form(sample_config_form)
        return HttpResponse(html)


def delete_sample_config(request, **kwargs):
    config_id = kwargs['config_id']
    if request.method == "POST":
        settings_models.SampleTypeConfig.objects.get(pk=config_id).delete()

    return HttpResponse()


def process_file(file) -> [str, str, str]:
    file_name = file.name
    file_type = file_name.split('.')[-1].lower()

    # the file can only be read once per request
    data = file.read()

    return file_name, file_type, data


def load_sample_config(request, database, **kwargs):
    context = {
        'database': database
    }

    if request.method == "GET":
        if 'reload' in request.GET:
            response = HttpResponse()
            response['HX-Trigger'] = 'reload_sample_file'
            return response

        mission_id = request.GET['mission'] if 'mission' in request.GET else None
        loading = 'sample_file' in request.GET

        if loading:
            # Let's make some soup
            url = reverse_lazy("core:form_sample_config_load", args=(database,))

            soup = BeautifulSoup('', "html.parser")

            div_sampletype_holder = soup.new_tag("div")
            div_sampletype_holder.attrs['id'] = "div_id_sample_type_holder"
            div_sampletype_holder.attrs['hx-swap-oob'] = "true"

            div_loaded_sample_types = soup.new_tag("div")
            div_loaded_sample_types.attrs['id'] = "div_id_loaded_samples_list"
            div_loaded_sample_types.attrs['hx-swap-oob'] = "true"

            attrs = {
                'component_id': "div_id_loaded_sample_type_message",
                'message': _("Loading"),
                'alert_type': 'info',
                'hx-post': url,
                'hx-trigger': "load",
                'hx-swap-oob': "#div_id_sample_type_holder",
            }
            dialog_soup = core_forms.save_load_component(**attrs)

            div_sampletype_holder.append(dialog_soup)

            soup.append(div_sampletype_holder)
            soup.append(div_loaded_sample_types)

            return HttpResponse(soup)

        if request.htmx:
            # if this is an htmx request it's to grab an updated element from the form, like the BioChem Datatype
            # field after the Datatype_filter has been triggered.
            sample_config_form = SampleTypeConfigForm(database, file_type="", field_choices=[], initial=request.GET)
            html = render_crispy_form(sample_config_form)
            return HttpResponse(html)

        if mission_id is None:
            raise Http404(_("Mission does not exist"))

        context['mission'] = models.Mission.objects.using(database).get(pk=mission_id)
        html = render_to_string("core/mission_samples.html", request=request, context=context)
        return HttpResponse(html)
    elif request.method == "POST":

        if 'sample_file' not in request.FILES:
            context['message'] = _("File is required before adding sample")
            html = render_block_to_string("core/partials/form_sample_type.html", "sample_type_block", context=context)
            return HttpResponse(html)

        if 'config' in kwargs:
            return new_sample_config(database, request, config=kwargs['config'])

        mission_id = request.POST['mission_id']
        file = request.FILES['sample_file']
        file_name, file_type, data = process_file(file)

        # If mission ID is present this is an initial page load from the sample_file input
        # We want to locate file configurations that match this file_type
        file_configs = SampleParser.get_file_configs(data, file_type)

        soup = BeautifulSoup("", 'html.parser')
        div_sample_type_holder = soup.new_tag("div")
        div_sample_type_holder.attrs['id'] = "div_id_sample_type_holder"
        div_sample_type_holder.attrs['hx-swap-oob'] = 'true'

        soup.append(div_sample_type_holder)

        soup.append(div_sample_type := soup.new_tag("div", id='div_id_loaded_sample_type'))
        div_sample_type.attrs['hx-swap-oob'] = "true"

        file_error_url = reverse_lazy("core:mission_samples_get_file_errors", args=(database, mission_id,))
        file_error_url += f"?file_name={file_name}"
        div_error_list = soup.new_tag('div')
        div_error_list.attrs['id'] = "div_id_error_list"
        div_error_list.attrs['hx-get'] = file_error_url
        div_error_list.attrs['hx-trigger'] = "load, file_errors_updated from:body"
        div_error_list.attrs['class'] = "mt-2"
        div_sample_type.append(div_error_list)

        div_sample_type_list = soup.new_tag("div")
        div_sample_type_list.attrs['id'] = "div_id_loaded_samples_list"
        div_sample_type_list.attrs['class'] = "mt-2"
        div_sample_type.append(div_sample_type_list)

        div_sample_type.append(button_row := soup.new_tag("div", attrs={'class': "row"}))
        button_row.append(soup.new_tag("div", attrs={'class': "col"}))
        button_row.append(button_col := soup.new_tag("div", attrs={'class': "col-auto"}))
        button_col.append(load_button := get_upload_button(database))

        if file_configs:

            for config in file_configs:
                html = render_to_string('core/partials/card_sample_config.html', context={'database': database,
                                                                                          'sample_config': config})
                sample_type = BeautifulSoup(html, 'html.parser')
                div_sample_type_list.append(sample_type.find("div"))
        else:
            load_button.attrs['disabled'] = "disabled"
            attrs = {
                'component_id': "div_id_loaded_samples_alert",
                'message': _("No File Configurations Found"),
                'type': 'info'
            }
            alert_div = core_forms.blank_alert(**attrs)
            soup.find(id="div_id_sample_type_holder").append(alert_div)

        # html = render_block_to_string("core/partials/form_sample_type.html", "loaded_samples_block",
        #                               context=context)
        return HttpResponse(soup)
 
    
url_prefix = "<str:database>/sample_config"
sample_type_config_urls = [
    path(f'{url_prefix}/', load_sample_config, name="form_sample_config_load"),
    path(f'{url_prefix}/<int:config>/', load_sample_config, name="form_sample_config_load"),

    # show the create a sample config form
    path(f'{url_prefix}/new/', new_sample_config, name="form_sample_config_new"),
    path(f'{url_prefix}/new/<int:config_id>/', new_sample_config, name="form_sample_config_new"),

    # save the sample config
    path(f'{url_prefix}/save/', save_sample_config, name="form_sample_config_save"),
    path(f'{url_prefix}/update/<int:config_id>/', save_sample_config, name="form_sample_config_save"),
    path('sample_config/delete/<int:config_id>/', delete_sample_config, name="form_sample_config_delete"),
]
