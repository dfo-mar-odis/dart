import os
import io
import re

import pandas as pd

from core import models


class VolumeParser:
    def __init__(self, file_stream: io.StringIO):
        self.file_stream = file_stream

    def parse_header(self):
        cruise = None
        station = None
        header_found = False

        for line in self.file_stream:
            if "Header Comment" in line:
                header_found = True
                continue

            if header_found:
                if line.startswith("Cruise:"):
                    cruise = line.split("Cruise:")[1].strip()
                elif line.startswith("Station:"):
                    station = line.split("Station:")[1].strip()

                # Stop parsing after finding both values
                if cruise and station:
                    break

        return {"Cruise": cruise, "Station": station}

    def parse_data(self):
        # Move the file pointer to the start
        self.file_stream.seek(0)
        data_started = False
        data_lines = []

        for line in self.file_stream:
            if data_started:
                data_lines.append(line.strip())
            elif line.startswith("Time [hh:mm:ss]"):
                # Capture the header and start collecting data
                header = line.strip()
                data_started = True

        # Combine header and data into a single string
        data_content = "\n".join([header] + data_lines)

        # Read the data into a pandas DataFrame
        data_frame = pd.read_csv(io.StringIO(data_content), sep="\t")

        # Strip out ' [.*?]' from column names
        data_frame.columns = [re.sub(r'\s*\[.*?\]', '', col).upper() for col in data_frame.columns]
        return data_frame

    def parse(self):
        self.header_info = self.parse_header()
        self.data_frame = self.parse_data()

    def get_nets(self):
        if hasattr(self, 'data_frame'):
            return self.data_frame['NET'].unique()
        else:
            raise ValueError("Data has not been parsed yet. Call parse() method first.")

    def get_volume_by_net(self, net_number):
        if hasattr(self, 'data_frame'):
            net_data = self.data_frame[self.data_frame['NET'] == net_number]
            if not net_data.empty:
                return net_data.iloc[-1]['VOLUME']
            else:
                raise ValueError(f"No data found for net number {net_number}.")
        else:
            raise ValueError("Data has not been parsed yet. Call parse() method first.")

def read_file():
    file_path = os.path.join(r'C:\DFO-MPO\sample_data\JC28302\Multinet', 'JC28302_A1_data.txt')
    with open(file_path, 'r') as file:
        file_content = file.read()
        file_stream = io.StringIO(file_content)
        volume_data = VolumeParser(file_stream)
        volume_data.parse()

    mission = models.Mission.objects.get(pk=1)
    update_volume_data(volume_data, mission)

def update_volume_data(volume_data: VolumeParser, mission: models.Mission):

    if mission.name != volume_data.header_info['Cruise']:
        raise ValueError(f"Cruise '{volume_data.header_info['Cruise']}' does not match the current mission.")

    # this will raise does not exists or multiple elements returned error if there are multiple nets for the same
    # event.
    event = mission.events.get(station__name__iexact=volume_data.header_info['Station'],
                               instrument__type=models.InstrumentType.net, instrument__name__iexact="MULTINET")

    update_bottles = []
    bad_sample_ids = []
    for sample_id in range(event.sample_id, event.end_sample_id + 1):
        net_volume = volume_data.get_volume_by_net(sample_id - event.sample_id + 1)
        try:
            bottle = event.bottles.get(bottle_id=sample_id)
        except models.Bottle.DoesNotExist as e:
            bad_sample_ids.append(str(sample_id))
            continue

        bottle.gear_type_id = models.NET_TYPES['MULTINET'].get('GEAR_TYPE')
        bottle.volume = net_volume
        update_bottles.append(bottle)

    models.Bottle.objects.bulk_update(update_bottles, ['gear_type_id', 'volume'])

    if bad_sample_ids:
        raise models.Bottle.DoesNotExist(f"No bottle found for sample ID {', '.join(bad_sample_ids)} in event '{event}'.")
