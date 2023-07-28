class BioChemRouter:
    route_app_labels = {'biochem'}

    # We're only going to allow migrations of specific models so we can't accidentally destroy code tables we use
    # but never modify.
    allow_model_migrations = ['azmptestmodel', 'dynamictestmodel']

    def db_for_read(self, model, **hints):
        if model._meta.app_label in self.route_app_labels:
            return 'mirror_biochem'

        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label in self.route_app_labels:
            return 'mirror_biochem'

        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label in self.route_app_labels:
            if db == 'mirror_biochem' and model_name in self.allow_model_migrations:
                return True

        if not db == 'default':
            pass

        return None
