import logging

from bs4 import BeautifulSoup
from crispy_forms.helper import FormHelper
from crispy_forms.utils import render_crispy_form

from crispy_forms.layout import Layout, Field, Row, Div, HTML, Hidden

from django import forms
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import reverse_lazy, path
from django.utils.html import escape
from django.utils.translation import gettext as _
from django.db.models import Q
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from core import forms as core_forms, form_biochem_database
from biochem import models as biochem_models
from biochem import download

logger = logging.getLogger('dart')
user_logger = logger.getChild('user')

_page_limit = 50

card_name = "biochem_mission_summary"


class BiochemMissionFilterForm(forms.Form):
    loading = forms.IntegerField()
    mission_name = forms.CharField(label=_("Mission Name"))
    mission_type = forms.ChoiceField(
        label=_("Mission Type"),
        choices=[
            (None, "----------"),
            ("PLANKTON", _("Plankton")),
            ("DISCRETE", _("Discrete")),
            ("NEITHER", _("Neither")),
            ("BOTH", _("Both")),
        ],
        required=False,
    )

    class Meta:
        fields = ['loading', 'mission_name', "mission_type"]

    def get_input_mission_name(self):
        id_builder = BiochemMissionSummaryForm.get_id_builder_class()(card_name)
        attrs = {
            'hx-get': reverse_lazy("core:form_biochem_list_missions"),
            'hx-trigger': "keyup changed delay:500ms",
            'hx-target': "#" + id_builder.get_mission_selection_id(),
            'hx-indicator': "#" + get_mission_filter_spinner_id(),
            'hx-params': "*"
        }
        mission_name = Field('mission_name', css_class='form-control-sm', **attrs)
        return mission_name

    def get_choice_mission_type(self):
        id_builder = BiochemMissionSummaryForm.get_id_builder_class()(card_name)
        attrs = {
            'hx-post': reverse_lazy("core:form_biochem_list_missions"),
            'hx-target': "#" + id_builder.get_mission_selection_id(),
            'hx-indicator': "#" + get_mission_filter_spinner_id(),
            'hx-params': "*"
        }

        mission_type = Field('mission_type', css_class='form-select-sm', **attrs)
        return mission_type

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        hidden_attrs = {
            'id': "input_hidden_id_loading",
            'hx-get': reverse_lazy("core:form_biochem_list_missions"),
            'hx-target': "#" + BiochemMissionSummaryForm.get_id_builder_class()(card_name).get_mission_selection_id(),
            'hx-trigger': 'reload_db_table from:body',
            'hx-indicator': "#" + get_mission_filter_spinner_id(),
            'hx-params': "*"
        }

        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            Hidden("loading", "false", **hidden_attrs),
            Row(
                Div(self.get_input_mission_name(), css_class="col"),
                Div(self.get_choice_mission_type(), css_class="col")
            )
        )


class ConnectionAlert(core_forms.AlertArea):

    def __init__(self, *args, css_id=None, css_class=None, **kwargs):
        super().__init__(*args, css_id=css_id, css_class=css_class, **kwargs)
        update_url = reverse_lazy("core:form_biochem_connected_message")
        attrs = {
            'hx-trigger': 'biochem_db_connect from:body',
            'hx-get': update_url,
            'hx-swap': "outerHTML"
        }

        id_builder = BiochemMissionSummaryForm.get_id_builder_class()(card_name)
        node_id = id_builder.get_connection_message_id()
        self.msg_node = Div(css_id=node_id, **attrs)
        self.fields.append(self.msg_node)

def get_mission_filter_spinner_id():
    return f"div_id_{card_name}_mission_loading_spinner"

def get_mission_filter_spinner(on=False, oob_swap=False):
    soup = BeautifulSoup('', 'html.parser')

    attrs = {
        'id': get_mission_filter_spinner_id(),
        "class": "htmx-indicator",
    }
    if oob_swap:
        attrs["hx-swap-oob"] = "true"

    soup.append(span:=soup.new_tag('span', attrs=attrs))

    span.append(load_msg:=soup.new_tag('div', attrs={'class': 'spinner-border text-primary', 'style': 'width: 10px; height: 10px;'}))
    return soup.find(id=get_mission_filter_spinner_id())


# This form is for after a user has connected to a Biochem database. It will query the database for a "BcBatches" table
# and if found will give the user the ability to select and remove batches as well as view errors associated with a batch
class BiochemMissionSummaryForm(core_forms.CardForm):
    class BiochemMissionSummaryIdBuilder(core_forms.CardForm.CardFormIdBuilder):

        def get_connection_message_id(self):
            return self.get_alert_area_id() + "_message"

        def get_mission_filter_id(self):
            return f"div_id_{self.card_name}_mission_filter"

        def get_mission_selection_id(self):
            return f"div_id_{self.card_name}_mission_selection"

        def get_loading_spinner_id(self):
            return

    @staticmethod
    def get_id_builder_class():
        return BiochemMissionSummaryForm.BiochemMissionSummaryIdBuilder

    class Meta:
        pass
        # fields = ['selected_mission']

    alert_area_class = ConnectionAlert

    def get_mission_filter_form(self):
        form_attrs = {
            'hx-get': reverse_lazy("core:form_biochem_list_missions"),
            'hx-target': "#" + self.get_id_builder().get_mission_selection_id(),
            'hx-trigger': 'load, biochem_db_connect from:body',
            'hx-indicator': "#" + get_mission_filter_spinner_id(),
            'hx-params': "*"
        }

        form = BiochemMissionFilterForm()
        html = render_crispy_form(form=form)
        mission_filter = Div(
            HTML(html),
            css_id=self.get_id_builder().get_mission_filter_id(),
            **form_attrs
        )
        return mission_filter

    def get_mission_selection_form(self):
        return Div(css_class='vertical-scrollbar-sm', css_id=self.get_id_builder().get_mission_selection_id())

    def get_card_title(self) -> Div:
        header = super().get_card_title()
        header.fields.append(HTML(get_mission_filter_spinner()))
        return header

    def get_card_body(self):
        body = Div(
            self.get_mission_filter_form(),
            self.get_mission_selection_form(),
            css_class='card-body', id=self.get_card_body_id())
        return body

    def __init__(self, *args, **kwargs):
        super().__init__(*args, card_name=card_name, card_title=_("Mission Selection"), **kwargs)


def set_alert_area(form):
    msg_node = form.get_alert_area().msg_node

    if not form_biochem_database.is_connected():
        safe_html = escape(_("No Connected Database"))
        msg_node.css_class = 'bg-danger-subtle'
        msg_node.fields.append(HTML(safe_html))


def update_summary_alert(request):
    form = BiochemMissionSummaryForm()

    set_alert_area(form)

    html = render_crispy_form(form)
    form_soup = BeautifulSoup(html, 'html.parser')
    msg_id = form.get_id_builder().get_alert_area_id()
    return HttpResponse(form_soup.find(id=msg_id))


def get_mission_selection_card(request):
    form = BiochemMissionSummaryForm()
    set_alert_area(form)

    soup = BeautifulSoup('', 'html.parser')
    soup.append(BeautifulSoup(render_crispy_form(form), 'html.parser'))
    return HttpResponse(soup.prettify())


def list_missions(request):
    soup = BeautifulSoup('', 'html.parser')
    page = request.GET.get('loading', 1)

    context = {
        "missions": None
    }
    missions = None
    page = int(page) if page and page!='false' else 1
    if form_biochem_database.is_connected():
        query_set = biochem_models.Bcmissions.objects.using('biochem').order_by('-start_date')
        if 'mission_name' in request.GET:
            query_set = query_set.filter(name__icontains=request.GET['mission_name'])

        if 'mission_type' in request.GET:
            value = request.GET.get('mission_type').upper()
            if value == "DISCRETE":
                query_set = query_set.filter(events__discrete_headers__isnull=False).distinct()
            elif value == "PLANKTON":
                query_set = query_set.filter(events__planktonheaders__isnull=False).distinct()
            elif value == "BOTH":
                q1 = query_set.filter(events__planktonheaders__isnull=False).distinct()
                q2 = query_set.filter(events__discrete_headers__isnull=False).distinct()
                query_set = query_set.filter(Q(mission_seq__in=q1) & Q(mission_seq__in=q2))
            elif value == "NEITHER":
                q1 = query_set.filter(events__planktonheaders__isnull=False).distinct()
                q2 = query_set.filter(events__discrete_headers__isnull=False).distinct()
                query_set = query_set.exclude(mission_seq__in=q1).exclude(mission_seq__in=q2)

        paginator = Paginator(query_set, 25)  # 50 items per page
        try:
            missions = paginator.page(page)
        except PageNotAnInteger:
            missions = paginator.page(1)
        except EmptyPage:
            missions = paginator.page(paginator.num_pages)

        context["missions"] = missions

    html = render_to_string('core/partials/table_biochem_mission_selection.html', context=context)
    table_soup = BeautifulSoup(html, 'html.parser')
    if missions and missions.has_next():
        trs = table_soup.find('tbody').find_all('tr')
        last_tr = trs[-1]
        last_tr.attrs['hx-get'] = request.path + "?" +  f"loading={page+1}"
        last_tr.attrs['hx-trigger'] = 'intersect once'
        last_tr.attrs['hx-swap'] = 'afterend'
        last_tr.attrs['hx-indicator'] = '#' + get_mission_filter_spinner_id()

        if page > 1:
            return HttpResponse(table_soup.find('tbody').find_all('tr'))

    soup.append(table_soup)
    return HttpResponse(soup)


def download_mission(request, mission_seq):
    soup = BeautifulSoup('<div id="div_id_mission_summary_download"></div>', 'html.parser')
    message_area = soup.find(id="div_id_mission_summary_download")

    if "download" not in request.GET:
        alert_attrs = {
            "alert_area_id": "div_id_mission_summary_download_alert",
            "alert_type": "primary",
            "hx-get": request.path + f"?download=true",
            "hx-indicator": "#" + get_mission_filter_spinner_id(),
            "hx-trigger": "load",
            "hx-target": "#div_id_mission_summary_download",
            "logger": download.user_logger,
            "message": _("Downloading Mission")
        }
        alert = core_forms.websocket_post_request_alert(swap_oob=False, **alert_attrs)
        message_area.append(alert)

    error = None
    try:
        downloader = download.DatabaseDownloader(mission_seq)
        downloader.download()
    except biochem_models.Bcmissions.DoesNotExist:
        error = _("Could not find mission with requested ID") + f": {mission_seq}"
    except Exception as e:
        error = _("Unknown Error downloading Mission") + f": {str(e)}"

    if error:
        alert_attrs = {
            "component_id": "div_id_mission_summary_download_alert",
            "message": error,
            "alert_type": "danger",
        }
        alert = core_forms.blank_alert(**alert_attrs)
        message_area.append(alert)

    return HttpResponse(soup)

urlpatterns = [
    path('biochem/clear_summary/', get_mission_selection_card, name='form_biochem_get_mission_selection_card'),
    path('biochem/update_summary_alert/', update_summary_alert, name='form_biochem_connected_message'),
    path('biochem/list_missions/', list_missions, name='form_biochem_list_missions'),

    path('biochem/download/<int:mission_seq>/', download_mission, name='form_biochem_mission_summary_download'),
]
