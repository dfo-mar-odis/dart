from django.urls import path

from . import views, htmx


app_name = 'core'

urlpatterns = [
    path('mission/', views.MissionFilterView.as_view(), name="mission_filter"),
    path('mission/new/', views.MissionCreateView.as_view(), name="mission_new"),
    path('mission/update/<int:pk>/', views.MissionUpdateView.as_view(), name="mission_edit"),
    path('mission/delete/<int:mission_id>/', htmx.mission_delete, name="mission_delete"),

    path('mission/event/<int:pk>/', views.EventDetails.as_view(), name="event_details"),
    path('mission/event/new/<int:mission_id>/', views.EventCreateView.as_view(), name="event_new"),
    path('mission/event/update/<int:pk>/', views.EventUpdateView.as_view(), name="event_edit"),
]

htmx_urlpatterns = [
    path('mission/list/', htmx.list_missions, name="hx_list_missions"),
    path('hx/mission/delete/<int:mission_id>/', htmx.hx_mission_delete, name="hx_mission_delete"),
    path('geographic_region/add/', htmx.add_geo_region, name="hx_geo_region_add"),
    path('update_regions/', htmx.update_geographic_regions, name="hx_update_regions"),
    path('mission/upload/elog/<int:mission_id>/', htmx.upload_elog, name="hx_upload_elog"),
    path('mission/select/<int:mission_id>/<int:event_id>/', htmx.select_event, name="hx_select_event"),
    path('mission/errors/<int:mission_id>/', htmx.get_file_errors, name="hx_get_file_errors"),
    path('event/action/blank/<int:event_id>/', htmx.event_action, name="hx_get_blank_action"),
    path('event/action/add/<int:event_id>/', htmx.event_action, name="hx_add_action"),
    path('event/action/list/<int:event_id>/', htmx.event_list_action, name="hx_list_actions"),

]

urlpatterns = urlpatterns + htmx_urlpatterns