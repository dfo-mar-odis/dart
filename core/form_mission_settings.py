import datetime
import os

from bs4 import BeautifulSoup
from crispy_forms.bootstrap import StrictButton
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, HTML, Hidden, Field, Submit, Layout, Row, Div
from crispy_forms.utils import render_crispy_form
from django import forms
from django.conf import settings
from django.http import HttpResponse
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _

from git import Repo

from core import models
from core.form_biochem_pre_validation import BIOCHEM_CODES
from core.forms import NoWhiteSpaceCharField
from config.utils import load_svg
from settingsdb import models as settings_models, utils as settings_utils


class MissionSettingsForm(forms.ModelForm):

    name = NoWhiteSpaceCharField(max_length=50, label="Mission Name", required=True)
    mission_descriptor = NoWhiteSpaceCharField(max_length=50, required=False)
    global_geographic_region = forms.ChoiceField(label=_("Geographic Region"))

    start_date = forms.DateField(widget=forms.DateInput(
        attrs={'type': 'date', 'max': "9999-12-31",
               'value': datetime.datetime.now().strftime("%Y-%m-%d")}))
    end_date = forms.DateField(widget=forms.DateInput(
        attrs={'type': 'date', 'max': "9999-12-31",
               'value': datetime.datetime.now().strftime("%Y-%m-%d")}))

    class Meta:
        model = models.Mission
        fields = ['name', 'description', 'geographic_region', 'mission_descriptor', 'data_center', 'lead_scientist',
                  'start_date', 'end_date', 'platform', 'protocol', 'collector_comments', 'data_manager_comments',
                  'start_underway_sample', 'end_underway_sample']

    @property
    def get_btn_add(self):
        btn_attrs = {
            'hx-post': reverse_lazy("core:form_mission_settings_add_region"),
            'hx-target': "#div_id_geographic_region_card_body",
            'hx-swap': 'outerHTML',
            'title': _("Add selected region(s) to mission")
        }
        btn_add_icon = BeautifulSoup(load_svg('plus-square'), 'html.parser').svg
        return StrictButton(btn_add_icon, css_class="btn btn-success", **btn_attrs)

    @property
    def get_btn_delete(self):
        del_btn_attrs = {
            'hx-post': reverse_lazy("core:form_mission_settings_delete_region"),
            'hx-confirm': _("Are you sure?"),
            'hx-target': "#div_id_geographic_region_card_body",
            'hx-swap': 'outerHTML',
            'title': _("Delete selected region(s)")
        }
        btn_del_icon = BeautifulSoup(load_svg('dash-square'), 'html.parser').svg
        return StrictButton(btn_del_icon, css_class="btn btn-danger", **del_btn_attrs)

    def get_region_button(self, region_name):
        global_region = settings_models.GlobalGeographicRegion.objects.get_or_create(name=region_name)[0]
        btn_attrs = {
            'hx-post': reverse_lazy("core:form_mission_settings_remove_region", args=(global_region.pk,)),
            'hx-target': "#div_id_geographic_region_field",
            'title': _("Remove Region")
        }
        button = Div(HTML("-"), name="remove_geographic_region", value=f"{global_region.pk}",
                     css_class="badge bg-danger", **btn_attrs)
        return button

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_show_labels = True
        self.fields['global_geographic_region'].widget.attrs["hx-swap"] = 'outerHTML'
        self.fields['global_geographic_region'].widget.attrs["hx-trigger"] = 'change'
        self.fields['global_geographic_region'].widget.attrs["hx-target"] = "#id_global_geographic_region"
        self.fields['global_geographic_region'].widget.attrs["hx-get"] = reverse_lazy('core:form_mission_settings_update_regions')
        self.fields['global_geographic_region'].choices = [(None, '------')]
        region_choices = settings_models.GlobalGeographicRegion.objects.all().order_by('name')
        self.fields['global_geographic_region'].choices += [(gr.id, gr) for gr in region_choices]
        self.fields['global_geographic_region'].choices += [(-2, _('')), (-1, _('New Region'))]
        self.fields['global_geographic_region'].required = False

        self.fields['mission_descriptor'].required = False
        self.fields['lead_scientist'].required = False
        self.fields['data_center'].required = False

        if self.instance.pk:
            name_column = Column(
                HTML(f"<h2>{self.instance.name}</h2>"),
                Hidden('name', self.instance.name)
            )
            self.fields['start_date'].widget.attrs['value'] = self.instance.start_date.strftime("%Y-%m-%d")
            self.fields['end_date'].widget.attrs['value'] = self.instance.end_date.strftime("%Y-%m-%d")
        else:
            name_column = Column(Field('name', autocomplete='true'))

        if (start_date := self.initial.get("start_date", -1)) != -1:
            self.fields['start_date'].widget.attrs['value'] = start_date.strftime("%Y-%m-%d")

        if (end_date := self.initial.get("end_date", -1)) != -1:
            self.fields['end_date'].widget.attrs['value'] = end_date.strftime("%Y-%m-%d")

        multi_select_help_text = _("One to four geographic regions. Combined text length may not exceed 100 characters")
        multi_select_field = Row(id="div_id_geographic_region_field", css_class='d-flex align-self-stretch align-items-center')
        multi_select_field.fields.append(multi_select_col := Div(css_class=''))

        button_row = Row(css_class="bg-light border")
        regions = None
        if 'geographic_region' in self.errors:
            multi_select_col.fields.append(HTML(self.errors['geographic_region'][0]))
        elif self.initial.get("geographic_region"):
            multi_select_col.fields.append(button_row)
            region_str = self.initial.get("geographic_region", '')
            multi_select_col.fields.append(Hidden("geographic_region", region_str))
            regions = list(set([region.strip() for region in region_str.split(',') if region]))
            regions.sort()
            # make sure regions exist in the global table if they're loaded from a mission
            for region in regions:
                button_row.fields.append(Column(Div(
                    HTML(f'<span class="me-2">{region}</span>'),
                    self.get_region_button(region),
                    css_class="btn btn-outline-secondary"),
                    css_class="col-auto")
                )

        # if there's a validation error for a missing mission descriptor, highlight this field
        descriptor_field = Field('mission_descriptor')
        start_date_field = Field('start_date')
        end_date_field = Field('end_date')
        if self.instance.pk:
            if models.MissionError.objects.filter(
                    code=BIOCHEM_CODES.DESCRIPTOR_MISSING.value).exists():
                descriptor_field.attrs['class'] = descriptor_field.attrs.get('class', "") + " bg-danger-subtle"

            date_issues = [BIOCHEM_CODES.DATE_MISSING.value, BIOCHEM_CODES.DATE_BAD_VALUES.value]
            # if there's an issue with the dates highlight the date fields
            if models.MissionError.objects.filter(code__in=date_issues).exists():
                start_date_field.attrs['class'] = start_date_field.attrs.get('class', "") + " bg-danger-subtle"
                end_date_field.attrs['class'] = end_date_field.attrs.get('class', "") + " bg-danger-subtle"

        submit = Submit('submit', 'Submit')

        self.helper.layout = Layout(
            Row(
                Column(name_column),
            ),
            Row(
                Column(Field('description')),
            ),
            Row(
                Column(
                    start_date_field
                ),
                Column(
                    end_date_field
                )
            ),
            Div(
                Div(
                    Row(
                        Column(
                            Field('global_geographic_region')
                        ),
                        Column(
                            self.get_btn_delete,
                            css_class='col-auto align-self-end mb-3'
                        ),
                        id="id_global_region_field"
                    ),
                    Row(
                        Column(self.get_btn_add, css_class="col-auto align-self-center"),
                        Column(
                            multi_select_field,
                            css_class="border me-2 d-flex" + (" bg-danger-subtle" if regions is None and 'geographic_region' in self.errors else " bg-light")
                        ),
                        css_class="mb-2"
                    ),
                    Row(Column(HTML(f'<span class="text-secondary">{multi_select_help_text}</span>'))),
                    css_class="card-body",
                    id="div_id_geographic_region_card_body"
                ),
                css_class="card mb-2",
                id="div_id_geographic_region_card"
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
                        Column(descriptor_field),
                        Column(Field('lead_scientist')),
                    ),
                    Row(
                        Column(Field('platform')),
                        Column(Field('protocol')),
                    ),
                    Row(
                        Column(Field('data_center')),
                    ),
                    Row(Field('collector_comments')),
                    Row(Field('data_manager_comments')),
                    Row(
                        Column(Field('start_underway_sample')),
                        Column(Field('end_underway_sample')),
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

    def clean_name(self):

        mission_name = self.cleaned_data['name']
        db_name = f'{mission_name}.sqlite3'
        if mission_name not in settings.DATABASES:
            # if the mission_name is already in the settings.Databases, it's a connected
            # database that's being updated, otherwise we want to use the new naming convention.
            db_name = f'DART_{mission_name}.sqlite3'

        if settings_models.LocalSetting.objects.filter(connected=True).exists():
            db_settings = settings_models.LocalSetting.objects.filter(connected=True).first()
        else:
            db_settings = settings_models.LocalSetting.objects.first()

        location = db_settings.database_location
        if location.startswith("./"):
            location = os.path.join(settings.BASE_DIR, location.replace("./", ""))

        if self.instance.pk:
            # if there's an instance with this object we're updating an existing database
            # allow the name within the database to be changed
            return mission_name

        # if there's no database, do not allow a name of an existing database to be used
        database_location = os.path.join(location, db_name)
        if os.path.exists(database_location):
            message = _("A Mission Database with this name already exists in the mission directory")
            message += f" : '{location}'"
            raise forms.ValidationError(message)

        return mission_name

    def clean_geographic_region(self):
        region = self.cleaned_data['geographic_region']
        if not region:
            raise forms.ValidationError(_("Mission requires at least one geographic region"))

        return self.cleaned_data['geographic_region']

    def clean(self):
        cleaned_data = super().clean()
        start_sample = cleaned_data.get('start_underway_sample')
        end_sample = cleaned_data.get('end_underway_sample')

        if bool(start_sample) != bool(end_sample):  # XOR logic: one is provided but not the other
            raise forms.ValidationError(
                _("Both 'Start Underway Sample' and 'End Underway Sample' must be provided, or neither.")
            )
        elif bool(start_sample) and bool(end_sample) and start_sample > end_sample:
            raise forms.ValidationError(
                _("The 'End Underway Sample' must be greater than or equal to the 'Start Underway Sample'.")
            )

        return cleaned_data

    def save(self, commit=True):
        mission_name = self.cleaned_data['name']
        database_name = mission_name
        if 'mission_db' not in settings.DATABASES:
            # if the mission_name is already in the settings.Databases, it's a connected
            # database that's being updated, otherwise we want to use the new naming convention.
            database_name = f'DART_{mission_name}'

            # if we're already connected then we don't want to run migrations and apply fixtures to the db
            if mission_name not in settings.DATABASES:
                settings_utils.add_database(database_name)

        repo = Repo(settings.BASE_DIR)
        instance: models.Mission = super().save(commit=False)

        instance.dart_version = repo.head.commit.hexsha
        instance.save()

        return instance


def update_geographic_regions(request):
    soup = BeautifulSoup('', 'html.parser')

    if request.method == "GET":
        if request.GET.get("global_geographic_region", "-1") == '-1':
            row = soup.new_tag('div')
            row.attrs['class'] = 'row mb-2'
            row.attrs['id'] = 'id_global_geographic_region'
            row.append(col1 := soup.new_tag('div'))
            col1.attrs['class'] = 'col'

            geo_region_input = soup.new_tag('input')
            geo_region_input.attrs['name'] = 'new_global_region'
            geo_region_input.attrs['id'] = 'id_global_geographic_region_input'
            geo_region_input.attrs['type'] = 'text'
            geo_region_input.attrs['class'] = 'textinput form-control col'
            geo_region_input.attrs['placeholder'] = _("Enter a new region name or comma separated list of regions")

            col1.append(geo_region_input)

            soup.append(row)

            return HttpResponse(soup)

        mission_form = MissionSettingsForm(request.GET)
        html = render_crispy_form(mission_form)
        soup = BeautifulSoup(html, "html.parser")
        geo_region = soup.find(id="id_global_geographic_region")

        return HttpResponse(geo_region.prettify())

    elif request.method == "POST":
        region = None
        if 'new_global_region' in request.POST and (region_name := request.POST['new_global_region'].strip()):
            region = settings_models.GlobalGeographicRegion.objects.get_or_create(name=region_name)[0]

        mission_form = MissionSettingsForm(initial={'global_geographic_region': region.pk})
        html = render_crispy_form(mission_form)

        form_soup = BeautifulSoup(html, 'html.parser')
        geographic_select = form_soup.find(id="id_global_geographic_region")
        geographic_select.attrs.pop('hx-get')
        geographic_select.attrs['hx-post'] = reverse_lazy("core:form_mission_settings_add_region")
        geographic_select.attrs['hx-trigger'] = "load"
        geographic_select.attrs['hx-target'] = "#div_id_geographic_region_card_body"
        geographic_select.attrs['hx-swap'] = "outerHTML"

        soup.append(geographic_select)
        return HttpResponse(soup)


def remove_geographic_region(request, region_id):

    region_to_remove = settings_models.GlobalGeographicRegion.objects.get(pk=region_id)
    regions = [region.strip() for region in request.POST.get('geographic_region').split(',') if
               region.strip().lower() != region_to_remove.name.lower()]
    new_regions = ", ".join(regions)

    form = MissionSettingsForm(initial={'geographic_region': new_regions})
    form_html = render_crispy_form(form)
    form_soup = BeautifulSoup(form_html, 'html.parser')

    return HttpResponse(form_soup.find(id="div_id_geographic_region_field"))


def add_geographic_region(request):

    soup = BeautifulSoup('', 'html.parser')
    region = None
    if 'new_global_region' in request.POST and (region_name := request.POST['new_global_region'].strip()):
        region = settings_models.GlobalGeographicRegion.objects.get_or_create(name=region_name)[0]

    region_id = region.pk if region else int(request.POST.get('global_geographic_region', -1) or -1)
    region_str = request.POST.get('geographic_region', '')
    regions = list(set([region.strip() for region in region_str.split(',') if region]))

    too_many_regions_err = ''
    if region_id > 0:
        region_to_add = settings_models.GlobalGeographicRegion.objects.get(pk=region_id)

        if region_to_add.name not in regions:
            if len(regions) + len(region_to_add.name.split(',')) > 4:
                too_many_regions_err = _("Maximum of four regions")
            elif len(region_str + ', ' + region_to_add.name) > 100:
                str_len = len(region_str + ', ' + region_to_add.name)
                too_many_regions_err = _("Too many characters in region list") + f" : {str_len}"
            else:
                regions.append(region_to_add.name)

    regions.sort()
    new_regions = ", ".join(regions)

    initial = {
        'geographic_region': new_regions,
        'global_geographic_region': region_id
    }
    form = MissionSettingsForm(initial=initial)
    form_html = render_crispy_form(form)
    form_soup = BeautifulSoup(form_html, 'html.parser')

    region_field = form_soup.find(id="div_id_geographic_region_card_body")
    # region_field.attrs['hx-swap-oob'] = "outerHTML"
    if too_many_regions_err:
        region_field.append(div_row := form_soup.new_tag('div', attrs={'class': 'row'}))
        div_row.append(div := form_soup.new_tag('div', attrs={'class': 'col alert alert-warning'}))
        div.string = too_many_regions_err

    soup.append(region_field)
    return HttpResponse(soup)


def delete_geographic_region(request):
    region_id = request.POST.get('global_geographic_region', -1)
    selected_regions = request.POST.get('geographic_region', None)

    soup = BeautifulSoup('', 'html.parser')

    initial = {
    }

    regions = settings_models.GlobalGeographicRegion.objects.get(pk=region_id)

    if selected_regions:
        selected_regions = selected_regions.split(',')
        selected_regions.sort()
        initial['geographic_region'] = ','.join(selected_regions)

    regions.delete()

    form = MissionSettingsForm(initial=initial)
    form_html = render_crispy_form(form)
    form_soup = BeautifulSoup(form_html, 'html.parser')

    region_field = form_soup.find(id="div_id_geographic_region_card_body")

    soup.append(region_field)
    return HttpResponse(soup)



mission_urls = [
    path(f'add_region/', add_geographic_region, name="form_mission_settings_add_region"),
    path(f'remove_region/<int:region_id>/', remove_geographic_region, name="form_mission_settings_remove_region"),
    path(f'delete_region/', delete_geographic_region, name="form_mission_settings_delete_region"),
    path('update_regions/', update_geographic_regions, name="form_mission_settings_update_regions"),
]