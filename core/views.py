from django.utils.translation import gettext as _
from django.urls import reverse_lazy

from biochem import models
from dart2.views import GenericFlilterMixin, GenericCreateView

from core import forms, filters, models


class MissionMixin:
    model = models.Mission
    page_title = _("Missions")


class MissionFilterView(MissionMixin, GenericFlilterMixin):
    filterset_class = filters.MissionFilter
    new_url = reverse_lazy("core:mission_new")
    fields = ["id", "name", "start_date", "end_date", "biochem_table"]


class MissionCreateView(MissionMixin, GenericCreateView):
    success_url = reverse_lazy("core:mission_filter")
    form_class = forms.MissionSettingsForm
    template_name = "core/mission_settings.html"

    def get_success_url(self):
        success = reverse_lazy("core:event_details", args=(self.object.pk, ))
        return success

    def form_valid(self, form):
        response = super().form_valid(form)

        data = form.cleaned_data

        if 'elog_dir' in data:
            dfd = models.DataFileDirectory(mission=self.object, directory=data['elog_dir'])
            dfd.save()

            dfd_type = models.DataFileDirectoryType(directory=dfd, file_type=models.FileType.log.value)
            dfd_type.save()

        if 'bottle_dir' in data:
            dfd = models.DataFileDirectory(mission=self.object, directory=data['bottle_dir'])
            dfd.save()

            dfd_type = models.DataFileDirectoryType(directory=dfd, file_type=models.FileType.btl.value)
            dfd_type.save()

        return response
