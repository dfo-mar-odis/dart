from django.urls import path

import core.views_mission_sample
from . import views, views_mission_sample, htmx

app_name = 'core'

urlpatterns = [
    # ###### SAMPLE TYPES AND FILE CONFIGURATIONS ###### #

    # for testing the sample type form
    path('mission/sample/test/<int:pk>/', views_mission_sample.SampleDetails.as_view()),

    # used to reload elements on the sample form if a GET htmx request
    path('sample_type/hx/', views_mission_sample.load_sample_type, name="load_sample_type"),
    path('sample_type/hx/<int:config>/', views_mission_sample.load_sample_type, name="load_sample_type"),

    # show the create a sample type form
    path('sample_type/hx/new/', views_mission_sample.new_sample_type, name="new_sample_type"),
    path('sample_type/hx/new/<int:sample_type_id>/', views_mission_sample.new_sample_type, name="new_sample_type"),

    # save the sample type
    path('sample_type/hx/save/', views_mission_sample.save_sample_type, name="save_sample_type"),
    path('sample_type/hx/update/<int:sample_type_id>/', views_mission_sample.save_sample_type, name="save_sample_type"),

    # delete a sample file configuration or load samples using that file configuration
    path('sample_type/hx/load/<int:sample_type_id>/', views_mission_sample.load_samples, name="load_samples"),
    path('sample_type/hx/delete/<int:sample_type_id>/', views_mission_sample.delete_sample_type,
         name="delete_sample_type"),

    # ###### sample details ###### #

    path('mission/sample/<int:pk>/', views.SampleDetails.as_view(), name="sample_details"),
    path('mission/sample/hx/ctd/<int:mission_id>/', views_mission_sample.hx_sample_upload_ctd,
         name="hx_sample_upload_ctd"),
    path('mission/sample/hx/delete/<int:mission_id>/<int:sample_type_id>/', views_mission_sample.hx_sample_delete,
         name="hx_sample_delete"),
    path('mission/sample/hx/list/<int:mission_id>', views_mission_sample.hx_list_samples, name="hx_sample_list"),
    path('mission/sample/hx/list/<int:mission_id>/<int:sensor_id>', views_mission_sample.hx_list_samples,
         name="hx_sample_list"),

    # ###### Mission details and setting ###### #

    path('mission/', views.MissionFilterView.as_view(), name="mission_filter"),
    path('mission/new/', views.MissionCreateView.as_view(), name="mission_new"),
    path('mission/update/<int:pk>/', views.MissionUpdateView.as_view(), name="mission_edit"),
    path('mission/delete/<int:mission_id>/', htmx.mission_delete, name="mission_delete"),

    # ###### Mission Events (elog) ###### #

    path('mission/event/<int:pk>/', views.EventDetails.as_view(), name="event_details"),

    path('mission/event/hx/new/', views.hx_event_update, name="hx_event_new"),
    path('mission/event/hx/new/<int:mission_id>/', views.hx_event_new_delete, kwargs={'event_id': 0},
         name="hx_event_new"),
    path('mission/event/hx/delete/<int:event_id>', views.hx_event_new_delete, kwargs={'mission_id': 0},
         name="hx_event_delete"),
    path('mission/event/hx/select/<int:event_id>/', views.hx_event_select, name="hx_event_select"),
    path('mission/event/hx/update/', views.hx_event_update, kwargs={'event_id': 0}, name="hx_event_update"),
    path('mission/event/hx/update/<int:event_id>/', views.hx_event_update, name="hx_event_update"),
    path('mission/event/hx/list/<int:mission_id>/', views.hx_list_event, name="hx_event_list"),

    path('mission/event/action/hx/new/', views.hx_new_action, kwargs={'event_id': 0}, name="hx_action_new"),
    path('mission/event/action/hx/update/<int:action_id>/', views.hx_update_action, name="hx_action_update"),
    path('mission/event/action/hx/delete/<int:action_id>/', views.hx_update_action, name="hx_action_delete"),
    path('mission/event/action/hx/list/<int:event_id>/', views.hx_list_action, name="hx_action_list"),
    path('mission/event/action/hx/list/<int:event_id>/<str:editable>/', views.hx_list_action, name="hx_action_list"),

    path('mission/event/attachment/hx/new/', views.hx_new_attachment, name="hx_attachment_new"),
    path('mission/event/attachment/hx/update/<int:action_id>/', views.hx_update_attachment,
         name="hx_attachment_update"),
    path('mission/event/attachment/hx/delete/<int:action_id>/', views.hx_update_attachment,
         name="hx_attachment_delete"),
    path('mission/event/attachment/hx/list/<int:event_id>/', views.hx_list_attachment, name="hx_attachment_list"),
    path('mission/event/attachment/hx/list/<int:event_id>/<str:editable>/', views.hx_list_attachment,
         name="hx_attachment_list"),
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
