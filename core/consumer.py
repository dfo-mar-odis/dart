from asgiref.sync import async_to_sync
from bs4 import BeautifulSoup
from channels.generic.websocket import WebsocketConsumer
from django.template.loader import render_to_string
from django.utils.translation import gettext as _

from core.htmx import get_mission_elog_errors, get_mission_validation_errors

import logging


logger = logging.getLogger('dart.user')

message_queue = []


class CoreConsumer(WebsocketConsumer):

    GROUP_NAME = 'mission_events'
    def connect(self):
        logger.info(self.channel_name)

        async_to_sync(self.channel_layer.group_add)(
            self.GROUP_NAME, self.channel_name
        )
        self.accept()

    def disconnect(self, code):
        async_to_sync(self.channel_layer.group_discard)(
            self.GROUP_NAME, self.channel_name
        )

    def close_render_queue(self, event):

        html = BeautifulSoup(f'<div id="status">event["message"]</div>', 'html.parser')
        status_div = html.find('div')
        for key, value in event.items():
            status_div.attrs[key] = value

        self.send(text_data=html)

    def send_html_update(self, event):
        html = BeautifulSoup(f'<div id="status"></div>', 'html.parser')
        status_div = html.find('div')
        status_div.append(event['html_element'])

        self.send(text_data=html)

    def process_render_queue(self, event):
        soup = BeautifulSoup(f'<div id="status">{event["message"]}</div>', 'html.parser')
        progress_bar = soup.new_tag("div")
        progress_bar.attrs = {
            'class': "progress-bar progress-bar-striped progress-bar-animated",
            'role': "progressbar",
        }

        progress_bar_div = soup.new_tag("div", attrs={'class': "progress", 'id': 'progress_bar'})
        progress_bar_div.append(progress_bar)

        if event['queue']:
            progress_bar.attrs['style'] = f'width: {event["queue"]}%'
            progress_bar.string = f"{event['queue']}%"
            progress_bar_div.attrs['aria-valuenow'] = str(event["queue"])
            progress_bar_div.attrs['aria-valuemin'] = "0"
            progress_bar_div.attrs['aria-valuemax'] = "100"
        else:
            progress_bar.attrs['style'] = f'width: 100%'
            progress_bar.string = _("Working")

        soup.append(progress_bar_div)
        self.send(text_data=soup)

    def processing_elog_message(self, event):
        html = BeautifulSoup(f'<div id="status">{event["message"]}</div>', 'html.parser')
        self.send(text_data=html)

    def update_errors(self, event):
        mission = event['mission']

        context = {
            'mission': mission,
            'errors': get_mission_elog_errors(mission),
            'validation_errors': get_mission_validation_errors(mission)
        }
        html = render_to_string('core/partials/card_event_validation.html', context=context)

        self.send(text_data=html)


class BiochemConsumer(CoreConsumer, logging.Handler):

    GROUP_NAME = "biochem"

    def connect(self):
        super().connect()
        logger.addHandler(self)

    def disconnect(self, code):
        super().disconnect(code)
        logger.removeHandler(self)

    def emit(self, record: logging.LogRecord) -> None:
        component = self.scope['url_route']['kwargs']['component_id']

        if len(record.args) > 0:
            event = {
                'message': record.getMessage(),
                'queue': int((record.args[0]/record.args[1])*100)
            }
            self.process_render_queue(event)
        else:
            html = BeautifulSoup(f'<div id="status">{record.getMessage()}</div>', 'html.parser')
            self.send(text_data=html)

    def __init__(self):
        logging.Handler.__init__(self, level=logging.INFO)
        CoreConsumer.__init__(self)