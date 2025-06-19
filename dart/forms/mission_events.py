import pandas as pd

from bs4 import BeautifulSoup
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import path, reverse_lazy

from dart import models as dart_models

def list_events(request, mission_id):
    events = dart_models.Event.objects.filter(mission__id=mission_id).order_by('event_id').select_related('station', 'instrument')
    event_list = []
    for event in events:
        event_list.append({
            'event_pk': event.pk,
            'event_id': event.event_id,
            'station__name': event.station.name,
            'instrument__type': event.instrument.get_type_display(),
        })

    if not event_list:
        df = pd.DataFrame(columns=['event_pk', 'event_id', 'station__name', 'instrument__type'])
    else:
        df = pd.DataFrame(event_list)

    df.columns = ['#', 'Event ID', 'Station Name', 'Instrument Type']

    table_html = df.to_html(index=False, classes='table')
    soup = BeautifulSoup(table_html, 'html.parser')
    table = soup.find('table')
    tbody = table.find('tbody')

    trs = tbody.findAll('tr')
    for tr in trs:
        td_pk = tr.find('td')
        td_pk.attrs['class'] = 'd-none'
        event_id = td_pk.text.strip()
        tr.attrs['id'] = f'td_id_event_{event_id}'
        tr.attrs['hx-trigger'] = f'click, selected_event_{event_id} from:body'
        tr.attrs['hx-swap'] = 'outerHTML'
        tr.attrs['hx-get'] = reverse_lazy('dart:form_events_details', args=(mission_id, event_id))

    # Placeholder function to handle the request for listing events
    return HttpResponse(trs)


def get_event_details(event):
    context = {
        "mission": event.mission,
        "event": event
    }
    html = render_to_string('dart/partials/event_details_card.html', context)
    soup = BeautifulSoup(html, 'html.parser')

    return soup

def event_selection(request, mission_id, event_pk):
    try:
        event = dart_models.Event.objects.get(pk=event_pk, mission__id=mission_id)
    except dart_models.Event.DoesNotExist:
        return HttpResponse("Event not found", status=404)

    soup = BeautifulSoup('', 'html.parser')
    soup.append(table:=soup.new_tag('table'))
    table.append(tr := soup.new_tag('tr', id=f'tr_id_event_{event.pk}'))
    tr.attrs['id'] = f'td_id_event_{event.pk}'
    tr.attrs['hx-swap-oob'] = 'true'

    tr.append(td_id:=soup.new_tag('td', string=str(event.pk), attrs={'class': 'd-none'}))
    tr.append(soup.new_tag('td', string=str(event.event_id)))
    tr.append(soup.new_tag('td', string=event.station.name))
    tr.append(soup.new_tag('td', string=event.instrument.get_type_display()))

    url = reverse_lazy('dart:form_events_details', args=(mission_id, event.pk))
    if 'deselect' in request.GET:
        tr.attrs['hx-trigger'] = 'click'
        tr.attrs['hx-get'] = url
        response = HttpResponse(soup)
    else:
        tr.attrs['class'] = 'table-success'
        tr.attrs['hx-trigger'] = 'deselect from:body'
        tr.attrs['hx-get'] = url + "?deselect=true"
        soup.append(get_event_details(event))
        response = HttpResponse(soup)
        response['HX-Trigger'] = 'deselect'

    return response

urlpatterns = [
    path("mission/event/list/<int:mission_id>", list_events, name="form_events_list"),
    path("mission/event/select/<int:mission_id>/<int:event_pk>/", event_selection, name="form_events_details"),
]