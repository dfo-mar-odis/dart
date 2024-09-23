import math

import matplotlib.pyplot as plt

from settingsdb import utils
from core import models
from django_pandas.io import read_frame


class Dart:
    mission_database = None

    def __init__(self, database_name):
        self.set_database(database_name)

    def set_database(self, database_name):
        self.mission_database = database_name
        utils.connect_database(self.mission_database)

    def get_sample_names(self):
        samples = models.MissionSampleType.objects.using(self.mission_database).values_list('name', flat=True)
        return samples

    def get_stations(self):
        ctd_events = models.Event.objects.using(self.mission_database).filter(instrument__type=models.InstrumentType.ctd)
        ctd_stations = ctd_events.values_list('station__name', flat=True)
        stations = models.Station.objects.using(self.mission_database).filter(name__in=ctd_stations)
        return stations

    def plot_station(self, station_name, sample_type_name):
        event = models.Event.objects.using(self.mission_database).get(
            station__name=station_name, instrument__type=models.InstrumentType.ctd
        )
        data = models.DiscreteSampleValue.objects.using(self.mission_database).filter(
            sample__type__name=sample_type_name, sample__bottle__event=event
        )
        df = read_frame(data, fieldnames=['sample__bottle__pressure', 'value'])

        plt.plot(df)
        plt.show()
        plt.close()

    def plot_stations(self, station_names: list, sample_type_name: str):

        max_col = math.ceil(math.sqrt(len(station_names)))

        fig, axs = plt.subplots(math.ceil(len(station_names) / max_col), max_col)
        fig.subplots_adjust(hspace=(max_col*0.5), wspace=(max_col*0.25))
        col_index = 0

        for station, station_name in enumerate(station_names):
            row_index = int(station / max_col)
            col_index = int(station % max_col)

            event = models.Event.objects.using(self.mission_database).get(
                station__name__iexact=station_name, instrument__type=models.InstrumentType.ctd
            )
            data = models.DiscreteSampleValue.objects.using(self.mission_database).filter(
                sample__type__name=sample_type_name, sample__bottle__event=event
            )
            df = read_frame(data, fieldnames=['sample__bottle__pressure', 'value'])
            axs[row_index][col_index].set_title(station_name)
            if col_index == 0:
                axs[row_index][col_index].set_ylabel("Pressure")
            axs[row_index][col_index].set_xlabel(sample_type_name)
            axs[row_index][col_index].yaxis.set_inverted(True)

            axs[row_index][col_index].plot(df['value'], df['sample__bottle__pressure'])

        # erase extra plots in the row.
        if col_index < max_col:
            for i in range(col_index + 1, max_col):
                axs[row_index][i].remove()

        return plt


def dart_script():
    dart = Dart('DY18402')

    stations = dart.get_stations().filter(name__icontains='BBL_')
    plt = dart.plot_stations(stations, 'ph')
    plt.show()
    plt.close()
