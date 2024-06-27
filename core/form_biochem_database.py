import os.path
import time

from datetime import datetime

from bs4 import BeautifulSoup
from crispy_forms.bootstrap import StrictButton
from crispy_forms.layout import Column, Row, Field, HTML, Div
from crispy_forms.utils import render_crispy_form

from django import forms
from django.conf import settings
from django.core.cache import caches
from django.db import DatabaseError, close_old_connections
from django.db.models import Q
from django.http import HttpResponse, Http404
from django.template.context_processors import csrf
from django.template.loader import render_to_string
from django.urls import reverse_lazy, path
from django.utils.translation import gettext as _

import biochem.upload

from core import models as core_models
from core import forms as core_forms
from core.form_validation_biochem import BIOCHEM_CODES
from core.forms import get_crispy_element_attributes
from dart.utils import load_svg

from settingsdb import models as settings_models

import logging

user_logger = logging.getLogger('dart.user')
logger = logging.getLogger('dart')


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
        fields = ['account_name', 'uploader', 'name', 'host', 'port', 'engine', 'selected_database', 'db_password']

    def get_host_field_id(self):
        return f'input_id_host_{self.card_name}'

    def get_port_field_id(self):
        return f'input_id_port_{self.card_name}'

    def get_tns_name_field_id(self):
        return f'input_id_name_{self.card_name}'

    def get_db_select(self):
        url = reverse_lazy('core:form_biochem_database_update_db_selection', args=(self.database, self.mission_id))

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

    def get_connection_button(self, connected=False):
        connect_button_class = "btn btn-success btn-sm" if connected else "btn btn-primary btn-sm"

        connect_button_id = f'btn_id_connect_{self.card_name}'
        connect_button_icon = load_svg('plug')
        url = reverse_lazy('core:form_biochem_database_validate_connection', args=(self.database, self.mission_id))

        connect_button_attrs = {
            'id': connect_button_id,
            'name': 'connect',
            'hx-get': url,
            'hx-swap': 'none',
            'title': _("Connect to database")
        }

        connect_button = StrictButton(connect_button_icon, css_class=connect_button_class, **connect_button_attrs)
        return connect_button

    def get_db_password(self):

        connected = False
        if 'selected_database' in self.initial and self.initial['selected_database']:
            sentinel = object()
            password = caches['biochem_keys'].get("pwd", sentinel, version=self.initial['selected_database'])
            if password is not sentinel:
                connected = True

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
                        self.get_connection_button(connected),
                        css_class="input-group-sm mt-1"
                    ),
                    css_class="input-group input-group-sm"
                ),
                css_class='',
                id=f"div_id_db_password_{self.card_name}",
            )
        )

        return password_field

    def get_tns_name_field(self):
        tns_details_url = reverse_lazy("core:form_biochem_database_get_database", args=(self.database, self.mission_id))
        tns_field = Field('name', id=self.get_tns_name_field_id(), **{'hx-get': tns_details_url, 'hx-swap': 'none',
                                                                      'hx-trigger': 'keyup changed delay:500ms'})
        return tns_field

    def get_alert_area(self):
        msg_row = Row(id=f"div_id_biochem_alert_{self.card_name}")
        return msg_row

    def get_add_database_button(self):
        add_db_url = reverse_lazy('core:form_biochem_database_add_database', args=(self.database, self.mission_id))
        add_attrs = {
            'id': 'btn_id_db_details_add',
            'title': _('Add'),
            'name': 'add_db',
            'hx_post': add_db_url,
            'hx-target': f'#{self.get_card_id()}',
            'hx_swap': 'outerHTML'
        }

        icon = load_svg('plus-square')
        add_button = StrictButton(icon, css_class="btn btn-primary btn-sm", **add_attrs)
        return add_button

    def get_update_database_button(self):
        add_db_url = reverse_lazy('core:form_biochem_database_add_database', args=(self.database, self.mission_id))

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
        delete_db_url = reverse_lazy('core:form_biochem_database_remove_database', args=(self.database,
                                                                                         self.mission_id))
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

        update_db_selection_url = reverse_lazy('core:form_biochem_database_update_db_selection', args=(self.database,
                                                                                                       self.mission_id))
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

        if self.instance and self.instance.pk:
            button_column.append(self.get_update_database_button())
            button_column.append(self.get_remove_database_button())
        else:
            button_column.append(self.get_add_database_button())

        body.append(input_row)

        return body

    # at a minimum a mission_id and what happens when the upload button are pressed must be supplied in
    def __init__(self, database, mission_id, *args, **kwargs):
        self.database = database
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
    has_uploader = 'uploader' in request.POST and request.POST['uploader']
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


# this button is placed in the title of the Database card to indicate if the user is connected, or if there's
# an issue connecting to the database. This function is used in multiple methods when actions are preformed to change
# the status of the button.
def update_connection_button(database, mission_id, post: bool = False, error: bool = False):

    # url = reverse_lazy('core:form_biochem_validate_database_connection', args=(database, mission.pk,))
    url = reverse_lazy('core:form_biochem_database_validate_connection', args=(database, mission_id))
    icon = BeautifulSoup(load_svg('plug'), 'html.parser').svg
    soup = BeautifulSoup("", "html.parser")

    button = soup.new_tag('button')
    button.attrs = {
        'id': "btn_id_connect_biochem_db_details",
        'name': "connect",
        'hx-swap-oob': 'true',
    }
    if post:
        button.attrs['hx-post'] = url
        button.attrs['hx-trigger'] = 'load'
        button.attrs['disabled'] = 'true'
        button.attrs['class'] = "btn btn-disable btn-sm"
    else:
        button.attrs['hx-get'] = url
        if error:
            button.attrs['class'] = "btn btn-danger btn-sm"
        else:
            sentinel = object()
            password = sentinel
            database_id = caches['biochem_keys'].get('database_id', sentinel)
            if database_id is not sentinel:
                password = caches['biochem_keys'].get('pwd', sentinel, version=database_id)

            button.attrs['class'] = "btn btn-primary btn-sm"
            if password is not sentinel:
                button.attrs['class'] = "btn btn-success btn-sm"
                button.attrs['name'] = "disconnect"

    button.append(icon)

    return button


def remove_bcd_d_data(mission: core_models.Mission):
    database = mission._state.db
    batch = mission.get_batch_name

    delete_samples = core_models.BioChemUpload.objects.using(database).filter(
        status=core_models.BioChemUploadStatus.delete)

    bcd_d = biochem.upload.get_bcd_d_model(mission.get_biochem_table_name)
    for delete in delete_samples:
        try:
            bcd_d.objects.using('biochem').filter(
                dis_detail_data_type_seq=delete.type.datatype.data_type_seq,
                batch_seq=batch
            ).delete()
            delete.delete()
        except Exception as ex:
            message = _("An issue occured while removeing rows for sensor/sample") + f": {delete.type.name}"
            user_logger.error(message)
            logger.exception(ex)


def upload_bcs_d_data(mission: core_models.Mission, uploader: str):
    database = mission._state.db
    # 1) get bottles from BCS_D table
    bcs_d = biochem.upload.get_bcs_d_model(mission.get_biochem_table_name)
    exists = biochem.upload.check_and_create_model('biochem', bcs_d)

    # 2) if the BCS_D table doesn't exist, create with all the bottles. We're only uploading CTD bottles
    ctd_events = mission.events.filter(instrument__type=core_models.InstrumentType.ctd)
    bottles = core_models.Bottle.objects.using(database).filter(event__in=ctd_events)
    # bottles = models.Bottle.objects.using(database).filter(event__mission=mission)
    if exists:
        # 3) else filter bottles from local db where bottle.last_modified > bcs_d.created_date
        last_uploaded = bcs_d.objects.using('biochem').all().values_list('created_date', flat=True).distinct().last()
        # if last_uploaded:
        #     bottles = bottles.filter(last_modified__gt=last_uploaded)

        if bottles.exists():
            # 4) upload only bottles that are new or were modified since the last biochem upload
            # send_user_notification_queue('biochem', _("Compiling BCS rows"))
            user_logger.info(_("Compiling BCS rows"))
            create, update, fields = biochem.upload.get_bcs_d_rows(uploader=uploader, bottles=bottles,
                                                                   batch_name=mission.get_batch_name,
                                                                   bcs_d_model=bcs_d)

            # send_user_notification_queue('biochem', _("Creating/updating BCS rows"))
            user_logger.info(_("Creating/updating BCS rows"))
            biochem.upload.upload_bcs_d(bcs_d, create, update, fields)


def upload_bcd_d_data(mission: core_models.Mission, uploader: str):
    database = mission._state.db

    # 1) Start by removing records marked for deletion
    remove_bcd_d_data(mission)

    # 2) get the biochem BCD_D model
    bcd_d = biochem.upload.get_bcd_d_model(mission.get_biochem_table_name)

    # 3) if the BCD_D model doesn't exist create it and add all samples specified by sample_id
    exists = biochem.upload.check_and_create_model('biochem', bcd_d)

    if exists:
        user_logger.info(_("Compiling rows for : ") + mission.name)
        batch = mission.get_batch_name

        # 3) else filter the samples down to rows based on:
        # 3a) samples in this mission
        # 3b) samples of the current sample_type
        datatypes = core_models.BioChemUpload.objects.using(database).filter(
            status=core_models.BioChemUploadStatus.upload,
            type__mission=mission).values_list('type', flat=True).distinct()

        discreate_samples = core_models.DiscreteSampleValue.objects.using(database).filter(
            sample__bottle__event__mission=mission
        )
        discreate_samples = discreate_samples.filter(sample__type_id__in=datatypes)

        if discreate_samples.exists():
            # 4) upload only samples that are new or were modified since the last biochem upload
            message = _("Compiling BCD rows for sample type") + " : " + mission.name
            user_logger.info(message)
            create, update, fields = biochem.upload.get_bcd_d_rows(database=database, uploader=uploader,
                                                                   samples=discreate_samples,
                                                                   batch_name=batch,
                                                                   bcd_d_model=bcd_d)

            message = _("Creating/updating BCD rows for sample type") + " : " + mission.name
            user_logger.info(message)
            try:
                biochem.upload.upload_bcd_d(bcd_d, discreate_samples, create, update, fields)
                uploaded = core_models.BioChemUpload.objects.using(database).filter(
                    type__mission=mission,
                    status=core_models.BioChemUploadStatus.upload
                )
                for upload in uploaded:
                    upload.status = core_models.BioChemUploadStatus.uploaded
                    upload.upload_date = datetime.now()
                    upload.save()

            except Exception as ex:
                message = _("An error occured while writing BCD rows: ") + str(ex)
                core_models.Error.objects.using(database).create(
                    mission=mission, message=message, type=core_models.ErrorType.biochem,
                    code=BIOCHEM_CODES.FAILED_WRITING_DATA.value
                )
                user_logger.error(message)
                logger.exception(ex)


def upload_bcs_p_data(mission: core_models.Mission, uploader: str):
    database = mission._state.db

    # 1) get bottles from BCS_P table
    bcs_p = biochem.upload.get_bcs_p_model(mission.get_biochem_table_name)
    exists = biochem.upload.check_and_create_model('biochem', bcs_p)

    # 2) if the bcs_p table doesn't exist, create with all the bottles. linked to plankton samples
    samples = core_models.PlanktonSample.objects.using(database).filter(bottle__event__mission=mission)
    bottle_ids = samples.values_list('bottle_id').distinct()
    bottles = core_models.Bottle.objects.using(database).filter(pk__in=bottle_ids)

    # bottles = models.Bottle.objects.using(database).filter(event__mission=mission)
    if exists:
        # 3) else filter bottles from local db where bottle.last_modified > bcs_p.created_date
        last_uploaded = bcs_p.objects.all().values_list('created_date', flat=True).distinct().last()
        if last_uploaded:
            bottles = bottles.filter(last_modified__gt=last_uploaded)

    if bottles.exists():
        # 4) upload only bottles that are new or were modified since the last biochem upload
        # send_user_notification_queue('biochem', _("Compiling BCS rows"))
        user_logger.info(_("Compiling BCS rows"))
        bcs_create, bcs_update, updated_fields = biochem.upload.get_bcs_p_rows(uploader, bottles,
                                                                               mission.get_batch_name, bcs_p)

        # send_user_notification_queue('biochem', _("Creating/updating BCS rows"))
        user_logger.info(_("Creating/updating BCS rows"))
        biochem.upload.upload_bcs_p(bcs_p, bcs_create, bcs_update, updated_fields)


def upload_bcd_p_data(mission: core_models.Mission, uploader: str):
    database = mission._state.db

    # 1) get bottles from BCD_P table
    bcd_p = biochem.upload.get_bcd_p_model(mission.get_biochem_table_name)
    exists = biochem.upload.check_and_create_model('biochem', bcd_p)

    # 2) if the bcs_p table doesn't exist, create with all the bottles. linked to plankton samples
    samples = core_models.PlanktonSample.objects.using(database).filter(bottle__event__mission=mission)

    # bottles = models.Bottle.objects.using(database).filter(event__mission=mission)
    # if exists:
    #     # 3) else filter bottles from local db where bottle.last_modified > bcs_p.created_date
    #     last_uploaded = bcs_p.objects.all().values_list('created_date', flat=True).distinct().last()
    #     if last_uploaded:
    #         bottles = bottles.filter(last_modified__gt=last_uploaded)

    if samples.exists():
        # 4) upload only bottles that are new or were modified since the last biochem upload
        # send_user_notification_queue('biochem', _("Compiling BCS rows"))
        user_logger.info(_("Compiling BCD rows"))
        bcd_create, bcd_update, updated_fields = biochem.upload.get_bcd_p_rows(database, uploader, samples,
                                                                               mission.get_batch_name, bcd_p)

        # send_user_notification_queue('biochem', _("Creating/updating BCS rows"))
        user_logger.info(_("Creating/updating BCD rows"))
        biochem.upload.upload_bcd_p(bcd_p, bcd_create, bcd_update, updated_fields)


def get_biochem_errors(request, database, **kwargs):
    mission_id = kwargs['mission_id']
    if request.method == 'GET':
        mission = core_models.Mission.objects.using(database).get(pk=mission_id)
        context = {
            'database': database,
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


def get_database_connection_form(request, database, mission_id):
    database_connections = settings_models.BcDatabaseConnection.objects.all()
    if database_connections.exists():
        selected_db = database_connections.first()
        if (db_id := caches['biochem_keys'].get('database_id', -1)) == -1:
            db_id = selected_db.pk
        initial = {'selected_database': db_id}
        database_form_crispy = BiochemUploadForm(database, mission_id, instance=selected_db, initial=initial)
    else:
        database_form_crispy = BiochemUploadForm(database, mission_id)

    context = {}
    context.update(csrf(request))
    database_form_html = render_crispy_form(database_form_crispy, context=context)
    database_form_soup = BeautifulSoup(database_form_html, 'html.parser')

    disable_key = "'Enter'"
    form_soup = BeautifulSoup(f'<form id="form_id_db_connect" onkeydown="return event.key!={disable_key};"></form>', 
                              'html.parser')
    form = form_soup.find('form')
    form.append(database_form_soup)

    return form_soup


def get_tns_details(request, database, mission_id):
    if request.method == 'GET':
        tns_name = request.GET.get('name', None)
    else:
        tns_name = request.POST.get('name', None)

    tns = settings.TNS_NAMES.get(tns_name.upper(), None)
    if tns:
        form = BiochemUploadForm(database, mission_id, initial={'name': tns_name, 'host': tns['HOST'],
                                                                'port': tns['PORT']})
    else:
        form = BiochemUploadForm(database, mission_id)

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


def add_database(request, database, mission_id):
    if request.POST:
        if request.POST.get('selected_database'):
            selected_database = int(request.POST.get('selected_database'))
            instance = settings_models.BcDatabaseConnection.objects.get(pk=selected_database)
            form = BiochemUploadForm(database, mission_id, instance=instance, data=request.POST)
        else:
            form = BiochemUploadForm(database, mission_id, data=request.POST)

        if form.is_valid():
            db_connnection = form.save()

            form = BiochemUploadForm(database, mission_id, instance=db_connnection,
                                     initial={'selected_database': db_connnection.pk}, collapsed=False)
            response = HttpResponse(render_crispy_form(form))
            response['Hx-Trigger'] = "database_selection_changed, biochem_db_update"
            return response

        response = HttpResponse(render_crispy_form(form))
        response['Hx-Trigger'] = "biochem_db_update"
        return response

    # a get request just returns a blank form
    return HttpResponse(render_crispy_form(BiochemUploadForm(database, mission_id, collapsed=False)))


def remove_database(request, database, mission_id):
    if request.POST:
        selected_database = int(request.POST.get('selected_database', -1) or -1)
        if selected_database > 0:
            settings_models.BcDatabaseConnection.objects.get(pk=selected_database).delete()

    response = HttpResponse(render_crispy_form(BiochemUploadForm(database, mission_id, collapsed=False)))
    response['Hx-Trigger'] = "biochem_db_update"
    return response


def select_database(request, database, mission_id):
    soup = BeautifulSoup('', 'html.parser')
    if database_id := request.GET.get('selected_database', ''):
        bc_database = settings_models.BcDatabaseConnection.objects.get(pk=database_id)
        form = BiochemUploadForm(database, mission_id, instance=bc_database,
                                 initial={'selected_database': database_id})
    else:
        form = BiochemUploadForm(database, mission_id)

    html = render_crispy_form(form)
    form_soup = BeautifulSoup(html, 'html.parser')
    details = form_soup.find(id='div_id_biochem_db_details_input')

    # calls to this method should already target #div_id_biochem_db_details_input
    soup.append(details)
    return HttpResponse(soup)


def validate_connection(request, database, mission_id):
    if request.method == "GET":
        # if connected to the database the validate connection button will be in it's 'disconnect' state
        # if disconnected the button will be in it's 'connect' state
        if 'connect' in request.GET:
            soup = BeautifulSoup('', 'html.parser')
            soup.append(update_connection_button(database, mission_id, post=True))
            return HttpResponse(soup)
        elif 'disconnect' in request.GET:
            # if the user disconnects clear the password from the cache and set the connection button
            # back to it's origional state.
            soup = BeautifulSoup('', 'html.parser')

            sentinel = object()
            database_id = caches['biochem_keys'].get('database_id', sentinel)
            if database_id is not sentinel:
                caches['biochem_keys'].delete('pwd', version=database_id)

                url = reverse_lazy('core:mission_samples_upload_bio_chem', args=(database, mission_id,))
                db_form = BiochemUploadForm(database, mission_id, initial={'selected_database': database_id})
                db_form_html = render_crispy_form(db_form)

                title_attributes = get_crispy_element_attributes(db_form.get_card_title())
                soup = BeautifulSoup(db_form_html, 'html.parser')
                soup.find(id=title_attributes['id']).attrs['hx-swap-oob'] = 'true'

            close_old_connections()
            soup.append(update_connection_button(database, mission_id))
            return HttpResponse(soup)
    else:
        soup = BeautifulSoup('', 'html.parser')
        msg_div = soup.new_tag('div')
        msg_div.attrs = {
            'id': "div_id_biochem_alert_biochem_db_details",
            'hx-swap-oob': 'true'
        }
        soup.append(msg_div)

        if 'connect' in request.POST:
            database_id = request.POST['selected_database']
            password = request.POST['db_password']

            bc_database = settings_models.BcDatabaseConnection.objects.get(pk=database_id)
            settings.DATABASES['biochem'] = bc_database.connect(password=password)
            connection_success = False

            # we don't care about the table name in this case, we're just checking the connection
            bcs_d = biochem.upload.get_bcs_d_model('connection_test')
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
                    alert_soup = core_forms.blank_alert(component_id="div_id_upload_biochem", alert_type="danger",
                                                        message=message)
                    msg_div.append(alert_soup)
                elif e.args[0].code == 1017:
                    message = _("Invalid username/password; login denied")
                    alert_soup = core_forms.blank_alert(component_id="div_id_upload_biochem", alert_type="danger",
                                                        message=message)
                    msg_div.append(alert_soup)
                elif e.args[0].code == 1005:
                    message = _("null password given; login denied")
                    alert_soup = core_forms.blank_alert(component_id="div_id_upload_biochem", alert_type="danger",
                                                        message=message)
                    msg_div.append(alert_soup)
                else:
                    logger.exception(e)
                    message = _("An unexpected database error occured. (see ./logs/error.log)")
                    alert_soup = core_forms.blank_alert(component_id="div_id_upload_biochem", alert_type="danger",
                                                        message=message)
                    msg_div.append(alert_soup)

            if caches['biochem_keys'].get('database_id', -1) != -1:
                caches['biochem_keys'].delete('database_id')

            if caches['biochem_keys'].get('pwd', -1) != -1:
                caches['biochem_keys'].delete('pwd')

            if connection_success:
                caches['biochem_keys'].set('database_id', database_id, 3600)
                caches['biochem_keys'].set(f'pwd', password, 3600, version=database_id)

            # since we have a DB password in the cache we'll update the page
            # to indicate we're connected or there was an issue
            soup.append(update_connection_button(database, mission_id, post=False, error=(not connection_success)))

        else:
            if 'selected_database' in request.POST and request.POST['selected_database']:
                bc_database = settings_models.BcDatabaseConnection.objects.get(pk=request.POST['selected_database'])
                db_form = BiochemUploadForm(database, mission_id, data=request.POST, instance=bc_database)
            else:
                db_form = BiochemUploadForm(database, mission_id, data=request.POST)

            if db_form.is_valid():
                # if the form is valid we'll render it then send back the elements of the form that have to change
                # basically just the selected database dropdown and clear the password field, so just the title bar
                db_details = db_form.save()

                # set the selected database to the updated/saved value
                new_db_form = BiochemUploadForm(database, mission_id, initial={'selected_database': db_details.pk})
                selected_db_block = render_crispy_form(new_db_form)

                selected_db_soup = BeautifulSoup(selected_db_block, 'html.parser')
                selected_db_soup.find(id=new_db_form.get_card_header_id()).attrs['hx-swap-oob'] = 'true'
                soup.append(selected_db_soup)
            else:
                form_errors = render_crispy_form(db_form)
                form_soup = BeautifulSoup(form_errors, 'html.parser')
                form_soup.find(id="div_id_biochem_db_details_input").attrs['hx-swap-oob'] = 'true'

                soup.append(form_soup)
            soup.append(update_connection_button(database, mission_id))

        return HttpResponse(soup)


def is_connected():
    selected_database = caches['biochem_keys'].get('database_id', -1)
    return selected_database != -1 and caches['biochem_keys'].get('pwd', -1, version=selected_database) != -1


url_prefix = "<str:database>/<str:mission_id>"
database_urls = [
    path(f'{url_prefix}/sample/errors/biochem/', get_biochem_errors, name="form_biochem_errors"),
    path(f'{url_prefix}/database/details/', get_tns_details, name='form_biochem_database_get_database'),
    path(f'{url_prefix}/database/add/', add_database, name='form_biochem_database_add_database'),
    path(f'{url_prefix}/database/remove/', remove_database, name='form_biochem_database_remove_database'),
    path(f'{url_prefix}/database/select/', select_database, name='form_biochem_database_update_db_selection'),
    path(f'{url_prefix}/database/connect/', validate_connection, name='form_biochem_database_validate_connection'),
]
