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


def elog(request, **kwargs):
    mission_id = kwargs['mission_id']
    mission = core_models.Mission.objects.using(database).get(pk=mission_id)

    header = ['Mission', 'Event', 'Station', 'INSTRUMENT', 'AVG_SOUNDING', 'MIN_LAT', 'MIN_LON', 'MAX_LAT', 'MAX_LON',
              'SDATE', 'STIME', 'EDATE', 'ETIME', 'DURATION', 'ELAPSED_TIME', 'COMMENTS']

    events = core_models.Event.objects.using(database).filter(trip__mission_id=mission_id).annotate(
        start=Min("actions__date_time")).order_by('start')

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


def error_report(request, **kwargs):
    mission_id = kwargs['mission_id']
    mission = core_models.Mission.objects.using(database).get(pk=mission_id)

    header = ['MISSION', "FILE", "LINE/OBJECT", 'ERROR_TYPE', 'MESSAGE']
    data = ",".join(header) + '\n'

    file_errs = core_models.FileError.objects.filter(mission=mission)
    for error in file_errs:
        row = [mission.name, error.file_name, error.line, error.get_type_display(), error.message]
        data += ",".join([f"\"{str(val)}\"" for val in row]) + '\n'

    validation_errs = core_models.ValidationError.objects.filter(event__trip__mission=mission)
    for error in validation_errs:
        row = [mission.name, "", f"Event: {error.event.event_id}", error.get_type_display(), error.message]
        data += ",".join([f"\"{str(val)}\"" for val in row]) + '\n'

    general_errs = core_models.Error.objects.filter(mission=mission)
    for error in general_errs:
        row = [mission.name, "", "", error.get_type_display(), error.message]
        data += ",".join([f"\"{str(val)}\"" for val in row]) + '\n'

    file_to_send = ContentFile(data)

    response = HttpResponse(file_to_send, content_type="text/csv")
    response['Content-Length'] = file_to_send.size
    response['Content-Disposition'] = 'attachment; filename="' + mission.name + f'_Error_Report.csv"'

    return response


def profile_summary(request, **kwargs):
    mission_id = kwargs['mission_id']
    mission = core_models.Mission.objects.using(database).get(pk=mission_id)

    exclude = []
    mission_included_sampletypes = core_models.MissionSampleType.objects.filter(samples__bottle__event__trip__mission_id=mission_id)

    # if the mean chl and/or phae sampletypes are used then there's no need to include an average of the chl and/or
    # phae sampletypes because that's what the chl_mean/phae_mean
    if 'chl_mean' in [st.short_name for st in mission_included_sampletypes]:
        exclude.append('chl')

    if 'phae_mean' in [st.short_name for st in mission_included_sampletypes]:
        exclude.append('phae')

    sample_types = core_models.MissionSampleType.objects.filter(
        samples__bottle__event__trip__mission=mission
    ).exclude(name__in=exclude).distinct()

    header = ['MISSION', "STATION", "EVENT", 'GEAR', 'PRESSURE', "SAMPLE"] + [st.short_name.upper() for st in sample_types]
    data = ",".join(header) + '\n'

    bottles = core_models.Bottle.objects.using(database).filter(event__trip__mission=mission).order_by('bottle_id')
    for bottle in bottles:
        event = bottle.event
        row = [event.trip.mission, event.station, event.event_id, event.instrument.get_type_display(),
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


def std_sample_report(request, **kwargs):
    mission_id = kwargs['mission_id']
    mission = core_models.Mission.objects.using(database).get(pk=mission_id)

    data = ",".join(kwargs['headers']) + '\n'

    bottles = core_models.Bottle.objects.using(database).filter(event__trip__mission_id=mission_id).order_by('bottle_id')

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
def oxygen_report(request, **kwargs):
    sensors = ['Sbeox0ML/L', 'Sbeox1ML/L']
    samples = ['oxy']
    header = ["STATION", "EVENT", 'PRESSURE', "SAMPLE_ID", 'Oxy_CTD_P', 'Oxy_CTD_S', 'Oxy_W_Rep1', 'Oxy_W_Rep2']

    return std_sample_report(request, report_name='Oxygen_Rpt', headers=header,
                             sensors=sensors, samples=samples, **kwargs)


# The problem with this report is it depends on there being a SampleType with a short name 'sal'
# if they user has named it anything else, this report won't contain loaded oxygen samples
def salt_report(request, **kwargs):
    sensors = ['t090C', 't190C', 'c0S/m', 'c1S/m', 'Sal00', 'Sal11']
    samples = ['salts']
    header = ["STATION", "EVENT", 'PRESSURE', "SAMPLE_ID", 'Temp_CTD_P', 'Temp_CTD_S', 'Cond_CTD_P', 'Cond_CTD_S',
              'Sal_CTD_P', 'Sal_CTD_S', 'Sal_Rep1', 'Sal_Rep2']

    return std_sample_report(request, report_name='Salinity_Summary', headers=header,
                             sensors=sensors, samples=samples, **kwargs)


# The problem with this report is it depends on there being a SampleType with a short name 'chl'
# if they user has named it anything else, this report won't contain loaded oxygen samples
def chl_report(request, **kwargs):
    mission_id = kwargs['mission_id']
    sensors = [s.name for s in core_models.MissionSampleType.objects.filter(mission_id=mission_id,
                                                                            long_name__icontains='fluorescence')]

    header = ["STATION", "EVENT", 'PRESSURE', "SAMPLE_ID"]
    header += sensors
    header += ['Chl_Rep1', 'Chl_Rep2']
    samples = ['chl']

    return std_sample_report(request, report_name='Chl_Summary', headers=header,
                             sensors=sensors, samples=samples, **kwargs)


report_urls = [
    path('mission/report/elog/<int:mission_id>/', elog, name="hx_report_elog"),
    path('mission/report/error/<int:mission_id>/', error_report, name="hx_report_error"),
    path('mission/report/profile_sumamry/<int:mission_id>/', profile_summary, name="hx_report_profile"),
    path('mission/report/oxygen/<int:mission_id>/', oxygen_report, name="hx_report_oxygen"),
    path('mission/report/salinity/<int:mission_id>/', salt_report, name="hx_report_salt"),
    path('mission/report/chl/<int:mission_id>/', chl_report, name="hx_report_chl"),
]
