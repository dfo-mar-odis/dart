from django.conf import settings


class BioChemRouter:
    defult_db_labels = ['settingsdb', 'bio_tables']

    def db_for_read(self, model, **hints):
        if model._meta.app_label in self.defult_db_labels:
            return 'default'

        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label in self.defult_db_labels:
            return 'default'

        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        # if app_label == 'settingsdb':
            # if db == biochem_database_label and model_name in self.allow_model_migrations:
            #     return True

        if not db == 'default':
            pass

        return None

    def allow_relation(self, obj1, obj2, **hints):

        obj1_label = obj1._meta.app_label
        obj2_label = obj2._meta.app_label
        if obj1_label == obj2_label or obj1_label in self.defult_db_labels or obj2_label in self.defult_db_labels:
            return True
        return None
