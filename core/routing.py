from django.urls import path

from .consumer import CoreConsumer

ws_urlpatterns = [
    path('core/test/<str:chat_box_name>/', CoreConsumer.as_asgi())
]
