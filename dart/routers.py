from django.conf import settings

class PrimaryRouter:
    def db_for_read(self, model, **hints):
        return 'mission_db' if model._meta.app_label == "core" and 'mission_db' in settings.DATABASES else None

    def db_for_write(self, model, **hints):
        return 'mission_db' if model._meta.app_label == "core" and 'mission_db' in settings.DATABASES else None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return True if db == 'mission_db' and app_label == 'core' and 'mission_db' in settings.DATABASES else None

    def allow_relation(self, obj1, obj2, **hints):
        return None
