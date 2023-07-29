from django.urls import path

from . import views, utils


app_name = 'core'

urlpatterns = [
    path('mission/', views.MissionFilterView.as_view(), name="mission_filter"),
    path('mission/new/', views.MissionCreateView.as_view(), name="mission_new"),
    path('mission/update/<int:pk>/', views.MissionUpdateView.as_view(), name="mission_update"),
    path('mission/delete/', utils.mission_delete, name="mission_delete"),

    path('mission/event/<int:pk>/', views.EventDetails.as_view(), name="event_details"),
]

htmx_urlpatterns = [
    path('geographic_region/add/', utils.add_geo_region, name="geo_region_add"),
    path('update_regions/', utils.update_geographic_regions, name="update_regions"),
    path('mission/upload/elog/<int:mission_id>/', utils.upload_elog, name="upload_elog"),
    path('mission/select/<int:mission_id>/<int:event_id>/', utils.select_event, name="select_event")
]

urlpatterns = urlpatterns + htmx_urlpatterns