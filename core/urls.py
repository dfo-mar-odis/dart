from django.urls import path

import core.views_mission_event
from . import views, views_mission_sample, views_mission_event, views_sample_type, views_mission_plankton, htmx, reports

app_name = 'core'

urlpatterns = [
    # ###### Plankton loading ###### #
    path('plankton/<int:pk>/', views_mission_plankton.PlanktonDetails.as_view(), name="plankton_details"),
    path('plankton/', views_mission_plankton.load_plankton, name="load_plankton"),

    # ###### SAMPLE TYPES AND FILE CONFIGURATIONS ###### #
    # show the create a sample type form
    path('sample_type/', views_sample_type.SampleTypeList.as_view(), name="sample_type_details"),
    path('sample_type/hx/new/', views_mission_sample.new_sample_type, name="new_sample_type"),
    path('sample_type/hx/save/', views_sample_type.save_sample_type, name="save_sample_type"),
    path('sample_type/hx/save/<int:sample_type_id>/', views_sample_type.save_sample_type, name="save_sample_type"),
    path('sample_type/hx/load/<int:sample_type_id>/', views_sample_type.load_sample_type, name="load_sample_type"),
    path('sample_type/hx/edit/', views_sample_type.edit_sample_type, name="edit_sample_type"),
    path('sample_type/hx/edit/<int:sample_type_id>/', views_sample_type.edit_sample_type, name="edit_sample_type"),
    path('sample_type/hx/delete/<int:sample_type_id>/', views_sample_type.delete_sample_type,
         name="delete_sample_type"),

    # for testing the sample config form
    path('mission/sample/test/<int:pk>/', views_mission_sample.SampleDetails.as_view()),

    # used to reload elements on the sample form if a GET htmx request
    path('sample_config/hx/', views_mission_sample.load_sample_config, name="load_sample_config"),
    path('sample_config/hx/<int:config>/', views_mission_sample.load_sample_config, name="load_sample_config"),

    # show the create a sample config form
    path('sample_config/hx/new/', views_mission_sample.new_sample_config, name="new_sample_config"),
    path('sample_config/hx/new/<int:config_id>/', views_mission_sample.new_sample_config, name="new_sample_config"),

    # save the sample config
    path('sample_config/hx/save/', views_mission_sample.save_sample_config, name="save_sample_config"),
    path('sample_config/hx/update/<int:config_id>/', views_mission_sample.save_sample_config,
         name="save_sample_config"),

    # delete a sample file configuration or load samples using that file configuration
    path('sample_config/hx/load/<int:config_id>/', views_mission_sample.load_samples, name="load_samples"),
    path('sample_config/hx/delete/<int:config_id>/', views_mission_sample.delete_sample_config,
         name="delete_sample_config"),

    # ###### sample details ###### #

    path('mission/sample/<int:pk>/', views_mission_sample.SampleDetails.as_view(), name="sample_details"),
    path('mission/sample/<int:pk>/<int:sample_type_id>/', views_mission_sample.SampleDetails.as_view(),
         name="sample_details"),
    path('mission/sample/hx/ctd/<int:mission_id>/', views_mission_sample.hx_sample_upload_ctd,
         name="hx_sample_upload_ctd"),
    path('mission/sample/hx/delete/<int:mission_id>/<int:sample_type_id>/', views_mission_sample.hx_sample_delete,
         name="hx_sample_delete"),
    path('mission/sample/hx/list/<int:mission_id>', views_mission_sample.hx_list_samples, name="hx_sample_list"),
    path('mission/sample/hx/list/<int:mission_id>/<int:sensor_id>', views_mission_sample.hx_list_samples,
         name="hx_sample_list"),

    path('mission/sample/hx/datatype/', views_mission_sample.update_sample_type, name="hx_update_sample_type"),

    path('mission/sample/hx/upload/biochem/<int:mission_id>/<int:sample_type_id>/',
         views_mission_sample.upload_bio_chem, name="hx_upload_bio_chem"),

    # ###### Mission details and setting ###### #

    path('mission/', views.MissionFilterView.as_view(), name="mission_filter"),
    path('mission/new/', views.MissionCreateView.as_view(), name="mission_new"),
    path('mission/update/<int:pk>/', views.MissionUpdateView.as_view(), name="mission_edit"),
    path('mission/delete/<int:mission_id>/', htmx.mission_delete, name="mission_delete"),

    # ###### Mission Events (elog) ###### #

    path('mission/elog/<int:pk>/', views.ElogDetails.as_view(), name="elog_config"),
    path('mission/update/elog/<int:mission_id>/', views.hx_update_elog_config, name="update_elog_config"),

    path('mission/event/<int:pk>/', views_mission_event.EventDetails.as_view(), name="event_details"),

    path('mission/event/hx/new/', views_mission_event.hx_event_update, name="hx_event_new"),
    path('mission/event/hx/new/<int:mission_id>/', views_mission_event.hx_event_new_delete, kwargs={'event_id': 0},
         name="hx_event_new"),
    path('mission/event/hx/delete/<int:event_id>', views_mission_event.hx_event_new_delete, kwargs={'mission_id': 0},
         name="hx_event_delete"),
    path('mission/event/hx/select/<int:event_id>/', views_mission_event.hx_event_select, name="hx_event_select"),
    path('mission/event/hx/update/', views_mission_event.hx_event_update, kwargs={'event_id': 0}, name="hx_event_update"),
    path('mission/event/hx/update/<int:event_id>/', views_mission_event.hx_event_update, name="hx_event_update"),
    path('mission/event/hx/list/<int:mission_id>/', views_mission_event.hx_list_event, name="hx_event_list"),

    path('mission/event/action/hx/new/', views_mission_event.hx_new_action, kwargs={'event_id': 0}, name="hx_action_new"),
    path('mission/event/action/hx/update/<int:action_id>/', views_mission_event.hx_update_action, name="hx_action_update"),
    path('mission/event/action/hx/delete/<int:action_id>/', views_mission_event.hx_update_action, name="hx_action_delete"),
    path('mission/event/action/hx/list/<int:event_id>/', views_mission_event.hx_list_action, name="hx_action_list"),
    path('mission/event/action/hx/list/<int:event_id>/<str:editable>/', views_mission_event.hx_list_action, name="hx_action_list"),

    path('mission/event/attachment/hx/new/', views_mission_event.hx_new_attachment, name="hx_attachment_new"),
    path('mission/event/attachment/hx/update/<int:action_id>/', views_mission_event.hx_update_attachment,
         name="hx_attachment_update"),
    path('mission/event/attachment/hx/delete/<int:action_id>/', views_mission_event.hx_update_attachment,
         name="hx_attachment_delete"),
    path('mission/event/attachment/hx/list/<int:event_id>/', views_mission_event.hx_list_attachment, name="hx_attachment_list"),
    path('mission/event/attachment/hx/list/<int:event_id>/<str:editable>/', views_mission_event.hx_list_attachment,
         name="hx_attachment_list"),
]

htmx_urlpatterns = [
    path('mission/list/', htmx.list_missions, name="hx_list_missions"),
    path('hx/mission/delete/<int:mission_id>/', htmx.hx_mission_delete, name="hx_mission_delete"),
    path('geographic_region/add/', htmx.add_geo_region, name="hx_geo_region_add"),
    path('update_regions/', htmx.update_geographic_regions, name="hx_update_regions"),
    path('mission/upload/elog/<int:mission_id>/', views_mission_event.upload_elog, name="hx_upload_elog"),
    path('mission/errors/<int:mission_id>/', htmx.get_file_errors, name="hx_get_file_errors"),
    path('event/action/blank/<int:event_id>/', htmx.event_action, name="hx_get_blank_action"),
    path('event/action/list/<int:event_id>/', htmx.event_list_action, name="hx_list_actions"),

]

htmx_report_urls = [
    path('mission/report/elog/<int:mission_id>/', reports.elog, name="hx_report_elog"),
    path('mission/report/error/<int:mission_id>/', reports.error_report, name="hx_report_error"),
    path('mission/report/profile_sumamry/<int:mission_id>/', reports.profile_summary, name="hx_report_profile"),
    path('mission/report/oxygen/<int:mission_id>/', reports.oxygen_report, name="hx_report_oxygen"),
    path('mission/report/salinity/<int:mission_id>/', reports.salt_report, name="hx_report_salt"),
    path('mission/report/chl/<int:mission_id>/', reports.chl_report, name="hx_report_chl"),
]

urlpatterns = urlpatterns + htmx_urlpatterns + htmx_report_urls
