from django.urls import path

from . import views

app_name = 'settingsdb'

urlpatterns = [
    path('mission/', views.MissionFilterView.as_view(), name="mission_filter"),
    path('mission/view/list/', views.list_missions, name="mission_filter_list_missions")
]
