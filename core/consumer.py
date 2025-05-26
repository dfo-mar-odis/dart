from asgiref.sync import async_to_sync, sync_to_async
from bs4 import BeautifulSoup
from channels.generic.websocket import WebsocketConsumer, AsyncWebsocketConsumer
from django.utils.translation import gettext as _

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

        html = BeautifulSoup(f'<div id="status">{event["message"] if "message" in event else ""}</div>', 'html.parser')
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


class LoggerConsumer(AsyncWebsocketConsumer, logging.Handler):

    GROUP_NAME = "logger"

    async def connect(self):
        logger.info(self.channel_name)

        await self.channel_layer.group_add(
            self.GROUP_NAME, self.channel_name
        )
        await self.accept()
        logger_to_listen_to = self.scope['url_route']['kwargs']['logger']
        logging.getLogger(f'{logger_to_listen_to}').addHandler(self)

    async def disconnect(self, code):
        logger_to_listen_to = self.scope['url_route']['kwargs']['logger']
        logging.getLogger(f'{logger_to_listen_to}').removeHandler(self)
        await self.channel_layer.group_discard(
            self.GROUP_NAME, self.channel_name
        )

    async def process_render_queue(self, component_id, event) -> None:
        soup = BeautifulSoup(f'<div id="{component_id}">{event["message"]}</div>', 'html.parser')
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
        await self.send(soup)

    async def emit(self, record: logging.LogRecord) -> None:
        component = self.scope['url_route']['kwargs']['component_id']

        if len(record.args) > 0:
            event = {
                'message': record.getMessage(),
                'queue': int((record.args[0]/record.args[1])*100)
            }
            await self.process_render_queue(component, event)
        else:
            html = BeautifulSoup(f'<div id="{component}">{record.getMessage()}</div>', 'html.parser')
            await self.send(html)

    def __init__(self):
        logging.Handler.__init__(self, level=logging.INFO)
        AsyncWebsocketConsumer.__init__(self)
