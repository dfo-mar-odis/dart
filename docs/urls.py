from django.urls import path

from docs import views


app_name = 'docs'

urlpatterns = [
    path('', views.Home.as_view(), name="index"),
    path('mission/mission_filter', views.MissionFilter.as_view(), name="mission_filter"),
    path('mission/new_mission_form', views.NewMissionForm.as_view(), name="new_mission_form"),
    path('mission/mission_events', views.MissionEvents.as_view(), name="mission_events"),
    path('mission/mission_samples', views.MissionSamples.as_view(), name="mission_samples"),
    path('mission/sample_types', views.SampleTypes.as_view(), name="sample_types"),
]