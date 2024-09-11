from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView, DetailView, TemplateView
from django.views.generic.base import ContextMixin
from django_filters.views import FilterView
from git import Repo

from settingsdb import utils
from . import settings

from biochem import models as upload_models


class GenericViewMixin(ContextMixin):
    page_title = None
    home_url = reverse_lazy('settingsdb:mission_filter')
    theme = 'light'
    settings_url = None

    def get_home_url(self):
        return self.home_url

    def get_page_title(self):
        return self.page_title

    def get_settings_url(self):
        return self.settings_url

    def get_theme(self):
        return self.theme

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
        context['settings_url'] = self.get_settings_url()
        context['theme'] = self.get_theme()

        if hasattr(self, 'kwargs') and 'database' in getattr(self, 'kwargs'):
            context['database'] = self.kwargs['database']

        repo = Repo(settings.BASE_DIR)
        context['git_version'] = repo.git.rev_parse(repo.head.commit.hexsha, short=8)
        return context


class GenericFlilterMixin(GenericViewMixin, FilterView):
    new_url = None
    fields = None

    def get_queryset(self):
        if 'database' in self.kwargs:
            database = self.kwargs['database']
            utils.connect_database(database)

            return self.model.objects.using(database).all()

        return super().get_queryset()

    def get_new_url(self):
        return self.new_url

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["new_url"] = self.get_new_url()
        context["obj"] = self.get_queryset().values(*self.fields) if self.fields else self.get_queryset().values()

        return context


class GenericCreateView(GenericViewMixin, CreateView):
    success_url = None

    def get_queryset(self):
        if 'database' in self.kwargs:
            database = self.kwargs['database']
            utils.connect_database(database)

            return self.model.objects.using(database).all()

        return super().get_queryset()

    def get_success_url(self):
        return self.success_url


class GenericUpdateView(GenericViewMixin, UpdateView):
    success_url = None

    def get_queryset(self):
        if 'database' in self.kwargs:
            database = self.kwargs['database']
            utils.connect_database(database)

            return self.model.objects.using(database).all()

        return super().get_queryset()

    def get_success_url(self):
        return self.success_url


class GenericDetailView(GenericViewMixin, DetailView):

    def get_queryset(self):
        if 'database' in self.kwargs:
            database = self.kwargs['database']
            utils.connect_database(database)

            return self.model.objects.using(database).all()

        return super().get_queryset()


class GenericTemplateView(GenericViewMixin, TemplateView):
    pass