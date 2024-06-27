import os.path

from django.db.models import DecimalField

from dart import settings

import logging

logger = logging.getLogger('dart')


# Looks at a given field of a django model and determines if the values are different.
# if they are the value is updated and the filed is returned.
# Otherwise '' is returned (because you can't add a None type to a set)
#
# my standard pattern for using this is
#
# update_models = {'fields': set(), 'models': []}
# existing_models = models.SomeModel.object.all()
# for model in existing_models:
#    update_models['fields'].add(update_value(model, 'field_name', value))
#    update_models['fields'].add(update_value(model, 'field_name_2', value))
#    update_models['fields'].add(update_value(model, 'field_name_3', value))
#
#    if '' in update_models['fields']:  # if you try to remove something from a set that isn't there it throws an error
#       update_models['fields'].remove('')  # if a field isn't updates a blank is returned
#
#    if len(update_models['fields']) > 0:
#       update_models['models'].append(model)
#
# if len(update_models['models']) > 0:
#    models.SomeModel.object.bulk_update(update_models['models'], update_models['fields'])
#
def updated_value(row, field_name, new_value) -> str:
    field = row._meta.get_field(field_name)
    new_value = field.to_python(new_value)

    current_value = getattr(row, field_name)

    if new_value:
        if field.null and type(current_value) is str and current_value == '':
            current_value = None
        if type(field) is DecimalField:
            new_value = round(new_value, field.decimal_places)

    if current_value == new_value or (new_value is None and current_value is ''):
        return ''

    setattr(row, field_name, new_value)
    return field_name


def convertDMS_degs(dms_string):
    dms = dms_string.split()
    nsew = dms[2].upper()  # north, south, east, west
    degs = (float(dms[0]) + float(dms[1]) / 60) * (-1 if (nsew == 'S' or nsew == 'W') else 1)

    return degs


def convertDegs_DMS(dd):
    d = int(dd)
    m = float((dd - d) * 60.0)

    return [d, m]


def load_svg(svg_name: str):
    file = os.path.join(settings.STATIC_ROOT, settings.BS_ICONS_CUSTOM_PATH,
                        svg_name + ("" if svg_name.endswith('.svg') else ".svg"))

    if not os.path.isfile(file):
        file = os.path.join(settings.BASE_DIR, settings.STATIC_URL, settings.BS_ICONS_CUSTOM_PATH,
                            svg_name + ("" if svg_name.endswith('.svg') else ".svg"))
        if not os.path.isfile(file):
            raise FileNotFoundError

    with open(file, 'r') as fp:
        svg_icon = fp.read()

    return svg_icon
