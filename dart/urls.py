from django.urls import path, include

from dart import views
from dart.forms import (mission_list_filter_form, mission_settings_form, mission_events, mission_event_detail_form,
                        event_action_form)


app_name = 'dart'
urlpatterns = []

urlpatterns.extend(views.urlpatterns)
urlpatterns.extend(event_action_form.urlpatterns)
urlpatterns.extend(mission_event_detail_form.urlpatterns)
urlpatterns.extend(mission_events.urlpatterns)
urlpatterns.extend(mission_settings_form.urlpatterns)
urlpatterns.extend(mission_list_filter_form.urlpatterns)
