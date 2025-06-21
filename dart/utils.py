import os
import math
import easygui
import time
import ctypes

import concurrent.futures

from django.utils.translation import gettext as _


def force_foreground_window():
    # Give system time to create the dialog
    time.sleep(0.25)
    # Get the foreground window handle
    dialog_title = _("Choose BTL directory")
    hwnd = ctypes.windll.user32.FindWindowW(None, dialog_title)

    if hwnd:
        # Try more aggressive techniques to force to front
        # This combination works better for dialog windows
        ctypes.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW
        ctypes.windll.user32.BringWindowToTop(hwnd)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        ctypes.windll.user32.FlashWindow(hwnd, True)
    else:
        # Fall back to the original method if we can't find by title
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if hwnd:
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.FlashWindow(hwnd, True)

def diropenbox_on_top(*args, **kwargs):
    import platform

    # For Windows, use the dialog-forcing approach
    if platform.system() == 'Windows':
        # Start the dialog in a way that allows us to force it to the top
        result = None
        import threading
        threading.Timer(0.2, force_foreground_window).start()
        result = easygui.diropenbox(*args, **kwargs)
        return result
    else:
        # For non-Windows platforms, just use the standard dialog
        return easygui.diropenbox(*args, **kwargs)


def distance(point1: [float, float], point2: [float, float]) -> float:
    """
    Calculate the great-circle distance between two points on the Earth (specified in decimal degrees).
    :param point1: [latitude, longitude]
    :param point2: [latitude, longitude]
    :return: distance in kilometers
    """
    lat1, lon1 = point1
    lat2, lon2 = point2

    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    r = 6371  # Radius of Earth in kilometers
    return c * r

def is_locked(file):
    try:
        # if a file exists and can't be renamed to itself this will throw an exception indicating the file
        # can't be opened and written to
        if os.path.exists(file):
            os.rename(file, file)
        return False
    except OSError:
        return True

def is_integer_string(s):
    try:
        int(s)
        return True
    except ValueError:
        return False