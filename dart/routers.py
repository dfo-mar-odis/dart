from django.conf import settings

class PrimaryRouter:

    # if a mission database is connected we want to make updates and reads from that connected database for
    # core and bio_tables models. If no mission database is connected then bio_tables updates should be made
    # on the local default database. Core model read/writes should not be made on the local default database
    mission_databases = ['core', 'bio_tables']

    def db_for_read(self, model, **hints):
        if model._meta.app_label == 'settingsdb':
            return 'default'

        if 'mission_db' in settings.DATABASES:
            return 'mission_db' if model._meta.app_label in self.mission_databases else None

        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label == 'settingsdb':
            return 'default'

        if 'mission_db' in settings.DATABASES:
            return 'mission_db' if model._meta.app_label in self.mission_databases else None

        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == 'settingsdb':
            return True

        if 'mission_db' in settings.DATABASES:
            return True if app_label in self.mission_databases else None

        return None

    def allow_relation(self, obj1, obj2, **hints):
        return True
