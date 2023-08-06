import pandas as pd
import math


# compute the distance between two points on earth
def distance(point1: [float, float], point2: [float, float]) -> float:

    lat1 = point1[0] * math.pi / 180
    lat2 = point2[0] * math.pi / 180
    lon = (point2[1] - point1[1]) * math.pi / 180
    R = 6371e3

    inner = math.sin(lat1) * math.sin(lat2) + math.cos(lat1) * math.cos(lat2) * math.cos(lon)

    # if the inner value is greater than 1, likely due to rounding errors, math.acos will throw a ValueError
    d = math.acos(1 if inner > 1 else inner) * R

    return d
