import os
import markdown
import re

from django.conf import settings
from django.http import HttpResponse, HttpResponseNotFound
from django.views.generic import TemplateView
from django.shortcuts import render

from bs4 import BeautifulSoup

from dart.views import GenericViewMixin

from django.utils.translation import gettext as _


def markdown_page(request):
    file_vars = request.path_info.split("/")[2:]
    while not file_vars[-1]:
        file_vars.pop(-1)

    file_path = os.path.join(settings.STATIC_ROOT, *file_vars[0:-1])
    file = f'{file_vars[-1]}_{request.LANGUAGE_CODE}.md'
    path = os.path.join(file_path, file)
    if not os.path.isfile(path):
        path = os.path.join(file_path, f'{file_vars[-1]}.md')

    if not os.path.isfile(path):
        return HttpResponse(render(template_name='docs/markdown.html', request=request,
                                   context={'html': '<h1>Page Not Found</h1>'}))

    with open(path, encoding='utf-8') as fp:
        markdown_str = fp.read()

    cards = re.findall(r'\{%.*card.*%}(?s:.*?)\{%.*endcard.*%\}', markdown_str, re.M)

    html_cards = []
    for card in cards:
        card = re.sub(r'\{%.*card.*%\}|\{%.*endcard.*%\}', '', card)
        html_cards.append(markdown.markdown(card))

    soup = BeautifulSoup('', 'html.parser')
    for html_card in html_cards:
        soup.append(card := soup.new_tag('div', attrs={'class': 'card mb-2'}))
        card.append(card_head := soup.new_tag('div', attrs={'class': 'card-header'}))
        card.append(card_body := soup.new_tag('div', attrs={'class': 'card-body'}))

        card_head.append(card_title := soup.new_tag('div', attrs={'class': 'card-title'}))

        html = BeautifulSoup(html_card, 'html.parser')
        for i in range(1, 6):
            title = html.find(f'h{i}')
            if title is not None:
                card_title.append(h := soup.new_tag(f'h{i}'))
                h.string = title.string
                title.decompose()
                break

        card_body.append(html)

    for img in soup.findAll('img'):
        img['class'] = img.get('class', []) + ['img-fluid', 'border', 'pt-2', 'mb-2', 'border-1']

    for ul in soup.findAll('ul'):
        ul['class'] = ul.get('class', []) + ['list-group', 'mb-2']

    for li in soup.findAll('li'):
        li['class'] = li.get('class', []) + ['list-group-item']

    return HttpResponse(render(template_name='docs/markdown.html', request=request, context={'html': soup.prettify()}))


class Home(GenericViewMixin, TemplateView):
    page_title = _("Welcome to the Documentation")
    template_name = 'docs/index.html'


class MissionFilter(GenericViewMixin, TemplateView):
    page_title = _("Mission Filter Page")
    template_name = 'docs/mission_filter.html'


class NewMissionForm(GenericViewMixin, TemplateView):
    page_title = _("New Mission Form")
    template_name = 'docs/new_mission_form.html'


class MissionEvents(GenericViewMixin, TemplateView):
    page_title = _("Mission Events Page")
    template_name = 'docs/mission_events.html'


class MissionSamples(GenericViewMixin, TemplateView):
    page_title = _("Mission Samples Page")
    template_name = 'docs/mission_samples.html'


class FileConfigurations(GenericViewMixin, TemplateView):
    page_title = _("Creating and Modifying File Configurations")
    template_name = 'docs/file_configurations.html'


class SampleTypes(GenericViewMixin, TemplateView):
    page_title = _("Standard Sample Types Page")
    template_name = 'docs/standard_sample_types.html'
