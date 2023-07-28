from asgiref.sync import async_to_sync
from channels.generic.websocket import AsyncWebsocketConsumer

message_queue = []


class CoreConsumer(AsyncWebsocketConsumer):

    def connect(self):
        self.GROUP_NAME = 'user-notifications'
        async_to_sync(self.channel_layer.group_add)(
            self.GROUP_NAME, self.channel_name
        )
        self.accept()

    def disconnect(self, code):
        async_to_sync(self.channel_layer.group_discard)(
            self.GROUP_NAME, self.channel_name
        )