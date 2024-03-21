from bs4 import BeautifulSoup
from crispy_forms.utils import render_crispy_form
from django.http import Http404, HttpResponse
from django.template.loader import render_to_string
from django.urls import path
from django.utils.translation import gettext as _
from django.views.generic import TemplateView
from render_block import render_block_to_string

from dart.views import GenericViewMixin
from core import models as core_models
from core import forms

from settingsdb import models as settings_models

import logging

logger = logging.getLogger('dart')


class SampleTypeList(GenericViewMixin, TemplateView):
    model = settings_models.GlobalSampleType
    page_title = _("Standard Sample Types")
    template_name = 'core/sample_settings.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['sample_type_form'] = forms.SampleTypeForm()
        context['sample_types'] = settings_models.GlobalSampleType.objects.all()

        return context


def new_sample_type(request, **kwargs):
    response = None
    if request.method == "GET":
        if request.htmx:
            # if this is an htmx request it's to grab an updated element from the form, like the BioChem Datatype
            # field after the Datatype_filter has been triggered.
            sample_type_form = forms.SampleTypeForm(initial=request.GET)
            html = render_crispy_form(sample_type_form)
            return HttpResponse(html)

        html = render_crispy_form(forms.SampleTypeForm())
        response = HttpResponse(html)

    return response


def load_sample_type(request, **kwargs):
    if request.method == "GET":
        if 'sample_type_id' not in kwargs or not kwargs['sample_type_id']:
            raise Http404("Sample Type does not exist")

        context = {'sample_type': settings_models.GlobalSampleType.objects.get(pk=kwargs['sample_type_id'])}
        html = render_to_string(template_name='core/partials/card_sample_type.html', context=context)

        return HttpResponse(html)


def edit_sample_type(request, **kwargs):
    if request.method == "GET":
        if 'sample_type_id' not in kwargs or not kwargs['sample_type_id']:
            sample_type_form = forms.SampleTypeForm()

            html = render_to_string('core/partials/form_sample_type.html',
                                    context={'sample_type_form': sample_type_form, 'expanded': True})
            response = HttpResponse(html)
            return response

        sample_type = settings_models.GlobalSampleType.objects.get(pk=kwargs['sample_type_id'])
        sample_type_form = forms.SampleTypeForm(instance=sample_type)

        html = render_to_string('core/partials/form_sample_type.html', context={'sample_type_form': sample_type_form,
                                                                                'sample_type': sample_type,
                                                                                'expanded': True})
        response = HttpResponse(html)
        return response


def delete_sample_type(request, sample_type_id):

    settings_models.GlobalSampleType.objects.get(pk=sample_type_id).delete()
    return HttpResponse()


def save_sample_type(request, **kwargs):

    if request.method == "POST":
        if 'sample_type_id' in kwargs:
            sample_type = settings_models.GlobalSampleType.objects.get(pk=kwargs['sample_type_id'])
            sample_type_form = forms.SampleTypeForm(request.POST, instance=sample_type)
        else:
            sample_type_form = forms.SampleTypeForm(request.POST)

        if not sample_type_form.is_valid():
            html = render_to_string('core/partials/form_sample_type.html',
                                    context={'sample_type_form': sample_type_form})
            response = HttpResponse(html)
            return response

        sample_type = sample_type_form.save()
        html = render_to_string('core/partials/form_sample_type.html',
                                context={'sample_type_form': forms.SampleTypeForm()})

        context = {'sample_types': [sample_type]}
        html += render_block_to_string(template_name='core/sample_settings.html',
                                       block_name="loaded_samples", context=context)
        response = HttpResponse(html)
        return response


# ###### SAMPLE TYPES AND FILE CONFIGURATIONS ###### #
sample_type_urls = [
    # show the create a sample type form
    path('sample_type/', SampleTypeList.as_view(), name="sample_type_details"),
    path('sample_type/hx/new/', new_sample_type, name="sample_type_new"),
    path('sample_type/hx/save/', save_sample_type, name="sample_type_save"),
    path('sample_type/hx/save/<int:sample_type_id>/', save_sample_type, name="sample_type_save"),
    path('sample_type/hx/load/<int:sample_type_id>/', load_sample_type, name="sample_type_load"),
    path('sample_type/hx/edit/', edit_sample_type, name="sample_type_edit"),
    path('sample_type/hx/edit/<int:sample_type_id>/', edit_sample_type, name="sample_type_edit"),
    path('sample_type/hx/delete/<int:sample_type_id>/', delete_sample_type, name="sample_type_delete"),
]