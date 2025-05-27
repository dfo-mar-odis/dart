import os.path

from bs4 import BeautifulSoup
from crispy_forms.bootstrap import StrictButton
from crispy_forms.layout import Column, Row, Field, HTML, Div
from crispy_forms.utils import render_crispy_form

from django import forms
from django.conf import settings
from django.core.cache import caches
from django.db import DatabaseError, close_old_connections
from django.http import HttpResponse, Http404
from django.template.context_processors import csrf
from django.template.loader import render_to_string
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _

from biochem import models as bio_models
from biochem import upload

from core import models as core_models
from core import forms as core_forms
from dart.utils import load_svg

from settingsdb import models as settings_models

from bio_tables import sync_tables

import logging

user_logger = logging.getLogger('dart.user')
logger = logging.getLogger('dart')


# this is a convenience method that allows a developer to grab the "additional buttons area" on the upload form
# to add custom buttons/behaviours to the form
def get_biochem_additional_button_id():
    return 'div_id_biochem_additional_button_area'


class BiochemUploadForm(core_forms.CollapsableCardForm, forms.ModelForm):
    selected_database = forms.ChoiceField(required=False)
    db_password = forms.CharField(widget=forms.PasswordInput(render_value=True), required=False)

    # I had to override the default Bootstrap template for fields, because someone thought putting 'mb-3'
    # as a default for field wrappers was a good idea and it creates a massive gap under the inputs when
    # used in a card title
    field_template = os.path.join(settings.TEMPLATE_DIR, "field.html")

    class Meta:
        model = settings_models.BcDatabaseConnection
        fields = ['account_name', 'uploader', 'name', 'host', 'port', 'engine', 'selected_database', 'db_password',
                  'bc_discrete_data_edits', 'bc_discrete_station_edits', 'bc_plankton_data_edits',
                  'bc_plankton_station_edits']

    def get_host_field_id(self):
        return f'input_id_host_{self.card_name}'

    def get_port_field_id(self):
        return f'input_id_port_{self.card_name}'

    def get_tns_name_field_id(self):
        return f'input_id_name_{self.card_name}'

    def get_bcd_d_field_id(self):
        return f'input_id_bcd_d_{self.card_name}'

    def get_bcs_d_field_id(self):
        return f'input_id_bcs_d_{self.card_name}'

    def get_bcd_p_field_id(self):
        return f'input_id_bcd_p_{self.card_name}'

    def get_bcs_p_field_id(self):
        return f'input_id_bcs_p_{self.card_name}'

    def get_db_select(self):
        url = reverse_lazy('core:form_biochem_database_update_db_selection', args=(self.mission_id,))

        title_id = f"control_id_database_select_{self.card_name}"

        db_select_attributes = {
            'id': title_id,
            'class': 'form-select form-select-sm mt-1',
            'name': 'selected_database',
            'hx-get': url,
            'hx-target': '#div_id_biochem_db_details_input',
            'hx-swap': 'outerHTML'
        }
        db_select = Column(
            Field('selected_database', template=self.field_template, **db_select_attributes,
                  wrapper_class="col-auto"),
            id=f"div_id_db_select_{self.card_name}",
            css_class="col-auto"
        )

        return db_select

    def get_connection_button(self):
        connected = is_connected()
        connect_button_class = "btn btn-success btn-sm" if connected else "btn btn-primary btn-sm"

        connect_button_id = f'btn_id_connect_{self.card_name}'
        connect_button_icon = load_svg('plug')
        url = reverse_lazy('core:form_biochem_database_validate_connection', args=(self.mission_id,))

        connect_button_attrs = {
            'id': connect_button_id,
            'name': 'disconnect' if connected else 'connect',
            'hx-trigger': 'click, biochem_db_update from:body',
            'hx-get': url,
            'hx-swap': 'none',
            'title': _("Connect to database")
        }

        return StrictButton(connect_button_icon, css_class=connect_button_class, **connect_button_attrs)

    def get_sync_biochem_button(self):
        connected = is_connected()

        sync_button_id = f'btn_id_sync_{self.card_name}'
        sync_button_icon = load_svg('arrow-clockwise')
        url = reverse_lazy('core:form_biochem_database_sync', args=(self.mission_id,))

        sync_button_attrs = {
            'id': sync_button_id,
            'name': 'sync',
            'hx-get': url,
            'hx-swap': 'none',
            'title': _("Sync Biochem Lookup Tables")
        }

        if not connected:
            connect_button_class = "btn btn-secondary btn-sm"
            sync_button_attrs['disabled'] = 'disabled'
        else:
            connect_button_class = "btn btn-primary btn-sm"
            sync_button_attrs['hx-confirm'] = _("About to synchronize local Biochem tables with the selected database."
                                                "\nYou may have to reload data after updating Biochem tables."
                                                "\nAre you sure?")

        return StrictButton(sync_button_icon, css_class=connect_button_class, **sync_button_attrs)

    def get_db_password(self):

        password_field_label = f'control_id_password_{self.card_name}'
        html_css_class = "col-form-label me-2"
        password_field = Column(
            Row(
                Column(
                    HTML(f'<label class="{html_css_class}" for="{password_field_label}">{_("Password")}</label>'),
                    css_class="col-auto"
                ),
                Column(
                    Field('db_password', id=password_field_label, template=self.field_template,
                          wrapper_class="input-group-sm mt-1"),
                    Div(
                        self.get_connection_button(),
                        css_class="input-group-sm mt-1"
                    ),
                    Div(
                        self.get_sync_biochem_button(),
                        css_class="input-group-sm mt-1 ms-1"
                    ),
                    css_class="input-group input-group-sm"
                ),
                css_class='',
                id=f"div_id_db_password_{self.card_name}",
            )
        )

        return password_field

    def get_tns_name_field(self):
        tns_details_url = reverse_lazy("core:form_biochem_database_get_database", args=(self.mission_id,))
        tns_field = Field('name', id=self.get_tns_name_field_id(), **{'hx-get': tns_details_url, 'hx-swap': 'none',
                                                                      'hx-trigger': 'keyup changed delay:500ms'})
        return tns_field

    def get_alert_area(self):
        msg_row = Row(id=f"div_id_biochem_alert_{self.card_name}")
        return msg_row

    def get_add_database_button(self):
        add_db_url = reverse_lazy('core:form_biochem_database_add_database', args=(self.mission_id,))
        add_attrs = {
            'id': 'btn_id_db_details_add',
            'title': _('Add'),
            'name': 'add_db',
            'hx_post': add_db_url,
            'hx_target': f'#{self.get_card_id()}',
            'hx_swap': 'outerHTML'
        }

        icon = load_svg('plus-square')
        add_button = StrictButton(icon, css_class="btn btn-primary btn-sm", **add_attrs)
        return add_button

    def get_update_database_button(self):
        add_db_url = reverse_lazy('core:form_biochem_database_add_database', args=(self.mission_id,))

        update_attrs = {
            'id': 'btn_id_db_details_update',
            'title': _('Update'),
            'name': 'update_db',
            'value': self.instance.pk,
            'hx_post': add_db_url,
            'hx-target': f'#{self.get_card_id()}',
            'hx_swap': 'outerHTML'
        }
        icon = load_svg('arrow-clockwise')
        update_button = StrictButton(icon, css_class="btn btn-primary btn-sm", **update_attrs)
        return update_button

    def get_remove_database_button(self):
        delete_db_url = reverse_lazy('core:form_biochem_database_remove_database', args=(self.mission_id,))
        delete_attrs = {
            'id': 'btn_id_db_details_delete',
            'title': _('Delete'),
            'name': 'delete_db',
            'value': self.instance.pk,
            'hx_post': delete_db_url,
            'hx-target': f'#{self.get_card_id()}',
            'hx_swap': 'outerHTML',
            'hx-confirm': _("Are you sure?")
        }
        icon = load_svg('dash-square')
        delete_button = StrictButton(icon, css_class="btn btn-danger btn-sm", **delete_attrs)
        return delete_button

    def get_card_header(self):
        header = super().get_card_header()

        header.fields[0].fields.append(self.get_db_select())
        header.fields[0].fields.append(self.get_db_password())

        header.fields[0].fields.append(Column(id=get_biochem_additional_button_id(), css_class="col-auto"))

        header.fields.append(self.get_alert_area())
        return header

    def get_card_body(self):
        body = super().get_card_body()

        button_column = Column(css_class='align-self-center mb-1')

        host_field = Field('host', id=self.get_host_field_id())
        port_field = Field('port', id=self.get_port_field_id())

        bcd_d_field = Field('bc_discrete_data_edits', id=self.get_bcd_d_field_id())
        bcs_d_field = Field('bc_discrete_station_edits', id=self.get_bcs_d_field_id())

        bcd_p_field = Field('bc_plankton_data_edits', id=self.get_bcd_p_field_id())
        bcs_p_field = Field('bc_plankton_station_edits', id=self.get_bcs_p_field_id())

        update_db_selection_url = reverse_lazy('core:form_biochem_database_update_db_selection',
                                               args=(self.mission_id,))
        hx_attrs = {
            'hx-trigger': 'database_selection_changed from:body',
            'hx-get': update_db_selection_url,
            'hx-target': "#div_id_biochem_db_details_input",
            'hx-swap': 'outerHTML'
        }

        input_row = Row(
            Column(Field('account_name')),
            Column(Field('uploader')),
            Column(self.get_tns_name_field()),
            Column(host_field),
            Column(port_field),
            Column(Field('engine')),
            button_column,
            id="div_id_biochem_db_details_input",
            **hx_attrs
        )

        input_table_row = Row(
            Column(bcd_d_field),
            Column(bcs_d_field),
            Column(bcd_p_field),
            Column(bcs_p_field),
        )

        if self.instance and self.instance.pk:
            button_column.append(self.get_update_database_button())
            button_column.append(self.get_remove_database_button())
        else:
            button_column.append(self.get_add_database_button())

        body.append(input_row)
        body.append(input_table_row)

        return body

    # at a minimum a mission_id and what happens when the upload button are pressed must be supplied in
    def __init__(self, mission_id, *args, **kwargs):
        self.mission_id = mission_id

        super().__init__(*args, **kwargs, card_name="biochem_db_details", card_title=_("Biochem Database"))

        self.fields['selected_database'].label = False
        self.fields['db_password'].label = False

        databases = settings_models.BcDatabaseConnection.objects.all()
        self.fields['selected_database'].choices = [(db.id, db) for db in databases]
        self.fields['selected_database'].choices.insert(0, (None, '--- New ---'))

        if 'selected_database' in self.initial:
            database_id = int(self.initial['selected_database'])
            sentinel = object()
            password = caches['biochem_keys'].get('pwd', sentinel, version=database_id)
            if password is not sentinel:
                self.fields['db_password'].initial = password


def get_progress_alert(url):
    soup = BeautifulSoup('', 'html.parser')

    bio_message_component_id = 'div_id_upload_biochem'
    msg_attrs = {
        'component_id': bio_message_component_id,
        'alert_type': 'info',
        'message': _("Saving to file"),
        'hx-post': url,
        'hx-swap': 'none',
        'hx-trigger': 'load',
        'hx-target': "#div_id_biochem_alert_biochem_db_details",
        'hx-ext': "ws",
        'ws-connect': f"/ws/biochem/notifications/{bio_message_component_id}/"
    }

    bio_alert_soup = core_forms.save_load_component(**msg_attrs)

    # add a message area for websockets
    msg_div = bio_alert_soup.find(id="div_id_upload_biochem_message")
    msg_div.string = ""

    msg_div_status = soup.new_tag('div')
    msg_div_status['id'] = 'status'
    msg_div_status.string = _("Loading")
    msg_div.append(msg_div_status)

    return bio_alert_soup


def confirm_uploader(request):
    if request.method == "GET":
        alert_soup = get_progress_alert(request.path)
        return alert_soup

    soup = BeautifulSoup('', 'html.parser')

    has_uploader = False
    if is_connected() and (database := get_connected_database()):
        has_uploader = database.uploader if database.uploader else database.account_name

    # has_uploader = 'uploader' in request.POST and request.POST['uploader']
    if 'uploader2' not in request.POST and not has_uploader:
        message_component_id = 'div_id_upload_biochem'
        attrs = {
            'component_id': message_component_id,
            'alert_type': 'warning',
            'message': _("Require Uploader")
        }
        alert_soup = core_forms.blank_alert(**attrs)

        input_div = soup.new_tag('div')
        input_div['class'] = 'form-control input-group'

        uploader_input = soup.new_tag('input')
        uploader_input.attrs['id'] = 'input_id_uploader'
        uploader_input.attrs['type'] = "text"
        uploader_input.attrs['name'] = "uploader2"
        uploader_input.attrs['class'] = 'textinput form-control'
        uploader_input.attrs['maxlength'] = '20'
        uploader_input.attrs['placeholder'] = _("Uploader")

        icon = BeautifulSoup(load_svg('check-square'), 'html.parser').svg

        submit = soup.new_tag('button')
        submit.attrs['class'] = 'btn btn-primary'
        submit.attrs['hx-post'] = request.path
        submit.attrs['id'] = 'input_id_uploader_btn_submit'
        submit.attrs['name'] = 'submit'
        submit.append(icon)

        icon = BeautifulSoup(load_svg('x-square'), 'html.parser').svg
        cancel = soup.new_tag('button')
        cancel.attrs['class'] = 'btn btn-danger'
        cancel.attrs['hx-post'] = request.path
        cancel.attrs['id'] = 'input_id_uploader_btn_cancel'
        cancel.attrs['name'] = 'cancel'
        cancel.append(icon)

        input_div.append(uploader_input)
        input_div.append(submit)
        input_div.append(cancel)

        msg = alert_soup.find(id='div_id_upload_biochem_message')
        msg.string = msg.string + " "
        msg.append(input_div)
        return alert_soup
    elif request.htmx.trigger == 'input_id_uploader_btn_submit':
        alert_soup = get_progress_alert(request.path)
        # div_id_upload_biochem_message is the ID given to the component in the get_progress_alert() function
        message = alert_soup.find(id="div_id_upload_biochem")
        hidden = soup.new_tag("input")
        hidden.attrs['type'] = 'hidden'
        hidden.attrs['name'] = 'uploader2'
        hidden.attrs['value'] = request.POST['uploader2']
        message.append(hidden)
        return alert_soup
    elif request.htmx.trigger == 'input_id_uploader_btn_cancel':
        return soup


def confirm_descriptor(request, mission):
    if request.method == "GET":
        alert_soup = get_progress_alert(request.path)
        return alert_soup

    soup = BeautifulSoup('', 'html.parser')
    has_descriptor = hasattr(mission, 'mission_descriptor') and mission.mission_descriptor
    if 'descriptor2' not in request.POST and not has_descriptor:
        message_component_id = 'div_id_upload_biochem'
        attrs = {
            'component_id': message_component_id,
            'alert_type': 'warning',
            'message': _("Require Mission Descriptor")
        }
        alert_soup = core_forms.blank_alert(**attrs)

        input_div = soup.new_tag('div')
        input_div['class'] = 'form-control input-group'

        uploader_input = soup.new_tag('input')
        uploader_input.attrs['id'] = 'input_id_descriptor'
        uploader_input.attrs['type'] = "text"
        uploader_input.attrs['name'] = "descriptor2"
        uploader_input.attrs['class'] = 'textinput form-control'
        uploader_input.attrs['maxlength'] = '20'
        uploader_input.attrs['placeholder'] = _("Mission Descriptor")

        icon = BeautifulSoup(load_svg('check-square'), 'html.parser').svg

        submit = soup.new_tag('button')
        submit.attrs['class'] = 'btn btn-primary'
        submit.attrs['hx-post'] = request.path
        submit.attrs['id'] = 'input_id_descriptor_btn_submit'
        submit.attrs['name'] = 'submit'
        submit.append(icon)

        icon = BeautifulSoup(load_svg('x-square'), 'html.parser').svg
        cancel = soup.new_tag('button')
        cancel.attrs['class'] = 'btn btn-danger'
        cancel.attrs['hx-post'] = request.path
        cancel.attrs['id'] = 'input_id_descriptor_btn_cancel'
        cancel.attrs['name'] = 'cancel'
        cancel.append(icon)

        input_div.append(uploader_input)
        input_div.append(submit)
        input_div.append(cancel)

        msg = alert_soup.find(id='div_id_upload_biochem_message')
        msg.string = msg.string + " "
        msg.append(input_div)
        return alert_soup
    elif request.htmx.trigger == 'input_id_descriptor_btn_submit':
        alert_soup = get_progress_alert(request.path)
        mission.mission_descriptor = request.POST['descriptor2'].strip()

        mission.save()
        return alert_soup
    elif request.htmx.trigger == 'input_id_descriptor_btn_cancel':
        return soup


def get_connected_database() -> settings_models.BcDatabaseConnection:
    database_id = caches['biochem_keys'].get('database_id', None)
    if not database_id:
        raise DatabaseError("Not connected to a database")

    return settings_models.BcDatabaseConnection.objects.get(pk=database_id)


def get_uploader():
    connected_database = get_connected_database()
    if connected_database.uploader:
        return connected_database.uploader.upper()

    return connected_database.account_name.upper()


def get_bcd_d_table():
    return get_connected_database().bc_discrete_data_edits


def get_bcs_d_table():
    return get_connected_database().bc_discrete_station_edits


def get_bcd_p_table():
    return get_connected_database().bc_plankton_data_edits


def get_bcs_p_table():
    return get_connected_database().bc_plankton_station_edits


def get_database_connection_form(request, mission_id):
    database_connections = settings_models.BcDatabaseConnection.objects.all()
    if database_connections.exists():
        selected_db = database_connections.first()
        db_user = os.getenv("BIOCHEM_DB_USER", None)
        db_name = os.getenv("BIOCHEM_DB_NAME", None)

        if (db_name and db_user) and database_connections.filter(name__iexact=db_name,
                                                                 account_name__iexact=db_user).exists():
            selected_db = database_connections.filter(name__iexact=db_name,
                                                      account_name__iexact=db_user).first()

        db_id = caches['biochem_keys'].get('database_id', selected_db.pk)

        initial = {'selected_database': db_id}
        if db_id and (password := os.getenv("BIOCHEM_DB_PASS")):
            initial['db_password'] = password
            connect(db_id, password)

        database_form_crispy = BiochemUploadForm(mission_id, instance=selected_db, initial=initial)
    else:
        database_form_crispy = BiochemUploadForm(mission_id)

    context = {}
    context.update(csrf(request))
    database_form_html = render_crispy_form(database_form_crispy, context=context)
    database_form_soup = BeautifulSoup(database_form_html, 'html.parser')

    disable_key = "'Enter'"
    form_soup = BeautifulSoup(f'<form id="form_id_db_connect" onkeydown="return event.key!={disable_key};"></form>',
                              'html.parser')
    form = form_soup.find('form')
    form.append(database_form_soup)

    soup = BeautifulSoup('', 'html.parser')
    soup.append(biochem_card_wrapper := soup.new_tag('div', id="div_id_biochem_card_wrapper"))
    biochem_card_wrapper.attrs['class'] = "mb-2 mt-2"

    biochem_card_wrapper.append(form_soup)

    responce = HttpResponse(soup)
    responce['Hx-Trigger'] = "biochem_db_connect"
    return responce


def get_tns_details(request, mission_id):
    if request.method == 'GET':
        tns_name = request.GET.get('name', None)
    else:
        tns_name = request.POST.get('name', None)

    tns = settings.TNS_NAMES.get(tns_name.upper(), None)
    if tns:
        form = BiochemUploadForm(mission_id, initial={'name': tns_name, 'host': tns['HOST'],
                                                                'port': tns['PORT']})
    else:
        form = BiochemUploadForm(mission_id)

    html = render_crispy_form(form)
    form_soup = BeautifulSoup(html, 'html.parser')
    soup = BeautifulSoup('', 'html.parser')

    host_field = form_soup.find(id=form.get_host_field_id())
    host_field.attrs['hx-swap-oob'] = 'true'
    soup.append(host_field)

    port_field = form_soup.find(id=form.get_port_field_id())
    port_field.attrs['hx-swap-oob'] = 'true'
    soup.append(port_field)

    return HttpResponse(soup)


def add_database(request, mission_id):
    if request.POST:
        if request.POST.get('selected_database'):
            selected_database = int(request.POST.get('selected_database'))
            instance = settings_models.BcDatabaseConnection.objects.get(pk=selected_database)
            form = BiochemUploadForm(mission_id, instance=instance, data=request.POST)
        else:
            form = BiochemUploadForm(mission_id, data=request.POST)

        if form.is_valid():
            db_connnection = form.save()

            form = BiochemUploadForm(mission_id, instance=db_connnection,
                                     initial={'selected_database': db_connnection.pk}, collapsed=False)
            response = HttpResponse(render_crispy_form(form))
            response['Hx-Trigger'] = "database_selection_changed, biochem_db_update"
            return response

        response = HttpResponse(render_crispy_form(form))
        response['Hx-Trigger'] = "biochem_db_update"
        return response

    # a get request just returns a blank form
    return HttpResponse(render_crispy_form(BiochemUploadForm(mission_id, collapsed=False)))


def remove_database(request, mission_id):
    if request.POST:
        selected_database = int(request.POST.get('selected_database', -1) or -1)
        if selected_database > 0:
            settings_models.BcDatabaseConnection.objects.get(pk=selected_database).delete()

    response = HttpResponse(render_crispy_form(BiochemUploadForm(mission_id, collapsed=False)))
    response['Hx-Trigger'] = "biochem_db_update"
    return response


def select_database(request, mission_id):
    soup = BeautifulSoup('', 'html.parser')
    if database_id := request.GET.get('selected_database', ''):
        caches['biochem_keys'].set('database_id', database_id, 3600)
        password = caches['biochem_keys'].get('pwd', None, version=database_id)

        initial = {'selected_database': database_id}
        if password:
            initial['password'] = password

        bc_database = settings_models.BcDatabaseConnection.objects.get(pk=database_id)
        form = BiochemUploadForm(mission_id, instance=bc_database,
                                 initial=initial)
    else:
        form = BiochemUploadForm(mission_id)

    html = render_crispy_form(form)
    form_soup = BeautifulSoup(html, 'html.parser')
    details = form_soup.find(id='div_id_biochem_db_details_input')
    password = form_soup.find(id='control_id_password_biochem_db_details')
    password.attrs['hx-swap-oob'] = 'true'

    connection_button = form_soup.find(id='btn_id_connect_biochem_db_details')
    connection_button.attrs['hx-swap-oob'] = 'true'

    # calls to this method should already target #div_id_biochem_db_details_input
    soup.append(details)
    soup.append(password)
    soup.append(connection_button)
    response = HttpResponse(soup)
    response['Hx-Trigger'] = "biochem_db_connect"
    return response


def connect(database_id, password) -> None | str:
    message = None
    if not database_id:
        caches['biochem_keys'].delete('database_id')
        caches['biochem_keys'].delete('pwd')
        return None

    if not password:
        caches['biochem_keys'].delete('pwd')
        return None

    try:
        bc_database = settings_models.BcDatabaseConnection.objects.get(pk=database_id)
        settings.DATABASES['biochem'] = bc_database.connect(password=password)
    except settings_models.BcDatabaseConnection.DoesNotExist:
        settings.DATABASES['biochem'] = None

    connection_success = False

    # we don't care about the table name in this case, we're just checking the connection
    bcs_d = upload.get_model('connection_test', bio_models.BcsD)
    try:
        # either we'll get a 942 error indicating the connection worked by the table doesn't exist
        # or the connection worked and the table does exist. Any other reason the connection failed.
        bcs_d.objects.using('biochem').exists()
        connection_success = True
    except DatabaseError as e:

        if e.args[0].code == 942:
            # A 942 Oracle error means the connection worked, but the table/objects don't exist.
            connection_success = True
        elif e.args[0].code == 12545:
            # A 12545 Oracle error means there's an issue with the database connection.
            # This could be because the user isn't logged in on VPN so the Oracle DB can't be connected to.
            message = _("No connection to database, this may be due to VPN (see ./logs/error.log)")
        elif e.args[0].code == 1017:
            message = _("Invalid username/password; login denied")
        elif e.args[0].code == 1005:
            message = _("null password given; login denied")
        else:
            logger.exception(e)
            message = _("An unexpected database error occured. (see ./logs/error.log)")

    if caches['biochem_keys'].get('database_id', -1) != -1:
        caches['biochem_keys'].delete('database_id')

    if caches['biochem_keys'].get('pwd', -1) != -1:
        caches['biochem_keys'].delete('pwd')

    if connection_success:
        caches['biochem_keys'].set('database_id', database_id, 3600)
        caches['biochem_keys'].set(f'pwd', password, 3600, version=database_id)

    return message


def validate_connection(request, mission_id):

    soup = BeautifulSoup('', 'html.parser')
    icon = BeautifulSoup(load_svg('plug'), 'html.parser').svg

    soup.append(connection_button := soup.new_tag('button'))
    connection_button.attrs = {
        'id': "btn_id_connect_biochem_db_details",
        'name': "disconnect" if is_connected() else "connect",
        'trigger': "clicked, biochem_db_update from:body",
        'hx-swap-oob': 'true',
    }

    connection_button.append(icon)

    if request.method == "GET":
        connection_button.attrs['hx-post'] = request.path
        connection_button.attrs['hx-trigger'] = 'load'
        connection_button.attrs['disabled'] = 'true'
        connection_button.attrs['class'] = "btn btn-secondary btn-sm"

        response = HttpResponse(soup)
        response['Hx-Trigger'] = "biochem_db_connect"
        return response

    connection_button.attrs['hx-get'] = request.path

    msg_div = soup.new_tag('div')
    msg_div.attrs = {
        'id': "div_id_biochem_alert_biochem_db_details",
        'hx-swap-oob': 'true'
    }
    soup.append(msg_div)

    if 'connect' in request.POST:
        database_id = request.POST['selected_database']
        password = request.POST['db_password']
        message = connect(database_id, password)

        connection_button.attrs['class'] = 'btn btn-primary btn-sm'
        if is_connected():
            connection_button.attrs['class'] = 'btn btn-success btn-sm'

        if message:
            connection_button.attrs['class'] = 'btn btn-danger btn-sm'
            alert_soup = core_forms.blank_alert(component_id="div_id_upload_biochem", alert_type="danger",
                                                message=message)
            msg_div.append(alert_soup)
    elif 'disconnect' in request.POST:
        database_id = caches['biochem_keys'].get('database_id', None)
        if database_id:
            caches['biochem_keys'].delete('pwd', version=database_id)

        close_old_connections()
        connection_button.attrs['class'] = 'btn btn-primary btn-sm'
    else:
        if 'selected_database' in request.POST and request.POST['selected_database']:
            bc_database = settings_models.BcDatabaseConnection.objects.get(pk=request.POST['selected_database'])
            db_form = BiochemUploadForm(mission_id, data=request.POST, instance=bc_database)
        else:
            db_form = BiochemUploadForm(mission_id, data=request.POST)

        if db_form.is_valid():
            # if the form is valid we'll render it then send back the elements of the form that have to change
            # basically just the selected database dropdown and clear the password field, so just the title bar
            db_details = db_form.save()

            # set the selected database to the updated/saved value
            new_db_form = BiochemUploadForm(mission_id, initial={'selected_database': db_details.pk})
            selected_db_block = render_crispy_form(new_db_form)

            selected_db_soup = BeautifulSoup(selected_db_block, 'html.parser')
            selected_db_soup.find(id=new_db_form.get_card_header_id()).attrs['hx-swap-oob'] = 'true'
            soup.append(selected_db_soup)
        else:
            form_errors = render_crispy_form(db_form)
            form_soup = BeautifulSoup(form_errors, 'html.parser')
            form_soup.find(id="div_id_biochem_db_details_input").attrs['hx-swap-oob'] = 'true'

            soup.append(form_soup)
        # soup.append(update_connection_button(database, mission_id))

    response = HttpResponse(soup)
    response['Hx-Trigger'] = "biochem_db_connect"
    return response


def is_connected():
    if (selected_database := caches['biochem_keys'].get('database_id', -1)) == -1:
        return False
    elif (password := caches['biochem_keys'].get('pwd', -1, version=selected_database)) == -1:
        return False
    elif 'biochem' not in settings.DATABASES:
        return False

    try:
        database = settings_models.BcDatabaseConnection.objects.get(pk=selected_database).name.upper()
        return settings.DATABASES['biochem']['NAME'].upper() == database
    except settings_models.BcDatabaseConnection.DoesNotExist:
        return False


def sync_biochem(request, mission_id, *kwargs):
    soup = BeautifulSoup(f'', 'html.parser')

    if request.method == "GET":

        attrs = {
            'alert_area_id': f'div_id_biochem_alert_biochem_db_details',
            'message': _("Loading"),
            'logger': sync_tables.logger_notifications.name,
            'alert_type': 'info',
            'hx-post': request.path,
            'hx-trigger': "load",
        }
        alert = core_forms.websocket_post_request_alert(**attrs)
        soup.append(alert)

        return HttpResponse(soup)

    try:
        sync_tables.sync_all(database='mission_db')
        message = _("Success")
        alert_type = 'success'
    except Exception as e:
        message = _("Could not synchronize local biochem tables with selected database. See error log for details.")
        alert_type = 'danger'
        logger.exception(e)

    alert = core_forms.blank_alert("div_id_biochem_alert_biochem_db_details", message, alert_type=alert_type)
    alert.find('div', recursive=False).attrs['hx-swap-oob'] = "true"
    soup.append(alert)

    return HttpResponse(soup)


def get_biochem_errors(request, **kwargs):
    mission_id = kwargs['mission_id']
    if request.method == 'GET':
        mission = core_models.Mission.objects.get(pk=mission_id)
        context = {
            'mission': mission,
            'biochem_errors': mission.errors.filter(type=core_models.ErrorType.biochem)
        }
        html = render_to_string(template_name='core/partials/card_biochem_validation.html', context=context)

        return HttpResponse(html)

    logger.error("user has entered an unmanageable state")
    logger.error(kwargs)
    logger.error(request.method)
    logger.error(request.GET)
    logger.error(request.POST)

    return Http404("You shouldn't be here")


url_prefix = "<str:mission_id>"
database_urls = [
    path(f'{url_prefix}/sample/errors/biochem/', get_biochem_errors, name="form_biochem_errors"),
    path(f'{url_prefix}/database/details/', get_tns_details, name='form_biochem_database_get_database'),
    path(f'{url_prefix}/database/add/', add_database, name='form_biochem_database_add_database'),
    path(f'{url_prefix}/database/remove/', remove_database, name='form_biochem_database_remove_database'),
    path(f'{url_prefix}/database/select/', select_database, name='form_biochem_database_update_db_selection'),
    path(f'{url_prefix}/database/connect/', validate_connection, name='form_biochem_database_validate_connection'),
    path(f'{url_prefix}/database/sync/', sync_biochem, name='form_biochem_database_sync'),

    path(f'{url_prefix}/database/card/', get_database_connection_form, name='form_biochem_get_database_connection_form'),
]
