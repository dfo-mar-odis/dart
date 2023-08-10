import os.path

from bs4 import BeautifulSoup

from dart2 import settings


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