import os

import numpy as np
import pandas as pd
import math


# compute the distance between two points on earth
def distance(point1: [float, float], point2: [float, float]) -> float:

    if point1 == [None, None] or point2 == [None, None]:
        return np.nan

    lat1 = float(point1[0]) * math.pi / 180
    lat2 = float(point2[0]) * math.pi / 180
    lon = float(point2[1] - point1[1]) * math.pi / 180
    R = 6371e3

    inner = math.sin(lat1) * math.sin(lat2) + math.cos(lat1) * math.cos(lat2) * math.cos(lon)

    # if the inner value is greater than 1, likely due to rounding errors, math.acos will throw a ValueError
    d = math.acos(1 if inner > 1 else inner) * R

    return d


def is_locked(file):
    try:
        # if a file exists and can't be renamed to itself this will throw an exception indicating the file
        # can't be opened and written to
        if os.path.exists(file):
            os.rename(file, file)
        return False
    except OSError:
        return True


def is_number(value: str) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False