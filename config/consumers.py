import logging

from asgiref.sync import sync_to_async, async_to_sync
from channels.generic.websocket import AsyncWebsocketConsumer

from . import components

logger = logging.getLogger("dart")

class NotificationConsumer(AsyncWebsocketConsumer, logging.Handler):

    GROUP_NAME = "notification"

    async def connect(self):
        logger.info(self.channel_name)

        await self.channel_layer.group_add(
            self.GROUP_NAME, self.channel_name
        )

        await self.accept()
        logger_to_listen_to = self.scope['url_route']['kwargs']['logger']
        logging.getLogger(f'{logger_to_listen_to}').addHandler(self)

    async def disconnect(self, close_code):
        logger_to_listen_to = self.scope['url_route']['kwargs']['logger']
        logging.getLogger(f'{logger_to_listen_to}').removeHandler(self)
        await self.channel_layer.group_discard(
            self.GROUP_NAME, self.channel_name
        )

    async def send_message(self, message):
        await self.send(text_data=message)

    def emit(self, record: logging.LogRecord) -> None:
        ws_modal = self.ws_modal.find(id='modalContent')
        ws_modal.find(id='modalTitle').string = record.getMessage()
        ws_progress = ws_modal.find(id="modalProgressBar")
        ws_sub_progress = ws_progress.find('div')

        complete, minvalue, maxvalue = 100, 100, 100
        if len(record.args) > 0:
            minvalue, maxvalue = record.args[0], record.args[1]
            complete = str(int((minvalue/maxvalue)*100))
            ws_sub_progress.string = f"{complete}%"
        else:
            ws_sub_progress.string = f"computing"

        ws_progress.attrs["aria-valuenow"] = complete
        ws_progress.attrs["aria-valuemin"] = minvalue
        ws_progress.attrs["aria-valuemax"] = maxvalue
        ws_sub_progress['style'] = f"width: {complete}%"

        async_to_sync(self.send_message)(str(ws_modal))

    def __init__(self):
        logging.Handler.__init__(self, level=logging.INFO)
        AsyncWebsocketConsumer.__init__(self)

        self.ws_modal = components.modal("initial")