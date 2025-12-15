from django.urls import path

from . import views
from . import form_sample_file_config

app_name = 'settingsdb'

urlpatterns = [
    path('mission/', views.MissionFilterView.as_view(), name="mission_filter"),
    path('mission/view/list/', views.list_missions, name="mission_filter_list_missions"),
    path('mission/dir/new/', views.add_mission_dir, name="update_mission_directory"),

    path('sample_file_config/', views.SampleFileConfigView.as_view(), name="sample_file_config"),

    path('<str:database>/migrate/', views.migrate_database, name="migrate_database"),
    path('<int:station_id>/report/fixstation/', views.fixstation, name="fixstation"),
]

urlpatterns.extend(form_sample_file_config.urlpatterns)

