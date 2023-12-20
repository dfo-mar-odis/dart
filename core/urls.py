from django.urls import path

from . import views, views_mission_sample, views_sample_type, htmx, reports, form_btl_load
from . import form_biochem_database, views_mission_event, views_mission_plankton

app_name = 'core'


urlpatterns = [
    # ###### Mission details and setting ###### #

    path('mission/', views.MissionFilterView.as_view(), name="mission_filter"),
    path('mission/new/', views.MissionCreateView.as_view(), name="mission_new"),
    path('mission/update/<int:pk>/', views.MissionUpdateView.as_view(), name="mission_edit"),
    path('mission/delete/<int:mission_id>/', htmx.mission_delete, name="mission_delete"),

    # ###### Elog configuration ###### #
    path('mission/elog/<int:pk>/', views.ElogDetails.as_view(), name="elog_config"),
    path('mission/update/elog/<int:mission_id>/', views.hx_update_elog_config, name="update_elog_config"),

]

urlpatterns.extend(views_mission_event.mission_event_urls)
urlpatterns.extend(views_sample_type.sample_type_urls)
urlpatterns.extend(views_mission_sample.mission_sample_urls)
urlpatterns.extend(views_mission_plankton.plankton_urls)
urlpatterns.extend(form_btl_load.bottle_load_urls)
urlpatterns.extend(form_biochem_database.database_urls)
urlpatterns.extend(htmx.htmx_urls)
urlpatterns.extend(reports.report_urls)
