from django.urls import path

from config import consumers

websocket_urlpatterns = [
    path(f'ws/notification/<str:logger>/', consumers.NotificationConsumer.as_asgi()),
]