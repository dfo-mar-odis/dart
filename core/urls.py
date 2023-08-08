from django.urls import path

from . import views, htmx


app_name = 'core'

urlpatterns = [
    path('mission/', views.MissionFilterView.as_view(), name="mission_filter"),
    path('mission/new/', views.MissionCreateView.as_view(), name="mission_new"),
    path('mission/update/<int:pk>/', views.MissionUpdateView.as_view(), name="mission_edit"),
    path('mission/delete/<int:mission_id>/', htmx.mission_delete, name="mission_delete"),

    path('mission/event/<int:pk>/', views.EventDetails.as_view(), name="event_details"),

    path('mission/event/hx/new/', views.hx_event_update, name="hx_event_new"),
    path('mission/event/hx/new/<int:mission_id>/', views.hx_event_new_delete, kwargs={'event_id': 0}, name="hx_event_new"),
    path('mission/event/hx/select/<int:event_id>/', views.hx_event_select, name="hx_event_select"),
    path('mission/event/hx/delete/<int:event_id>', views.hx_event_new_delete, kwargs={'mission_id': 0}, name="hx_event_delete"),
    path('mission/event/hx/update/', views.hx_event_update, kwargs={'event_id': 0}, name="hx_event_update"),
    path('mission/event/hx/update/<int:event_id>/', views.hx_event_update, name="hx_event_update"),
    path('mission/event/hx/list/<int:mission_id>/', views.hx_list_event, name="hx_event_list"),

    path('mission/event/action/hx/new/', views.hx_new_action, kwargs={'event_id': 0}, name="hx_action_new"),
    path('mission/event/action/hx/update/<int:action_id>/', views.hx_update_action, name="hx_action_update"),
    path('mission/event/action/hx/delete/<int:action_id>/', views.hx_update_action, name="hx_action_delete"),
    path('mission/event/action/hx/list/<int:event_id>/', views.hx_list_action, name="hx_action_list"),
    path('mission/event/action/hx/list/<int:event_id>/<str:editable>/', views.hx_list_action, name="hx_action_list"),

    path('mission/event/attachment/hx/new/', views.hx_new_attachment, name="hx_attachment_new"),
    path('mission/event/attachment/hx/update/<int:action_id>/', views.hx_update_attachment, name="hx_attachment_update"),
    path('mission/event/attachment/hx/delete/<int:action_id>/', views.hx_update_attachment, name="hx_attachment_delete"),
    path('mission/event/attachment/hx/list/<int:event_id>/', views.hx_list_attachment, name="hx_attachment_list"),
    path('mission/event/attachment/hx/list/<int:event_id>/<str:editable>/', views.hx_list_attachment, name="hx_attachment_list"),
]

htmx_urlpatterns = [
    path('mission/list/', htmx.list_missions, name="hx_list_missions"),
    path('hx/mission/delete/<int:mission_id>/', htmx.hx_mission_delete, name="hx_mission_delete"),
    path('geographic_region/add/', htmx.add_geo_region, name="hx_geo_region_add"),
    path('update_regions/', htmx.update_geographic_regions, name="hx_update_regions"),
    path('mission/upload/elog/<int:mission_id>/', htmx.upload_elog, name="hx_upload_elog"),
    path('mission/errors/<int:mission_id>/', htmx.get_file_errors, name="hx_get_file_errors"),
    path('event/action/blank/<int:event_id>/', htmx.event_action, name="hx_get_blank_action"),
    path('event/action/list/<int:event_id>/', htmx.event_list_action, name="hx_list_actions"),

]

urlpatterns = urlpatterns + htmx_urlpatterns