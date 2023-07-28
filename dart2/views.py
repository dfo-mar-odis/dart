from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView
from django_filters.views import FilterView

from . import urls
from . import settings

from biochem import models as upload_models


class GenericViewMixin:
    page_title = None
    home_url = reverse_lazy('core:mission_filter')

    def get_home_url(self):
        return self.home_url

    def get_page_title(self):
        return self.page_title

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["home_url"] = self.get_home_url()
        context["page_title"] = self.get_page_title()
        try:
            context["bio_chem_details_provided"] = settings.env('BIOCHEM_NAME', default=None) is not None
            dataset = upload_models.Bcdatatypes.objects.first()  # if this fails there is no DB connection.
        except:
            context["bio_chem_details_provided"] = None

        context["reports"] = {}
        sample_urls = urls.get_registered_sample_api_urls()
        sample_apis = [sample_urls[api] for api in sample_urls]
        resolvers = [url_resolver.url_patterns[0] for url_resolver in sample_apis]

        for resolver in resolvers:
            if 'csv_report-list' in [url.name for url in resolver.url_patterns]:
                context["reports"][resolver.namespace] = f'{resolver.app_name}:csv_report-list'

        return context


class GenericFlilterMixin(GenericViewMixin, FilterView):
    new_url = None
    fields = None

    def get_new_url(self):
        return self.new_url

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["new_url"] = self.get_new_url()
        context["obj"] = self.get_queryset().values(*self.fields) if self.fields else self.get_queryset().values()

        return context


class GenericCreateView(GenericViewMixin, CreateView):
    success_url = None

    def get_success_url(self):
        return self.success_url


class GenericUpdateView(GenericViewMixin, UpdateView):
    success_url = None

    def get_success_url(self):
        return self.success_url
