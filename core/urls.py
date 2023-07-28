from django.urls import path

from . import views, utils


app_name = 'core'

urlpatterns = [
    path('mission/', views.MissionFilterView.as_view(), name="mission_filter"),
    path('mission/new/', views.MissionCreateView.as_view(), name="mission_new"),
    path('mission/delete/', utils.mission_delete, name="mission_delete"),
]

htmx_urlpatterns = [
    path('geographic_region/add/', utils.add_geo_region, name="geo_region_add"),
    path('update_regions', utils.update_geographic_regions, name="update_regions"),
]

urlpatterns = urlpatterns + htmx_urlpatterns