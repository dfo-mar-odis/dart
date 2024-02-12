from bs4 import BeautifulSoup

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from crispy_forms.utils import render_crispy_form

from django.contrib import messages
from django.template.context_processors import csrf
from django.template.loader import render_to_string
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _
from django.http import HttpResponseRedirect, HttpResponse

from render_block import render_block_to_string

from dart.utils import load_svg

from biochem import models as bio_models
from core import models as core_models, forms
from settingsdb import models as settings_models


import logging
logger = logging.getLogger("dart")


def update_geographic_regions(request):
    soup = BeautifulSoup('', 'html.parser')

    if request.method == "GET":
        if request.GET.get("global_geographic_region", "-1") == '-1':
            row = soup.new_tag('div')
            row.attrs['class'] = 'container-fluid row'

            geo_region_input = soup.new_tag('input')
            geo_region_input.attrs['name'] = 'geographic_region'
            geo_region_input.attrs['id'] = 'id_global_geographic_region_input'
            geo_region_input.attrs['type'] = 'text'
            geo_region_input.attrs['class'] = 'textinput form-control form-control-sm col'

            submit = soup.new_tag('button')
            submit.attrs['class'] = 'btn btn-primary btn-sm ms-2 col-auto'
            submit.attrs['hx-post'] = request.path
            submit.attrs['hx-target'] = '#id_global_region_field'
            submit.attrs['hx-select'] = '#id_global_region_field'
            submit.attrs['hx-swap'] = 'outerHTML'
            submit.append(BeautifulSoup(load_svg('plus-square'), 'html.parser').svg)

            row.append(geo_region_input)
            row.append(submit)

            soup.append(row)

            return HttpResponse(soup)

        mission_form = forms.MissionSettingsForm(request.GET)
        html = render_crispy_form(mission_form)
        soup = BeautifulSoup(html, "html.parser")
        geo_region = soup.find(id="id_global_geographic_region")

        return HttpResponse(geo_region.prettify())

    elif request.method == "POST":
        mission_dict = request.POST.copy()
        if 'geographic_region' in request.POST and (region_name := request.POST['geographic_region'].strip()):
            if (region := settings_models.GlobalGeographicRegion.objects.filter(name=region_name)).exists():
                mission_dict['global_geographic_region'] = region[0].id
            else:
                region = settings_models.GlobalGeographicRegion(name=region_name)
                region.save()
                mission_dict['global_geographic_region'] = region.pk

        mission_form = forms.MissionSettingsForm(initial=mission_dict)
        html = render_crispy_form(mission_form)

        form_soup = BeautifulSoup(html, 'html.parser')
        geographic_select = form_soup.find(id="id_global_region_field")

        soup.append(geographic_select)
        return HttpResponse(soup)


htmx_urls = [
    path('update_regions/', update_geographic_regions, name="hx_update_regions"),
]
