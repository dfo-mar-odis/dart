from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

from config import utils

import logging
logger = logging.getLogger('dart')

class HtmxDatabaseMiddleware(MiddlewareMixin):
    """
    Middleware to handle HTMX requests that require dynamic database connections.

    - Checks if the incoming request has the 'HX-Request' header (indicating an HTMX request).
    - Parses the database name from the HTTP_REFERER header.
    - If the database name starts with 'DART_' and is not already active, connects to it using utils.connect_database.
    - Only acts if 'dart_active', the alias given to dart mission databases, is present in settings.DATABASES.
    """
    logger.debug("HtmxDatabaseMiddleware initialized")
    def process_request(self, request):
        if request.headers.get('HX-Request'):
            if 'dart_active' not in settings.DATABASES:
                return

            database_names = request.META['HTTP_REFERER'].split('/')
            database_names = [item for item in database_names if item != '']
            if len(database_names) > 2:
                database_name = database_names[2]
                if database_name.startswith('DART_') and not utils.is_active_database(database_name):
                    utils.connect_database(database_name)

        return None