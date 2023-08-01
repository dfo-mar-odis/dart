from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer

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

    def processing_message(self, event):
        html = render_block_to_string('core/mission_events.html', 'status_block',
                                      context={'object': event['mission'], 'msg': event['message']})
        self.send(text_data=html)

    def update_errors(self, event):
        mission = event['mission']

        error_dict = get_mission_elog_errors(mission=mission)

        context = {'errors': error_dict}

        html = render_block_to_string('core/mission_events.html', 'error_block',
                                      context=context)
        self.send(text_data=html)
