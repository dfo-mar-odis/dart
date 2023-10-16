from typing import Type

from django.db import connections, DatabaseError, connection
from dynamic_db_router import in_database

from biochem import models

import logging

logger = logging.getLogger('dart')


def create_model(database_name: str, model):
    with connections[database_name].schema_editor() as editor:
        editor.create_model(model)


def delete_model(database_name: str, model):
    with connections[database_name].schema_editor() as editor:
        editor.delete_model(model)


def check_and_create_model(database_name: str, upload_model):
    try:
        upload_model.objects.exists()
    except DatabaseError as e:
        # A 942 Oracle error means a table doesn't exist, in this case create the model. Otherwise pass the error along
        if e.args[0].code != 942:
            raise e

        create_model(database_name, upload_model)
    except Exception as e:
        logger.exception(e)

    return upload_model


def get_bcd_d_model(db_name: str, table_name: str) -> Type[models.BcdD]:
    bcd_table = table_name + '_bcd_d'
    opts = {'__module__': 'biochem'}
    mod = type(bcd_table, (models.BcdD,), opts)
    mod._meta.db_table = bcd_table

    return check_and_create_model(database_name=db_name, upload_model=mod)


def get_bcs_d_model(db_name: str, table_name: str) -> Type[models.BcsD]:
    bcs_table = table_name + '_bcs_d'
    opts = {'__module__': 'biochem'}
    mod = type(bcs_table, (models.BcsD,), opts)
    mod._meta.db_table = bcs_table

    return check_and_create_model(database_name=db_name, upload_model=mod)


def get_bcd_p_model(db_name: str, table_name: str) -> Type[models.BcdP]:

    bcd_table = table_name + '_bcd_p'
    opts = {'__module__': 'biochem'}
    mod = type(bcd_table, (models.BcdP,), opts)
    mod._meta.db_table = bcd_table

    return check_and_create_model(database_name=db_name, upload_model=mod)


def get_bcs_p_model(db_name: str, table_name: str) -> Type[models.BcsP]:
    bcs_table = table_name + '_bcs_p'
    opts = {'__module__': 'biochem'}
    mod = type(bcs_table, (models.BcsP,), opts)
    mod._meta.db_table = bcs_table

    return check_and_create_model(database_name=db_name, upload_model=mod)
