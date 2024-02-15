from django.urls import path

from . import views

app_name = 'settingsdb'

urlpatterns = [
    path('mission/', views.MissionFilterView.as_view(), name="mission_filter"),
    path('mission/view/list/', views.list_missions, name="mission_filter_list_missions"),
    path('mission/dir/new/', views.add_mission_dir, name="update_mission_directory"),

    path('<str:database>/migrate/', views.migrate_database, name="migrate_database"),
]
