import os
import math

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