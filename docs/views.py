from django.views.generic import TemplateView

from dart2.views import GenericViewMixin

from django.utils.translation import gettext as _


class Home(GenericViewMixin, TemplateView):
    page_title = _("Welcome to the Documentation")
    template_name = 'docs/index.html'


class MissionFilter(GenericViewMixin, TemplateView):
    page_title = _("Mission Filter")
    template_name = 'docs/mission_filter.html'


class NewMissionForm(GenericViewMixin, TemplateView):
    page_title = _("New Mission Form")
    template_name = 'docs/new_mission_form.html'
