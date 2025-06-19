import re

from bs4 import BeautifulSoup

from django import forms
from django.utils.text import normalize_newlines
from django.utils.translation import gettext as _
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import reverse, path

from config.utils import load_svg
from dart import models
from user_settings import models as user_models
from config import utils, components

import logging

logger = logging.getLogger('dart')
user_logger = logging.getLogger('dart.user')


class MissionSettingsForm(forms.ModelForm):

    data_center = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True,

    )

    class Meta:
        model = models.Mission
        fields = ['name', 'mission_descriptor', 'start_date', 'end_date', 'geographic_region', 'lead_scientist',
                  'platform', 'protocol', 'collector_comments', 'data_manager_comments', 'data_center']

        widgets = {
            'start_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'max': '9999-12-31'
            }),
            'end_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'max': '9999-12-31'
            }),
            'geographic_region': forms.HiddenInput(),
            'collector_comments': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'data_manager_comments': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }

    def clean_lead_scientist(self):
        cleaned_data = super().clean()
        lead_scientist = cleaned_data.get('lead_scientist')
        if lead_scientist:
            # Require at least one character for last and first name, separated by a comma and optional space
            if not re.match(r'^[^,]+,\s*[^,]+$', lead_scientist):
                raise ValidationError("Lead scientist name must be in the format 'last name, first name'.")

        return lead_scientist

    def clean_name(self):
        name = self.cleaned_data['name']
        if not re.match(r'^\w+$', name):
            raise ValidationError("Mission name can only contain letters, numbers, and underscores.")
        return name

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        if start_date and end_date and start_date > end_date:
            raise ValidationError({'start_date': "Start date cannot be after end date."})
        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['data_center'].choices = [(20, 'BIO'), (30, 'GEO'), (40, 'MET'), (50, 'OCE'), (60, 'PHY')]


def get_db_name(name: str) -> str:
    return f'DART_{name}'


def get_form_soup(request, **kwargs) -> tuple[bool, models.Mission, BeautifulSoup]:
    form_context = {}
    valid = False
    mission = None
    if 'mission' in kwargs:
        user_logger.info("Update new mission database")
        mission = kwargs['mission']
        form = MissionSettingsForm(request.POST or None, instance=mission)
        form_context['object'] = mission
    else:
        user_logger.info("Creating new mission database")
        form = MissionSettingsForm(request.POST or None)

    form_context['form'] = form
    if form.is_valid():
        if mission is None:
            db_name = get_db_name(request.POST.get('name', '').strip())
            utils.create_database(db_name)

        valid = True
        mission = form.save()
        form_context['object'] = mission

    form_html = render_to_string('dart/forms/mission_settings_form.html', form_context)
    form_soup = BeautifulSoup(form_html, 'html.parser')
    mission_form = form_soup.find(id="form_id_mission")
    mission_form.attrs['hx-swap-oob'] = "true"

    return valid, mission if mission else -1, form_soup


def new_mission(request, **kwargs):
    soup = BeautifulSoup('', 'html.parser')
    if request.method == "GET":
        soup.append(soup.new_tag("div", id="form_id_mission_hidden_submit",
                                 attrs={'hx-swap': 'none',
                                        'hx-post': request.path,
                                        'hx-swap-oob': 'true',
                                        'hx-trigger': 'load'}))
        soup.append(components.websocket_modal(
            title="New Mission",
            logger_name=user_logger.name
        ))
        return HttpResponse(soup)

    try:
        valid, mission, form_soup = get_form_soup(request, **kwargs)
        if valid:
            db_name = get_db_name(request.POST.get('name', '').strip())
            response = HttpResponse()
            response['HX-Redirect'] = reverse('dart:mission_update',
                                              kwargs={'database': db_name, 'mission_id': mission.pk})
            return response
        else:
            response = HttpResponse(form_soup)
            response['HX-Trigger'] = 'closeModal'
    except Exception as e:
        logger.exception(e)
        soup.append(components.modal(
            title=str(e),
            completion=components.completed.failure,
            swap_oob=True
        ))
        response = HttpResponse(soup)

    return response


def update_mission(request, mission_id, **kwargs):
    soup = BeautifulSoup('', 'html.parser')
    if request.method == "GET":
        soup.append(soup.new_tag("div", id="form_id_mission_hidden_submit",
                                 attrs={'hx-swap': 'none', 'hx-post': request.path, 'hx-swap-oob': 'true',
                                        'hx-trigger': 'load'}))
        return HttpResponse(soup)

    mission = models.Mission.objects.get(pk=mission_id)
    valid, pk, form_soup = get_form_soup(request, mission=mission, **kwargs)
    soup.append(form:=form_soup.find(id="form_id_mission"))
    form.attrs['hx-swap'] = 'outerHTML'
    return HttpResponse(soup)


def get_region_button(soup, region):
    column = soup.new_tag('div')
    column.attrs['class'] = 'col-auto me-2'

    column.append(badge:=soup.new_tag('span'))
    badge.attrs['class'] = 'badge bg-secondary'
    badge.string = region

    dash_icon = BeautifulSoup(load_svg("dash-square"), "html.parser")
    badge.append(button:=soup.new_tag('button', type='button'))
    button.attrs['class'] = "btn btn-danger btn-sm ms-1"
    button.attrs['hx-post'] = reverse("dart:form_mission_delete_geographic_region")
    button.attrs['hx-confirm'] = _("Are you sure?")
    button.attrs['title'] = _("Delete selected region(s)")
    button.attrs['name'] = 'delete'
    button.attrs['value'] = region

    button.append(dash_icon)

    return column


def get_region_list(selected=None):

    regions = user_models.GlobalGeographicRegion.objects.all().order_by('name')

    html = render_to_string('dart/forms/components/field_geographic_region.html')
    select_soup = BeautifulSoup(html, 'html.parser')
    select = select_soup.find('select', id='global_geographic_region_select')
    select.attrs['hx-get'] = reverse('dart:form_mission_new_geographic_region')
    select.attrs['hx-trigger'] = 'change'
    select.attrs['hx-swap-oob'] = 'true'
    select.attrs['hx-swap'] = 'none'

    option = select_soup.new_tag('option', value="0")
    option.string = _("New")
    select.append(option)

    for region in regions:
        option = select_soup.new_tag('option', value=region.pk)
        option.string = region.name
        if selected and region.pk == selected:
            option.attrs['selected'] = 'selected'
        select.append(option)

    return select_soup


def list_geographic_regions(request, **kwargs):
    soup = BeautifulSoup('', 'html.parser')
    if request.method == "GET":
        soup.append(get_region_list())
        response = HttpResponse(soup)
        response['HX-Trigger'] = 'update_regions'
        return response

    return HttpResponse("Invalid request method.", status=405)


def new_geographic_regions(request, **kwargs):
    soup = BeautifulSoup('', 'html.parser')
    if request.method == "GET" and request.GET.get('global_geographic_region') == '0':
        context = {
            'field_swap_id': "div_id_global_geographic_region_select",
            'field_name': 'new_global_region',
            'add_url': reverse('dart:form_mission_new_geographic_region'),
            'cancel_url': reverse('dart:form_mission_list_geographic_regions'),
        }
        html = render_to_string('dart/forms/components/field_new_option.html', context)
        soup.append(BeautifulSoup(html, 'html.parser'))
    elif request.method == "POST":
        region = None
        if 'new_global_region' in request.POST and (region_name := request.POST['new_global_region'].strip()):
            region = user_models.GlobalGeographicRegion.objects.get_or_create(name=region_name)[0]

        region_id = region.pk if region else int(request.POST.get('global_geographic_region', -1) or -1)
        region_str = request.POST.get('geographic_region', '')
        regions = list(set([region.strip() for region in region_str.split(',') if region]))

        too_many_regions_err = ''
        if region_id > 0:
            region_to_add = user_models.GlobalGeographicRegion.objects.get(pk=region_id).name

            for region in region_to_add.split(', '):
                if region not in regions:
                    if len(regions) + 1 > 4:
                        too_many_regions_err = _("Maximum of four regions")
                    elif len(region_str + ', ' + region) > 100:
                        str_len = len(region_str + ', ' + region)
                        too_many_regions_err = _("Too many characters in region list") + f" : {str_len}"
                    else:
                        regions.append(region)

        if len(regions) > 4:
            too_many_regions_err = _("Maximum of four regions")
        elif len(region_str) > 100:
            too_many_regions_err = _("Too many characters in region list") + f" : {len(region_str)}"

        regions.sort(key=str.lower)
        new_regions = ", ".join(regions)

        initial = {
            'geographic_region': new_regions,
        }
        form = MissionSettingsForm(initial=initial)

        form_html = render_to_string('dart/forms/mission_settings_form.html', {'form': form})
        form_soup = BeautifulSoup(form_html, 'html.parser')

        region_field = form_soup.find(id="div_id_geographic_region_section")

        if too_many_regions_err:
            region_input = region_field.find("input", id="id_geographic_region")
            region_input.attrs['class'] = "form-control is-invalid"
            region_errors = region_field.find("div", id="div_id_geographic_region_errors")
            region_errors.string = too_many_regions_err

        geo_region_row = region_field.find("div", id="div_id_geographic_regions_row")
        for region in regions:
            geo_region_row.append(get_region_button(soup, region))

        soup.append(region_field)

    response = HttpResponse(soup)
    response['HX-Trigger'] = 'update_regions'
    return response


def delete_geographic_region(request):
    region_id = request.POST.get('global_geographic_region', -1)
    selected_regions = request.POST.get('geographic_region', None)

    soup = BeautifulSoup('', 'html.parser')

    initial = {
    }

    if (regions:= user_models.GlobalGeographicRegion.objects.filter(pk=region_id)).exists():
        regions = regions.first()
        regions.delete()

    if selected_regions:
        selected_regions = selected_regions.split(',')
        if 'delete' in request.POST:
            selected_regions = [x.strip() for x in selected_regions if x.strip() != request.POST['delete']]
        selected_regions.sort()

        initial['geographic_region'] = ','.join(selected_regions)

    form = MissionSettingsForm(initial=initial)
    form_html = render_to_string('dart/forms/mission_settings_form.html', {'form': form})
    form_soup = BeautifulSoup(form_html, 'html.parser')

    region_field = form_soup.find(id="div_id_geographic_region_section")
    geo_region_row = region_field.find("div", id="div_id_geographic_regions_row")
    if selected_regions:
        for region in selected_regions:
            geo_region_row.append(get_region_button(soup, region))

    soup.append(region_field)
    response = HttpResponse(soup)
    response['HX-Trigger'] = 'update_regions'
    return response


def show_selected_regions(request, **kwargs):
    selected_regions = request.POST.get('geographic_region', None)

    soup = BeautifulSoup('', 'html.parser')

    form = MissionSettingsForm(initial={"geographic_region": selected_regions})
    form_html = render_to_string('dart/forms/mission_settings_form.html', {'form': form})
    form_soup = BeautifulSoup(form_html, 'html.parser')

    geo_region_row = form_soup.find("div", id="div_id_geographic_regions_row")

    if selected_regions:
        for region in selected_regions.split(','):
            geo_region_row.append(get_region_button(soup, region.strip()))

    soup.append(geo_region_row)
    return HttpResponse(soup)


urlpatterns = [
    path('mission/new_mission/', new_mission, name='form_mission_new_mission'),
    path('mission/<int:mission_id>/', update_mission, name='form_mission_update_mission'),
    path('mission/global_geographic_regions/list/', list_geographic_regions, name='form_mission_list_geographic_regions'),
    path('mission/geographic_regions/list/', show_selected_regions, name='form_mission_show_selected_geographic_regions'),
    path('mission/geographic_regions/new/', new_geographic_regions, name='form_mission_new_geographic_region'),
    path('mission/geographic_regions/delete/', delete_geographic_region, name='form_mission_delete_geographic_region'),
]
