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

    def process_render_block(self, event):
        template = event['template']
        block = event['block'] if 'block' in event else None
        context = event['context']
        if block:
            html = render_block_to_string(template, block, context=context)
        else:
            html = render_to_string(template, context=context)

        self.send(text_data=html)

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
