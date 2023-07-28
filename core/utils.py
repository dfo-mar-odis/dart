import json

from django.contrib import messages
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.http import JsonResponse, HttpResponseRedirect, HttpResponse

from render_block import render_block_to_string

from biochem import models
from core import models

import logging

logger = logging.getLogger("dart")


def mission_delete(request):
    if "mission" in request.GET:
        m = models.Mission.objects.get(pk=request.GET["mission"])
        m.delete()

    messages.success(request=request, message=_("Mission Deleted"))
    return HttpResponseRedirect(reverse_lazy("core:mission_filter"))


def update_geographic_regions(request):
    regions = models.GeographicRegion.objects.all().order_by("pk")
    selected = regions.last()
    regions.order_by('name')
    context = {'geographic_regions': regions, 'selected': selected.pk}

    html = render(request, 'core/partials/geographic_region.html', context)
    return HttpResponse(html)


def add_geo_region(request):
    region_name = request.POST.get('new_region')

    if region_name is None or region_name.strip() == "":
        message = _("could not create geographic region, no name provided")
        logger.error(message)

        html = render_block_to_string('core/mission_settings.html', 'geographic_region_block')
        # TODO: This should be replaced with a notification using Django Channels
        return HttpResponse(html)

    regs = models.GeographicRegion.objects.filter(name=region_name)

    if not regs.exists():
        region = models.GeographicRegion(name=region_name)
        region.save()

        regs = models.GeographicRegion.objects.filter(name=region_name)

    html = render_block_to_string('core/mission_settings.html', 'geographic_region_form')
    response = HttpResponse(html)
    response['HX-Trigger'] = "region_added"

    return response
