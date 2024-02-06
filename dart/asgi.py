"""
ASGI config for dart project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.2/howto/deployment/asgi/
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dart.settings')
django.setup()

from django.core.asgi import get_asgi_application

from channels.routing import ProtocolTypeRouter
from channels.routing import URLRouter
from channels.auth import AuthMiddlewareStack

from core.routing import ws_urlpatterns


application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(URLRouter(ws_urlpatterns))
})
