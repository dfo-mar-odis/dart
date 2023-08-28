from bs4 import BeautifulSoup
from django.http import Http404, HttpResponse
from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from django.views.generic import TemplateView
from render_block import render_block_to_string

from dart2.views import GenericViewMixin
from core import models as core_models
from core import forms

import logging

logger = logging.getLogger('dart')


class SampleTypeList(GenericViewMixin, TemplateView):
    model = core_models.SampleType
    page_title = _("Sample Types")
    template_name = 'core/sample_settings.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['sample_type_form'] = forms.SampleTypeForm()
        context['sample_types'] = core_models.SampleType.objects.all()

        return context


def load_sample_type(request, **kwargs):
    if request.method == "GET":
        if 'sample_type_id' not in kwargs or not kwargs['sample_type_id']:
            raise Http404("Sample Type does not exist")

        context = {'sample_type': core_models.SampleType.objects.get(pk=kwargs['sample_type_id'])}
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

        sample_type = core_models.SampleType.objects.get(pk=kwargs['sample_type_id'])
        sample_type_form = forms.SampleTypeForm(instance=sample_type)

        html = render_to_string('core/partials/form_sample_type.html', context={'sample_type_form': sample_type_form,
                                                                                'sample_type': sample_type,
                                                                                'expanded': True})
        response = HttpResponse(html)
        return response


def delete_sample_type(request, **kwargs):

    if request.method == 'POST':
        if 'sample_type_id' not in kwargs:
            raise Http404("Sample Type does not exist")

        sample_type_id = int(kwargs['sample_type_id'])
        soup = BeautifulSoup(f'<div id="div_id_message_{sample_type_id}"></div>', 'html.parser')
        try:
            sample_type = core_models.SampleType.objects.get(pk=sample_type_id)

            if not sample_type.samples.all().exists():
                sample_type.delete()

                msg_div = soup.find('div')
                msg_div.attrs = {
                    'hx-trigger': 'load',
                    'hx-get': '',
                    'hx-swap': 'delete',
                    'hx-swap-oob': f'delete:#div_id_sample_type_{sample_type_id}'
                }
                return HttpResponse(soup)

            message = _("Sample type is attached to missions and would destroy data if it was deleted")
            div_alert = soup.new_tag("div")
            div_alert.attrs = {
                'id': f'div_id_alert_{sample_type_id}',
                'class': 'alert alert-warning'
            }

            div_alert.string = message
            soup.find("div").append(div_alert)

            return HttpResponse(soup)
        except Exception as ex:
            logger.exception(ex)
            message = _("Couldn't delete Sample Type: ") + str(ex)
            div_alert = soup.new_tag("div")
            div_alert.attrs = {
                'id': f'div_id_alert_{sample_type_id}',
                'class': 'alert alert-warning'
            }

            div_alert.string = message
            soup.find("div").append(div_alert)

            return HttpResponse(soup)


def save_sample_type(request, **kwargs):

    if request.method == "POST":
        if 'sample_type_id' in kwargs:
            sample_type = core_models.SampleType.objects.get(pk=kwargs['sample_type_id'])
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
