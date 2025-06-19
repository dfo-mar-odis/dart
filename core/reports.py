import numpy as np

from datetime import datetime, timedelta

from django.core.files.base import ContentFile
from django.db.models import Min, Avg
from django.http import HttpResponse
from django.urls import path

from . import models as core_models


def convert_timedelta_to_string(delta: timedelta) -> str:
    hours, rem = divmod(delta.total_seconds(), 3600)
    minutes, seconds = divmod(rem, 60)
    days = f"{int(delta.days):02}" if delta.days > 0 else "00"

    hours = f"{int(hours+ (delta.days*24)):02d}" if (hours + (delta.days*24)) > 0 else "00"
    minutes = f"{int(minutes):02d}" if minutes > 0 else "00"
    seconds = f"{int(seconds):02d}" if seconds > 0 else "00"
    elapsed = f"{hours}:{minutes}:{seconds}"

    return elapsed


def get_event_ids(event_query):
    if event_query is None or not event_query.exists():
        return ''

    return ' / '.join([f'{c:03d}' for c in event_query.values_list('event_id', flat=True)])


def get_station_list(database):
    stations = []
    station_list = []
    events = core_models.Event.objects.order_by('event_id')
    for event in events:
        if event.station.name not in stations:
            stn_events = events.filter(station=event.station)
            station_date = datetime.strftime(stn_events.first().start_date, '%Y-%m-%d %H:%M:%S')

            # was a CTD done at this station
            ctd_done = stn_events.filter(instrument__type=core_models.InstrumentType.ctd)
            # Were samples taken at this station.
            rosette_done = core_models.Bottle.objects.filter(event__station=event.station)

            # was a VPR done at this station
            vpr_done = stn_events.filter(instrument__type=core_models.InstrumentType.vpr)
            xbt_done = stn_events.filter(instrument__name__iexact='xbt')
            multinet_done = stn_events.filter(instrument__name__iexact='multinet')

            net_events = stn_events.filter(instrument__type=core_models.InstrumentType.net)
            net_202_done = net_events.filter(instrument__name__icontains='202', sample_id__isnull=False)
            net_76_done = net_events.filter(instrument__name__icontains='76')

            instrument_events = stn_events.exclude(actions__type=core_models.ActionType.aborted)

            live_tow = False
            mooring_deployed = None
            mooring_recovered = None
            argo_done = None
            if instrument_events.exists():
                # I don't like this, but check if this is a live tow. If a net event is missing a sample ID
                # it *MIGHT* have been a live tow... or someone just forgot to fill in the sample ID
                live_tow = instrument_events.filter(instrument__type=core_models.InstrumentType.net,
                                                    sample_id__isnull=True)
                moorings = instrument_events.filter(instrument__name__icontains='mooring')
                mooring_deployed = moorings.filter(instrument__name__icontains='deploy')
                mooring_recovered = moorings.filter(instrument__name__icontains='recover')
                argo_done = instrument_events.filter(instrument__name__icontains='argo')

            stations.append(event.station.name)
            action = event.actions.first()
            station_list.append({
                'station': event.station.name,
                'date': station_date,
                'latitude': action.latitude,
                'longitude': action.longitude,
                'depth': action.sounding if action.sounding else 'NA',
                'ctd': get_event_ids(ctd_done),
                'rosette': get_event_ids(ctd_done) if rosette_done.exists() else '',
                'biol station': '',
                'xbt': get_event_ids(xbt_done),
                'vpr': get_event_ids(vpr_done),
                'plankton multinet':  get_event_ids(multinet_done),
                'plankton 200': get_event_ids(net_202_done),
                'plankton 76': get_event_ids(net_76_done),
                'plankton live':  get_event_ids(live_tow),
                'mooring deployed': get_event_ids(mooring_deployed),
                'mooring recovered': get_event_ids(mooring_recovered),
                'argo': get_event_ids(argo_done),
            })

    return station_list


def station_report(request, database, mission_id):
    mission = core_models.Mission.objects.get(pk=mission_id)
    station_list = get_station_list(database)

    header = ['station', 'date (UTC)', 'latitude', 'longitude', 'depth', 'ctd', 'rosette', 'biol station', 'xbt', 'vpr',
              'plankton multinet', 'plankton 200', 'plankton 76', 'plankton live', 'mooring deployed',
              'mooring recovered', 'argo']
    data = ",".join(header) + "\n"

    for station in station_list:
        data += (f'{station["station"]},{station["date"]},{station["latitude"]},'
                 f'{station["longitude"]},{station["depth"]},'
                 f'{station["ctd"]},{station["rosette"]},'
                 f'{station["biol station"]},{station["xbt"]},{station["vpr"]},'
                 f'{station["plankton multinet"]},{station["plankton 200"]},'
                 f'{station["plankton 76"]},{station["plankton live"]},'
                 f'{station["mooring deployed"]},{station["mooring recovered"]},'
                 f'{station["argo"]}'
                 f'\n')

    file_to_send = ContentFile(data)

    response = HttpResponse(file_to_send, content_type="text/csv")
    response['Content-Length'] = file_to_send.size
    response['Content-Disposition'] = 'attachment; filename="' + mission.name + f'_Station_Report.csv"'

    return response


def elog(request, database, mission_id):
    mission = core_models.Mission.objects.get(pk=mission_id)

    header = ['Mission', 'Event', 'Station', 'Instrument', 'AVG_SOUNDING', 'Min_Lat', 'Min_Lon', 'Max_Lat', 'Max_Lon',
              'SDATE', 'STIME', 'EDATE', 'ETIME', 'DURATION', 'ELAPSED_TIME', 'COMMENTS']

    events = mission.events.annotate(start=Min("actions__date_time")).order_by('start')

    data = ",".join(header) + "\n"
    last_event = None
    for event in events:
        row = [mission.name, event.event_id, event.station.name, event.instrument.name]

        sounding = event.actions.all().exclude(sounding=None).values_list('sounding', flat=True)
        avg_sounding = ''
        if None not in sounding:
            avg_sounding = np.average(sounding)
        avg_sounding = '' if np.isnan(avg_sounding) or avg_sounding == '' else avg_sounding
        row.append(avg_sounding)

        slocation = event.start_location
        elocation = event.end_location
        row.append(min(slocation[0], elocation[0]))
        row.append(min(slocation[1], elocation[1]))
        row.append(max(slocation[0], elocation[0]))
        row.append(max(slocation[1], elocation[1]))

        sdate = event.start_date
        row.append(sdate.strftime('%Y-%m-%d'))
        row.append(sdate.strftime('%H:%M:%S'))

        edate = event.end_date
        row.append(edate.strftime('%Y-%m-%d'))
        row.append(edate.strftime('%H:%M:%S'))

        row.append(convert_timedelta_to_string(event.drift_time))

        elapsed = "00:00:00"
        if last_event:
            delta = (event.start_date - last_event.end_date)
            elapsed = convert_timedelta_to_string(delta)

        row.append(elapsed)

        comments = ""
        for action in event.actions.all():
            if action.comment:
                if comments != "":
                    comments += " "
                comments += f"{action.get_type_display()}: {action.comment}"

        if comments != "":
            comments = f"\"{comments}\""

        row.append(comments)
        # make sure all values are strings.
        row = [str(val) for val in row]

        data += ",".join(row) + "\n"
        last_event = event

    file_to_send = ContentFile(data)

    response = HttpResponse(file_to_send, content_type="text/csv")
    response['Content-Length'] = file_to_send.size
    response['Content-Disposition'] = 'attachment; filename="' + mission.name + f'_Elog_Summary.csv"'

    return response


def error_report(request, database, mission_id):
    mission = core_models.Mission.objects.get(pk=mission_id)

    header = ['MISSION', "FILE", "LINE/OBJECT", 'ERROR_TYPE', 'MESSAGE']
    data = ",".join(header) + '\n'

    file_errs = mission.file_errors.all()
    for error in file_errs:
        row = [mission.name, error.file_name, error.line, error.get_type_display(), error.message]
        data += ",".join([f"\"{str(val)}\"" for val in row]) + '\n'

    validation_errs = core_models.ValidationError.objects.filter(event__mission=mission)
    for error in validation_errs:
        row = [mission.name, "", f"Event: {error.event.event_id} - {error.event.station}", error.get_type_display(), error.message]
        data += ",".join([f"\"{str(val)}\"" for val in row]) + '\n'

    general_errs = mission.errors.all()
    for error in general_errs:
        row = [mission.name, "", "", error.get_type_display(), error.message]
        data += ",".join([f"\"{str(val)}\"" for val in row]) + '\n'

    file_to_send = ContentFile(data)

    response = HttpResponse(file_to_send, content_type="text/csv")
    response['Content-Length'] = file_to_send.size
    response['Content-Disposition'] = 'attachment; filename="' + mission.name + f'_Error_Report.csv"'

    return response


def profile_summary(request, database, mission_id):
    mission = core_models.Mission.objects.get(pk=mission_id)

    exclude = []
    mission_included_sampletypes = mission.mission_sample_types.all()

    # if the mean chl and/or phae sampletypes are used then there's no need to include an average of the chl and/or
    # phae sampletypes because that's what the chl_mean/phae_mean
    if 'chl_mean' in [st.name for st in mission_included_sampletypes]:
        exclude.append('chl')

    if 'phae_mean' in [st.name for st in mission_included_sampletypes]:
        exclude.append('phae')

    sample_types = mission.mission_sample_types.exclude(name__in=exclude).distinct()

    header = ['MISSION', "STATION", "EVENT", 'GEAR', 'PRESSURE', "SAMPLE"] + [st.name.upper() for st in sample_types]
    data = ",".join(header) + '\n'

    bottles = core_models.Bottle.objects.filter(event__mission=mission).order_by('bottle_id')
    for bottle in bottles:
        event = bottle.event
        row = [event.mission, event.station, event.event_id, event.instrument.get_type_display(),
               bottle.pressure, bottle.bottle_id]
        for st in sample_types:
            if(sample := bottle.samples.filter(type=st)).exists():
                avg = sample[0].discrete_values.aggregate(Avg("value"))
                row.append(avg['value__avg'])
            else:
                row.append("")
        data += ",".join([str(val) for val in row]) + '\n'

    file_to_send = ContentFile(data)

    response = HttpResponse(file_to_send, content_type="text/csv")
    response['Content-Length'] = file_to_send.size
    response['Content-Disposition'] = 'attachment; filename="' + mission.name + f'_Profile_Summary.csv"'

    return response


def std_sample_report(request, database, mission_id, **kwargs):
    mission = core_models.Mission.objects.get(pk=mission_id)

    data = ",".join(kwargs['headers']) + '\n'

    bottles = core_models.Bottle.objects.filter(event__mission_id=mission_id).order_by('bottle_id')

    for bottle in bottles:
        row = [bottle.event.station, bottle.event.event_id, bottle.pressure, bottle.bottle_id]
        for sensor in kwargs['sensors']:
            sensor = bottle.samples.filter(type__name__iexact=sensor)
            if sensor.exists():
                row += sensor.values_list('discrete_values__value', flat=True)
            else:
                row.append('')

        for sample in kwargs['samples']:
            sample = bottle.samples.filter(type__name__iexact=sample)
            if sample.exists():
                row += sample.values_list('discrete_values__value', flat=True)
            else:
                row.append('')
        data += ",".join([str(val) for val in row]) + '\n'

    file_to_send = ContentFile(data)

    response = HttpResponse(file_to_send, content_type="text/csv")
    response['Content-Length'] = file_to_send.size
    response['Content-Disposition'] = f'attachment; filename="{mission.name}_{kwargs["report_name"]}.csv"'

    return response


# The problem with this report is it depends on there being a SampleType with a short name 'oxy'
# if they user has named it anything else, this report won't contain loaded oxygen samples
def oxygen_report(request, database, mission_id):
    sensors = ['Sbeox0ML/L', 'Sbeox1ML/L']
    samples = ['oxy']
    header = ["STATION", "EVENT", 'PRESSURE', "SAMPLE_ID", 'Oxy_CTD_P', 'Oxy_CTD_S', 'Oxy_W_Rep1', 'Oxy_W_Rep2']

    return std_sample_report(request, database=database, mission_id=mission_id, report_name='Oxygen_Rpt',
                             headers=header, sensors=sensors, samples=samples)


# The problem with this report is it depends on there being a SampleType with a short name 'sal'
# if they user has named it anything else, this report won't contain loaded oxygen samples
def salt_report(request, database, mission_id):
    sensors = ['t090C', 't190C', 'c0S/m', 'c1S/m', 'Sal00', 'Sal11']
    samples = ['salts']
    header = ["STATION", "EVENT", 'PRESSURE', "SAMPLE_ID", 'Temp_CTD_P', 'Temp_CTD_S', 'Cond_CTD_P', 'Cond_CTD_S',
              'Sal_CTD_P', 'Sal_CTD_S', 'Sal_Rep1', 'Sal_Rep2']

    return std_sample_report(request, database=database, mission_id=mission_id, report_name='Salinity_Summary', headers=header,
                             sensors=sensors, samples=samples)


# The problem with this report is it depends on there being a SampleType with a short name 'chl'
# if they user has named it anything else, this report won't contain loaded oxygen samples
def chl_report(request, database, mission_id):
    mission = core_models.Mission.objects.get(pk=mission_id)
    sensors = [s.name for s in mission.mission_sample_types.filter(long_name__icontains='fluorescence')]

    header = ["STATION", "EVENT", 'PRESSURE', "SAMPLE_ID"]
    header += sensors
    header += ['Chl_Rep1', 'Chl_Rep2']
    samples = ['chl']

    return std_sample_report(request, database=database, mission_id=mission_id, report_name='Chl_Summary', headers=header,
                             sensors=sensors, samples=samples)


url_prefix = "<str:database>/report"
report_urls = [
    path(f'{url_prefix}/elog/<int:mission_id>/', elog, name="hx_report_elog"),
    path(f'{url_prefix}/error/<int:mission_id>/', error_report, name="hx_report_error"),
    path(f'{url_prefix}/profile_sumamry/<int:mission_id>/', profile_summary, name="hx_report_profile"),
    path(f'{url_prefix}/oxygen/<int:mission_id>/', oxygen_report, name="hx_report_oxygen"),
    path(f'{url_prefix}/salinity/<int:mission_id>/', salt_report, name="hx_report_salt"),
    path(f'{url_prefix}/chl/<int:mission_id>/', chl_report, name="hx_report_chl"),
    path(f'{url_prefix}/station/<int:mission_id>/', station_report, name="hx_report_station"),
]
