from bs4 import BeautifulSoup

from django.utils.translation import gettext as _
from django.http import HttpResponse
from django.forms import ModelForm
from django.urls import path, reverse
from django.template.loader import render_to_string

from user_settings import models as user_models
from dart.utils import diropenbox_on_top


class DatabaseLocationForm(ModelForm):

    class Meta:
        model = user_models.LocalSetting
        fields = ['database_location']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if (default:=user_models.LocalSetting.objects.filter(connected=True)).exists():
            default = default.first()
        else:
            default = user_models.LocalSetting.objects.get_or_create(connected=True)[0]

        self.fields['database_location'].choices = [(default.pk, default.database_location), (0, ''), (-1, '--- New ---')]
        self.fields['database_location'].choices += [(dir.pk, dir.database_location) for dir in user_models.LocalSetting.objects.all() if dir!=default]
        self.fields['database_location'].widget.attrs['hx-post'] = reverse('dart:form_db_location_new')
        self.fields['database_location'].widget.attrs['hx-swap'] = 'outerHTML'


def update_form(location_id):
    soup = BeautifulSoup('', 'html.parser')

    connected_locations = user_models.LocalSetting.objects.filter(connected=True)
    for connected in connected_locations:
        connected.connected = False
    user_models.LocalSetting.objects.bulk_update(connected_locations, ['connected'])

    new_location = user_models.LocalSetting.objects.get(pk=location_id)
    new_location.connected = True
    new_location.save()

    context = {
        'form': DatabaseLocationForm()
    }

    form_html = render_to_string('dart/forms/database_location_form.html', context=context)
    form_soup = BeautifulSoup(form_html, 'html.parser')
    soup.append(form_soup.find(id='id_database_location'))
    response = HttpResponse(soup)
    response['HX-Trigger'] = "reload_missions"
    return response

def new_location(request):
    location_id = request.POST.get('database_location', -1)

    result = None
    if location_id == "-1":
        # Trigger directory selection dialog
        result = diropenbox_on_top(title=_("Selected a Mission Directory"))

    if result:
        dir = user_models.LocalSetting.objects.get_or_create(database_location=result)[0]
        location_id = dir.pk
    elif int(location_id) <= 0:
        if(dir := user_models.LocalSetting.objects.filter(connected=True)).exists():
            dir = dir.first()
        else:
            dir = user_models.LocalSetting.objects.first()

        location_id = dir.pk

    return update_form(location_id)


def remove_location(request):
    # can't remove the "new" or default locations
    if int(location_id:=request.POST.get('database_location', -1)) != (-1 and 1):
        user_models.LocalSetting.objects.get(pk=location_id).delete()
        location_id = 1  # 1 should be the default './missions' directory

    return update_form(location_id)

urlpatterns = [
    path("db_location/new/", new_location, name="form_db_location_new"),
    path("db_location/remove/", remove_location, name="form_db_location_remove_selected"),
]