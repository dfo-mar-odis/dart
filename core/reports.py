from datetime import datetime, timedelta

from django.core.files.base import ContentFile
from django.db.models import Min, Avg
from django.http import HttpResponse

from . import models as core_models


def convert_timedelta_to_string(delta: timedelta) -> str:
    hours, rem = divmod(delta.total_seconds(), 3600)
    minutes, seconds = divmod(rem, 60)
    days = f"{int(delta.days):02}" if delta.days > 0 else "00"
    hours = f"{int(hours):02}" if hours > 0 else "00"
    minutes = f"{int(minutes):02}" if minutes > 0 else "00"
    seconds = f"{int(seconds):02}" if seconds > 0 else "00"
    elapsed = f"{days}:{hours}:{minutes}:{seconds}"

    return elapsed


def elog(request, **kwargs):
    mission_id = kwargs['mission_id']
    mission = core_models.Mission.objects.get(pk=mission_id)

    header = ['Event', 'Station', 'Instrument', 'Min_Lat', 'Min_Lon', 'Max_Lat', 'Max_lon', 'SDate', 'STime',
              'EDate', 'Etime', 'Duration', 'Name', 'Description', 'Elapsed_Time', 'Comments']

    events = core_models.Event.objects.filter(mission_id=mission_id).annotate(
        start=Min("actions__date_time")).order_by('start')

    data = ",".join(header) + "\n"
    last_event = None
    for event in events:
        row = [event.event_id, event.station.name, event.instrument.name]

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
        row.append(mission.name)
        elapsed = "00:00:00:00"
        if last_event:
            delta = (event.start_date - last_event.end_date)
            elapsed = convert_timedelta_to_string(delta)

        row.append(elapsed)

        comments = ""
        for action in event.actions.all():
            if action.comment:
                comments += f"###{action.get_type_display()}###: {action.comment}"
        row.append(comments)
        # make sure all values are strings.
        row = [str(val) for val in row]

        data += ",".join(row) + "\n"
        last_event = event

    file_to_send = ContentFile(data)

    response = HttpResponse(file_to_send, content_type="text/csv")
    response['Content-Length'] = file_to_send.size
    response['Content-Disposition'] = 'attachment; filename="' + mission.name + '_Elog_Summary.csv"'

    return response


def error_report(request, **kwargs):
    mission_id = kwargs['mission_id']
    mission = core_models.Mission.objects.get(pk=mission_id)

    header = ['Mission', "File", "Line/Object", 'Error_Type', 'Message']
    data = ",".join(header) + '\n'

    file_errs = core_models.FileError.objects.filter(mission=mission)
    for error in file_errs:
        row = [mission.name, error.file_name, error.line, error.get_type_display(), error.message]
        data += ",".join([f"\"{str(val)}\"" for val in row]) + '\n'

    validation_errs = core_models.ValidationError.objects.filter(event__mission=mission)
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
    response['Content-Disposition'] = 'attachment; filename="' + mission.name + '_Error_Report.csv"'

    return response


def profile_summary(request, **kwargs):
    mission_id = kwargs['mission_id']
    mission = core_models.Mission.objects.get(pk=mission_id)

    sample_types = core_models.SampleType.objects.filter(samples__bottle__event__mission=mission).distinct()

    header = ['Mission', "Station", "Event", 'Gear', 'Pressure', "Sample"] + [st.short_name for st in sample_types]
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
    response['Content-Disposition'] = 'attachment; filename="' + mission.name + '_Profile_Summary.csv"'

    return response


def std_sample_report(request, **kwargs):
    mission_id = kwargs['mission_id']
    mission = core_models.Mission.objects.get(pk=mission_id)

    sample_types = core_models.SampleType.objects.filter(short_name__in=kwargs['sensors'])

    data = ",".join(kwargs['headers']) + '\n'

    bottles = core_models.Bottle.objects.filter(event__mission_id=mission_id).order_by('bottle_id')

    for bottle in bottles:
        row = [bottle.event.station, bottle.event.event_id, bottle.pressure, bottle.bottle_id]
        row += bottle.samples.filter(type__in=sample_types).values_list('discrete_values__value', flat=True)
        row += bottle.samples.filter(type__short_name__in=kwargs['samples']).values_list('discrete_values__value',
                                                                                         flat=True)
        data += ",".join([str(val) for val in row]) + '\n'

    file_to_send = ContentFile(data)

    response = HttpResponse(file_to_send, content_type="text/csv")
    response['Content-Length'] = file_to_send.size
    response['Content-Disposition'] = f'attachment; filename="{mission.name}_{kwargs["report_name"]}.csv"'

    return response


# The problem with this report is it depends on there being a SampleType with a short name 'oxy'
# if they user has named it anything else, this report won't contain loaded oxygen samples
def oxygen_report(request, **kwargs):
    sensors = ['sbeox0V', 'sbeox1V']
    samples = ['oxy']
    header = ["Station", "Event", 'Pressure', "Sample", 'Oxy_CTD_P', 'Oxy_CTD_S', 'oxy_W_Rep1', 'oxy_W_Rep2']

    return std_sample_report(request, report_name='Oxygen_Summary', headers=header,
                             sensors=sensors, samples=samples, **kwargs)


# The problem with this report is it depends on there being a SampleType with a short name 'sal'
# if they user has named it anything else, this report won't contain loaded oxygen samples
def salt_report(request, **kwargs):
    sensors = ['t090C', 't190C', 'c0S/m', 'c1S/m', 'Sal00', 'Sal11']
    samples = ['sal']
    header = ["Station", "Event", 'Pressure', "Sample", 'Temp_CTD_P', 'Temp_CTD_S', 'Cond_CTD_P', 'Cond_CTD_S',
              'Sal_CTD_P', 'Sal_CTD_S', 'Sal_Rep1', 'Sal_Rep2']

    return std_sample_report(request, report_name='Salinity_Summary', headers=header,
                             sensors=sensors, samples=samples, **kwargs)


# The problem with this report is it depends on there being a SampleType with a short name 'chl'
# if they user has named it anything else, this report won't contain loaded oxygen samples
def chl_report(request, **kwargs):
    sensors = ['flECO-AFL', 'wetCDOM']
    header = ["Station", "Event", 'Pressure', "Sample", 'flECO-AFL', 'wetCDOM', 'Chl_Rep1', 'Chl_Rep2']
    samples = ['chl']

    return std_sample_report(request, report_name='Chl_Summary', headers=header,
                             sensors=sensors, samples=samples, **kwargs)


