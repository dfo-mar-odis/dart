from django.urls import path

from . import views, views_mission_sample, views_sample_type, views_mission_plankton
from . import views_mission_sample_type, views_mission_event
from . import form_biochem_database, form_btl_load, form_sample_type_config, form_mission_sample_type
from . import form_plankton_load, form_mission_settings, form_validation_biochem
from . import reports

app_name = 'core'


url_prefix = "<str:database>/elog"
urlpatterns = [
    # ###### Mission details and setting ###### #
    path('mission/new/', views.MissionCreateView.as_view(), name="mission_new"),
    path('mission/<str:database>/update/<int:pk>/', views.MissionUpdateView.as_view(), name="mission_edit"),

    # ###### Elog configuration ###### #
    path(f'{url_prefix}/<int:pk>/', views.ElogDetails.as_view(), name="elog_config"),
    path(f'{url_prefix}/update/<int:mission_id>/', views.hx_update_elog_config, name="update_elog_config"),

]

urlpatterns.extend(views_mission_event.mission_event_urls)
urlpatterns.extend(views_sample_type.sample_type_urls)
urlpatterns.extend(views_mission_sample.mission_sample_urls)
urlpatterns.extend(views_mission_sample_type.mission_sample_type_urls)
urlpatterns.extend(views_mission_plankton.plankton_urls)
urlpatterns.extend(form_btl_load.bottle_load_urls)
urlpatterns.extend(form_biochem_database.database_urls)
urlpatterns.extend(form_validation_biochem.database_urls)
urlpatterns.extend(form_sample_type_config.sample_type_config_urls)
urlpatterns.extend(form_mission_sample_type.sample_type_urls)
urlpatterns.extend(form_plankton_load.plankton_urls)
urlpatterns.extend(form_mission_settings.mission_urls)
urlpatterns.extend(reports.report_urls)
