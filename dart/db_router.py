import sys
from django.conf import settings

class DartRouter:

    def _in_test_mode(self):
        return 'test' in sys.argv

    def db_for_read(self, model, **hints):
        if model._meta.app_label == 'dart':
            if 'dart_active' in settings.DATABASES:
                return 'dart_active'
        return 'default'

    def db_for_write(self, model, **hints):
        if model._meta.app_label == 'dart':
            if 'dart_active' in settings.DATABASES:
                return 'dart_active'
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == 'dart':
            if self._in_test_mode():
                return db == 'default'
            return db.startswith('dart_new_') or db == 'dart_active'
        return db == 'default'