from asgiref.sync import async_to_sync
from bs4 import BeautifulSoup
from channels.generic.websocket import WebsocketConsumer
from django.template.loader import render_to_string

from core.htmx import get_mission_elog_errors

import logging

from render_block import render_block_to_string

logger = logging.getLogger('dart.debug')

message_queue = []


class CoreConsumer(WebsocketConsumer):

    def connect(self):
        logger.info(self.channel_name)

        self.GROUP_NAME = 'mission_events'
        async_to_sync(self.channel_layer.group_add)(
            self.GROUP_NAME, self.channel_name
        )
        self.accept()

    def disconnect(self, code):
        async_to_sync(self.channel_layer.group_discard)(
            self.GROUP_NAME, self.channel_name
        )

    def close_render_queue(self, event):

        html = BeautifulSoup(f'<div id="status"></div>', 'html.parser')
        status_div = html.find('div')
        for key, value in event.items():
            status_div.attrs[key] = value

        self.send(text_data=html)

    def process_render_queue(self, event):
        soup = BeautifulSoup(f'<div id="status">{event["message"]}</div>', 'html.parser')
        progress_bar = soup.new_tag("div")
        progress_bar.attrs = {
            'class': "progress-bar progress-bar-striped progress-bar-animated",
            'role': "progressbar",
            'style': f'width: {event["queue"]}%'
        }
        progress_bar.string = event["queue"]

        progress_bar_div = soup.new_tag("div", attrs={'class': "progress", 'id': 'progress_bar'})
        progress_bar_div.append(progress_bar)
        progress_bar_div.attrs['aria-valuenow'] = event["queue"]
        progress_bar_div.attrs['aria-valuemin'] = "0"
        progress_bar_div.attrs['aria-valuemax'] = "100"

        soup.append(progress_bar_div)
        self.send(text_data=soup)

    def processing_elog_message(self, event):
        html = BeautifulSoup(f'<div id="status">{event["message"]}</div>', 'html.parser')
        self.send(text_data=html)

    def update_errors(self, event):
        mission = event['mission']

        error_dict = get_mission_elog_errors(mission=mission)

        context = {'errors': error_dict}

        html = render_block_to_string('core/mission_events.html', 'error_block',
                                      context=context)
        self.send(text_data=html)
