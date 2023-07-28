"""dart2 URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
import importlib.util

from django.conf.urls.i18n import i18n_patterns
from django.conf import settings
from django.conf.urls.static import static

from django.contrib import admin
from django.urls import path, include

from core import views


# automatically load URLs for all registered apps
def get_registered_app_urls():
    url_list = {}
    for app in settings.REGISTERED_APPS:
        url = importlib.util.find_spec(app + ".urls")
        if url is not None:
            url_list[app] = path(app+'/', include(app+'.urls'))

    return url_list

# automatically load all APIs for registered apps
def get_registered_sample_api_urls():
    api_list = {}
    # path('core/api/', include('core.api.urls')),

    for app in settings.REGISTERED_APPS:
        api = importlib.util.find_spec(app + ".api")
        if api is not None:
            api_list[app] = path(app+'/api', include(app+'.api.urls'))

    return api_list


urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),
    path('admin/', admin.site.urls),
]

# add mission filter as the default page
urlpatterns += i18n_patterns(path('', views.MissionFilterView.as_view(), name="index"), prefix_default_language=True)

# load all other URLs for registered apps using the i18n method for localization
app_url_list = list(get_registered_app_urls().values())
for app in app_url_list:
    urlpatterns += i18n_patterns(app, prefix_default_language=True)

# load the static root where javascript libraries, css and images for webpages is located.
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
