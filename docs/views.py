from django.views.generic import TemplateView

from config.views import GenericViewMixin

from django.utils.translation import gettext as _


class Home(GenericViewMixin, TemplateView):
    page_title = _("Welcome to the Documentation")
    template_name = 'docs/index.html'


class MissionFilter(GenericViewMixin, TemplateView):
    page_title = _("Mission Filter Page")
    template_name = 'docs/mission_filter.html'


class NewMissionForm(GenericViewMixin, TemplateView):
    page_title = _("New Mission Form")
    template_name = 'docs/new_mission_form.html'


class MissionEvents(GenericViewMixin, TemplateView):
    page_title = _("Mission Events Page")
    template_name = 'docs/mission_events.html'


class MissionSamples(GenericViewMixin, TemplateView):
    page_title = _("Mission Samples Page")
    template_name = 'docs/mission_samples.html'


class FileConfigurations(GenericViewMixin, TemplateView):
    page_title = _("Creating and Modifying File Configurations")
    template_name = 'docs/file_configurations.html'


class SampleTypes(GenericViewMixin, TemplateView):
    page_title = _("Standard Sample Types Page")
    template_name = 'docs/standard_sample_types.html'
