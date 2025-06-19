from django.urls import reverse_lazy
from django.views.generic import TemplateView

from config import utils


class GenericTemplateView(TemplateView):
    page_title = None
    home_url = None

    def get_page_title(self):
        return self.page_title

    def get_home_url(self):
        return reverse_lazy(self.home_url if self.home_url else "dart:mission_filter")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if 'database' in self.kwargs:
            utils.connect_database(kwargs['database'])

        context['page_title'] = self.get_page_title()
        context['home_url'] = self.get_home_url()

        return context