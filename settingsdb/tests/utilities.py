from django.db import connections
from django.db.models.base import ModelBase


def create_model_table(unmanaged_models: list[ModelBase], db_alias: str = "default") -> None:

    connection = connections[db_alias]
    with connection.schema_editor() as schema_editor:
        for model in unmanaged_models:
            schema_editor.create_model(model)
            if model._meta.db_table not in connection.introspection.table_names():
                raise ValueError(f"Table '{model._meta.db_table}' is missing in the test database")


def delete_model_table(unmanaged_models: list[ModelBase], db_alias: str = "default") -> None:
    connection = connections[db_alias]
    with connection.schema_editor() as schema_editor:
        for model in unmanaged_models:
            schema_editor.delete_model(model)