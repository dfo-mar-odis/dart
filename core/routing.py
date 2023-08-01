from django.urls import path

from .consumer import CoreConsumer

ws_urlpatterns = [
    path('ws/notifications/', CoreConsumer.as_asgi())
]
