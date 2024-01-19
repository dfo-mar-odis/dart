from django.urls import path

from .consumer import CoreConsumer, BiochemConsumer, LoggerConsumer

ws_urlpatterns = [
    path('ws/notifications/', CoreConsumer.as_asgi()),
    path('ws/biochem/notifications/<str:component_id>/', BiochemConsumer.as_asgi()),
    path('ws/notifications/<str:logger>/<str:component_id>/', LoggerConsumer.as_asgi()),
]
