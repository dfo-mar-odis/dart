import os.path
import time

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

import biochem.upload

from core import models as core_models
from core import forms as core_forms
from core.forms import get_crispy_element_attributes
from dart.utils import load_svg

from settingsdb import models

import logging

user_logger = logging.getLogger('dart.user')
logger = logging.getLogger('dart')


class BiochemUploadForm(core_forms.CollapsableCardForm, forms.ModelForm):
    selected_database = forms.ChoiceField(required=False)
    db_password = forms.CharField(widget=forms.PasswordInput(render_value=True), required=False)

    # I had to override the default Bootstrap template for fields, because someone thought putting 'mb-3'
    # as a default for field wrappers was a good idea and it creates a massive gap under the inputs when
    # used in a card title
    field_template = os.path.join(settings.TEMPLATE_DIR, "field.html")

    # the download url can be set when constructing the card if it's desired to have a button to create/download
    # database table rows instead of writing the rows to the database
    download_url = None

    class Meta:
        model = models.BcDatabaseConnection
        fields = ['account_name', 'uploader', 'name', 'host', 'port', 'engine', 'selected_database', 'db_password']

    def get_db_select(self):
        url = reverse_lazy('core:form_biochem_validate_database_connection', args=(self.database, self.mission.pk,))

        title_id = f"control_id_database_select_{self.card_name}"

        db_select_attributes = {
            'id': title_id,
            'class': 'form-select form-select-sm mt-1',
            'name': 'selected_database',
            'hx-get': url,
            'hx-swap': 'none'
        }
        db_select = Column(
            Field('selected_database', template=self.field_template, **db_select_attributes,
                  wrapper_class="col-auto"),
            id=f"div_id_db_select_{self.card_name}",
            css_class="col-auto"
        )

        return db_select

    def get_db_password(self):
        connect_button_icon = load_svg('plug')

        connect_button_id = f'btn_id_connect_{self.card_name}'
        url = reverse_lazy('core:form_biochem_validate_database_connection', args=(self.database, self.mission.pk,))

        connect_button_class = "btn btn-primary btn-sm"
        if 'selected_database' in self.initial and self.initial['selected_database']:
            sentinel = object()
            password = caches['biochem_keys'].get("pwd", sentinel, version=self.initial['selected_database'])
            if password is not sentinel:
                connect_button_class = "btn btn-success btn-sm"

        connect_button_attrs = {
            'id': connect_button_id,
            'name': 'connect',
            'hx-get': url,
            'hx-swap': 'none'
        }
        connect_button = StrictButton(connect_button_icon, css_class=connect_button_class, **connect_button_attrs)

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
                        connect_button,
                        css_class="input-group-sm mt-1"
                    ),
                    css_class="input-group input-group-sm"
                ),
                css_class='',
                id=f"div_id_db_password_{self.card_name}",
            )
        )

        return password_field

    def get_upload_url(self):
        return self.upload_url

    def get_upload(self):
        # url = reverse_lazy('core:mission_samples_upload_bio_chem', args=(self.mission_id,))
        upload_button_icon = load_svg('database-add')
        upload_button_id = f'btn_id_upload_{self.card_name}'
        upload_button_attrs = {
            'id': upload_button_id,
            'name': 'upload',
            'hx-get': self.get_upload_url(),
            'hx-swap': 'none'
        }
        upload_button = StrictButton(upload_button_icon, css_class='btn btn-sm btn-primary', **upload_button_attrs)

        upload_field = Column(
            Div(id='div_id_upload_sensor_type_list'),
            upload_button,
            id=f"div_id_db_upload_{self.card_name}",
            css_class="col-auto"
        )

        return upload_field

    def get_download_url(self):
        return self.download_url

    def get_download(self):
        # url = reverse_lazy('core:mission_samples_upload_bio_chem', args=(self.mission_id,))
        download_button_icon = load_svg('arrow-down-square')
        download_button_id = f'btn_id_download_{self.card_name}'
        download_button_attrs = {
            'id': download_button_id,
            'name': 'download',
            'hx-get': self.get_download_url(),
            'hx-swap': 'none'
        }
        download_button = StrictButton(download_button_icon, css_class='btn btn-sm btn-primary',
                                       **download_button_attrs)

        download_field = Column(
            Div(id='div_id_upload_sensor_type_list'),
            download_button,
            id=f"div_id_db_upload_{self.card_name}",
            css_class="col-auto"
        )

        return download_field

    def get_alert_area(self):
        msg_row = Row(id=f"div_id_biochem_alert_{self.card_name}")
        return msg_row

    def get_card_header(self):
        header = super().get_card_header()

        header.fields[0].fields.append(self.get_db_select())
        header.fields[0].fields.append(self.get_db_password())
        header.fields[0].fields.append(self.get_upload())

        if self.get_download_url():
            header.fields[0].fields.append(self.get_download())

        header.fields.append(self.get_alert_area())
        return header

    def get_card_body(self):
        body = super().get_card_body()

        button_column = Column(css_class='align-self-center mb-1')

        url = reverse_lazy('core:form_biochem_validate_database_connection', args=(self.database, self.mission.pk,))

        input_row = Row(
            Column(Field('account_name')),
            Column(Field('uploader')),
            Column(Field('name')),
            Column(Field('host')),
            Column(Field('port')),
            Column(Field('engine')),
            button_column,
            id="div_id_biochem_db_details_input"
        )

        if self.instance and self.instance.pk:
            update_attrs = {
                'id': 'btn_id_db_details_update',
                'title': _('Update'),
                'name': 'update_db',
                'value': self.instance.pk,
                'hx_get': url,
                'hx_swap': 'none'
            }
            icon = load_svg('arrow-clockwise')
            update_button = StrictButton(icon, css_class="btn btn-primary btn-sm", **update_attrs)
            button_column.append(update_button)
        else:
            add_attrs = {
                'id': 'btn_id_db_details_add',
                'title': _('Add'),
                'name': 'add_db',
                'hx_get': url,
                'hx_swap': 'none'
            }
            icon = load_svg('plus-square')
            add_button = StrictButton(icon, css_class="btn btn-primary btn-sm", **add_attrs)
            button_column.append(add_button)

        body.append(input_row)

        return body

    # at a minimum a mission_id and what happens when the upload button are pressed must be supplied in
    def __init__(self, database, mission, upload_url, *args, **kwargs):
        if not mission:
            raise KeyError("missing mission for database connection card")

        if not upload_url:
            raise KeyError("missing upload url for database connection card")

        self.mission = mission
        self.database = database
        self.upload_url = upload_url

        if 'download_url' in kwargs:
            self.download_url = kwargs.pop('download_url')

        super().__init__(*args, **kwargs, card_name="biochem_db_details", card_title=_("Biochem Database"))

        self.fields['selected_database'].label = False
        self.fields['db_password'].label = False

        databases = models.BcDatabaseConnection.objects.all()
        self.fields['selected_database'].choices = [(db.id, db) for db in databases]
        self.fields['selected_database'].choices.insert(0, (None, '--- New ---'))

        if 'selected_database' in self.initial:
            database_id = int(self.initial['selected_database'])
            sentinel = object()
            password = caches['biochem_keys'].get('pwd', sentinel, version=database_id)
            if password is not sentinel:
                self.fields['db_password'].initial = password


# this button is placed in the title of the Database card to indicate if the user is connected, or if there's
# an issue connecting to the data base. It's used in multiple methods when actions are preformed to change
# the status of the button.
def update_connection_button(database, mission: core_models.Mission, post: bool = False, error: bool = False):

    url = reverse_lazy('core:form_biochem_validate_database_connection', args=(database, mission.pk,))

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


def validate_database(request, database, mission_id):
    mission = core_models.Mission.objects.using(database).get(pk=mission_id)
    url = reverse_lazy('core:mission_samples_upload_bio_chem', args=(database, mission_id,))
    if request.method == "GET":
        if 'add_db' in request.GET or 'update_db' in request.GET:
            soup = BeautifulSoup('', 'html.parser')
            msg_div = soup.new_tag('div')
            msg_div.attrs = {
                'id': 'div_id_biochem_alert_biochem_db_details',
                'hx-swap-oob': 'true'
            }
            soup.append(msg_div)

            url = reverse_lazy('core:form_biochem_validate_database_connection', args=(database, mission_id,))
            attrs = {
                'component_id': 'div_id_biochem_alert',
                'message': _("Adding Database"),
                'hx-post': url,
                'hx-trigger': 'load'
            }
            alert_soup = core_forms.save_load_component(**attrs)
            msg_div.append(alert_soup)

            if 'add_db' in request.GET:
                # if we're adding a new DB, remove the selected input field containing the pk for the db instance
                select = soup.new_tag('select')
                select.attrs = {
                    'id': 'select_id_db_details',
                    'hx-swap-oob': 'true'
                }
                soup.append(select)

            return HttpResponse(soup)
        elif 'selected_database' in request.GET:
            # if the selected database changes update the form to show the selection
            database_id = request.GET['selected_database']
            password = None
            sentinal = object()
            if caches['biochem_keys'].get('database_id', sentinal) is not sentinal:
                if caches['biochem_keys'].get('pwd', sentinal, version=database_id) is not sentinal:
                    password = caches['biochem_keys'].get('pwd', version=database_id)

            if database_id:
                bc_database = models.BcDatabaseConnection.objects.get(pk=database_id)
                db_form = BiochemUploadForm(database, mission, url, instance=bc_database)
                caches['biochem_keys'].set('database_id', bc_database.pk, 3600)
            else:
                db_form = BiochemUploadForm(database, mission, url)
                caches['biochem_keys'].delete('database_id')

            form_html = render_crispy_form(db_form)
            soup = BeautifulSoup(form_html, 'html.parser')

            body_attrs = get_crispy_element_attributes(db_form.get_card_body())
            soup.find(id=body_attrs['id']).attrs['hx-swap-oob'] = 'true'

            password_soup = soup.find(id="control_id_password_biochem_db_details")
            password_soup.attrs['hx-swap-oob'] = 'true'
            password_soup.attrs['value'] = password

            soup.append(update_connection_button(database, mission))

            return HttpResponse(soup)
        elif 'connect' in request.GET:
            soup = BeautifulSoup('', 'html.parser')
            soup.append(update_connection_button(database, mission, post=True))
            return HttpResponse(soup)
        elif 'disconnect' in request.GET:
            # if the user disconnects clear the password from the cache and set the connection button
            # back to it's origional state.
            soup = BeautifulSoup('', 'html.parser')

            sentinel = object()
            database_id = caches['biochem_keys'].get('database_id', sentinel)
            if database_id is not sentinel:
                caches['biochem_keys'].delete('pwd', version=database_id)

                db_form = BiochemUploadForm(database, mission, url, initial={'selected_database': database_id})
                db_form_html = render_crispy_form(db_form)

                title_attributes = get_crispy_element_attributes(db_form.get_card_title())
                soup = BeautifulSoup(db_form_html, 'html.parser')
                soup.find(id=title_attributes['id']).attrs['hx-swap-oob'] = 'true'

            close_old_connections()
            soup.append(update_connection_button(database, mission))
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

            bc_database = models.BcDatabaseConnection.objects.get(pk=database_id)
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

            if connection_success:
                caches['biochem_keys'].set('database_id', database_id, 3600)
                caches['biochem_keys'].set(f'pwd', password, 3600, version=database_id)

            # since we have a DB password in the cache we'll update the page
            # to indicate we're connected or there was an issue
            soup.append(update_connection_button(database, mission, post=False, error=(not connection_success)))

            return HttpResponse(soup)
        else:
            soup = BeautifulSoup('', 'html.parser')
            div = soup.new_tag('div')
            div.attrs = {
                'id': 'div_id_biochem_alert_biochem_db_details',
                'hx-swap-oob': 'true'
            }
            soup.append(div)

            soup.append(update_connection_button(database, mission))

            if 'selected_database' in request.POST and request.POST['selected_database']:
                bc_database = models.BcDatabaseConnection.objects.get(pk=request.POST['selected_database'])
                db_form = BiochemUploadForm(database, mission, url, data=request.POST, instance=bc_database)
            else:
                db_form = BiochemUploadForm(database, mission, url, data=request.POST)

            if db_form.is_valid():
                # if the form is valid we'll render it then send back the elements of the form that have to change
                # basically just the selected database dropdown and clear the password field, so just the title bar
                db_details = db_form.save()

                # set the selected database to the updated/saved value
                new_db_form = BiochemUploadForm(database, mission, url, initial={'selected_database': db_details.pk})
                selected_db_block = render_crispy_form(new_db_form)

                selected_db_soup = BeautifulSoup(selected_db_block, 'html.parser')
                selected_db_soup.find(id=new_db_form.get_card_header_id()).attrs['hx-swap-oob'] = 'true'
                soup.append(selected_db_soup)
            else:
                form_errors = render_crispy_form(db_form)
                form_soup = BeautifulSoup(form_errors, 'html.parser')
                form_soup.find(id="div_id_biochem_db_details_input").attrs['hx-swap-oob'] = 'true'

                soup.append(form_soup)

            return HttpResponse(soup)


def upload_bcs_d_data(mission: core_models.Mission, uploader: str):
    database = mission._state.db
    # 1) get bottles from BCS_D table
    bcs_d = biochem.upload.get_bcs_d_model(mission.get_biochem_table_name)
    exists = biochem.upload.check_and_create_model('biochem', bcs_d)

    # 2) if the BCS_D table doesn't exist, create with all the bottles. We're only uploading CTD bottles
    ctd_events = core_models.Event.objects.using(database).filter(trip__mission=mission, 
                                                                  instrument__type=core_models.InstrumentType.ctd)
    bottles = core_models.Bottle.objects.using(database).filter(event__in=ctd_events)
    # bottles = models.Bottle.objects.using(database).filter(event__trip__mission=mission)
    if exists:
        # 3) else filter bottles from local db where bottle.last_modified > bcs_d.created_date
        last_uploaded = bcs_d.objects.all().values_list('created_date', flat=True).distinct().last()
        if last_uploaded:
            bottles = bottles.filter(last_modified__gt=last_uploaded)

    if bottles.exists():
        # 4) upload only bottles that are new or were modified since the last biochem upload
        # send_user_notification_queue('biochem', _("Compiling BCS rows"))
        user_logger.info(_("Compiling BCS rows"))
        create, update, fields = biochem.upload.get_bcs_d_rows(uploader=uploader, bottles=bottles, bcs_d_model=bcs_d)

        # send_user_notification_queue('biochem', _("Creating/updating BCS rows"))
        user_logger.info(_("Creating/updating BCS rows"))
        biochem.upload.upload_bcs_d(bcs_d, create, update, fields)


def upload_bcd_d_data(mission: core_models.Mission, uploader: str):
    database = mission._state.db
    # 1) get the biochem BCD_D model
    bcd_d = biochem.upload.get_bcd_d_model(mission.get_biochem_table_name)

    # 2) if the BCD_D model doesn't exist create it and add all samples specified by sample_id
    exists = biochem.upload.check_and_create_model('biochem', bcd_d)

    if exists:
        user_logger.info(_("Compiling rows for : ") + mission.name)

        # 3) else filter the samples down to rows based on:
        # 3a) samples in this mission
        # 3b) samples of the current sample_type
        datatypes = core_models.BioChemUpload.objects.using(database).filter(
            type__mission=mission).values_list('type', flat=True).distinct()

        discreate_samples = core_models.DiscreteSampleValue.objects.using(database).filter(
            sample__bottle__event__trip__mission=mission
        )
        discreate_samples = discreate_samples.filter(sample__type_id__in=datatypes)

        if discreate_samples.exists():
            # 4) upload only samples that are new or were modified since the last biochem upload
            message = _("Compiling BCD rows for sample type") + " : " + mission.name
            user_logger.info(message)
            create, update, fields = biochem.upload.get_bcd_d_rows(uploader=uploader, samples=discreate_samples,
                                                                   bcd_d_model=bcd_d)

            message = _("Creating/updating BCD rows for sample type") + " : " + mission.name
            user_logger.info(message)
            biochem.upload.upload_bcd_d(bcd_d, discreate_samples, create, update, fields)


def upload_bcs_p_data(mission: core_models.Mission, uploader: str):
    database = mission._state.db
    
    # 1) get bottles from BCS_P table
    bcs_p = biochem.upload.get_bcs_p_model(mission.get_biochem_table_name)
    exists = biochem.upload.check_and_create_model('biochem', bcs_p)

    # 2) if the bcs_p table doesn't exist, create with all the bottles. linked to plankton samples
    samples = core_models.PlanktonSample.objects.using(database).filter(bottle__event__trip__mission=mission)
    bottle_ids = samples.values_list('bottle_id').distinct()
    bottles = core_models.Bottle.objects.using(database).filter(pk__in=bottle_ids)

    # bottles = models.Bottle.objects.using(database).filter(event__trip__mission=mission)
    # if exists:
    #     # 3) else filter bottles from local db where bottle.last_modified > bcs_p.created_date
    #     last_uploaded = bcs_p.objects.all().values_list('created_date', flat=True).distinct().last()
    #     if last_uploaded:
    #         bottles = bottles.filter(last_modified__gt=last_uploaded)

    if bottles.exists():
        # 4) upload only bottles that are new or were modified since the last biochem upload
        # send_user_notification_queue('biochem', _("Compiling BCS rows"))
        user_logger.info(_("Compiling BCS rows"))
        bcs_create, bcs_update, updated_fields = biochem.upload.get_bcs_p_rows(uploader, bottles, bcs_p)

        # send_user_notification_queue('biochem', _("Creating/updating BCS rows"))
        user_logger.info(_("Creating/updating BCS rows"))
        biochem.upload.upload_bcs_p(bcs_p, bcs_create, bcs_update, updated_fields)


def upload_bcd_p_data(mission: core_models.Mission, uploader: str):
    database = mission._state.db

    # 1) get bottles from BCD_P table
    bcd_p = biochem.upload.get_bcd_p_model(mission.get_biochem_table_name)
    exists = biochem.upload.check_and_create_model('biochem', bcd_p)

    # 2) if the bcs_p table doesn't exist, create with all the bottles. linked to plankton samples
    samples = core_models.PlanktonSample.objects.using(database).filter(bottle__event__trip__mission=mission)

    # bottles = models.Bottle.objects.using(database).filter(event__trip__mission=mission)
    # if exists:
    #     # 3) else filter bottles from local db where bottle.last_modified > bcs_p.created_date
    #     last_uploaded = bcs_p.objects.all().values_list('created_date', flat=True).distinct().last()
    #     if last_uploaded:
    #         bottles = bottles.filter(last_modified__gt=last_uploaded)

    if samples.exists():
        # 4) upload only bottles that are new or were modified since the last biochem upload
        # send_user_notification_queue('biochem', _("Compiling BCS rows"))
        user_logger.info(_("Compiling BCD rows"))
        bcd_create, bcd_update, updated_fields = biochem.upload.get_bcd_p_rows(uploader, samples, bcd_p)

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


def get_database_connection_form(request, database, mission_id, upload_url, download_url):
    mission = core_models.Mission.objects.using(database).get(pk=mission_id)
    database_connections = models.BcDatabaseConnection.objects.all()
    if database_connections.exists():
        selected_db = database_connections.first()
        sentinel = object()
        db_id = caches['biochem_keys'].get('database_id', sentinel)
        if db_id is sentinel:
            db_id = selected_db.pk
        initial = {'selected_database': db_id}
        database_form_crispy = BiochemUploadForm(database, mission, upload_url, download_url=download_url,
                                                 instance=selected_db, initial=initial)
    else:
        database_form_crispy = BiochemUploadForm(database, mission, upload_url, download_url=download_url)

    context = {}
    context.update(csrf(request))
    database_form_html = render_crispy_form(database_form_crispy, context=context)
    database_form_soup = BeautifulSoup(database_form_html, 'html.parser')

    form_soup = BeautifulSoup('<form id="form_id_db_connect"></form>', 'html.parser')
    form = form_soup.find('form')
    form.append(database_form_soup)

    return form_soup


# supply the upload_function that gathers data and sends it to the database.
# It will receive a core.core_models.Mission and core.models.BcDatabaseConnection
def upload_bio_chem(request, database, mission_id, upload_function):

    soup = BeautifulSoup('', 'html.parser')
    div = soup.new_tag('div')
    div.attrs = {
        'id': "div_id_biochem_alert_biochem_db_details",
        'hx-swap-oob': 'true'
    }
    soup.append(div)

    # check that the database and password were set in the cache
    sentinel = object()
    database_id = caches['biochem_keys'].get('database_id', default=sentinel)
    password = caches['biochem_keys'].get(f'pwd', default=sentinel, version=database_id)
    if database_id is sentinel or password is sentinel:
        attrs = {
            'component_id': 'div_id_upload_biochem',
            'alert_type': 'danger',
            'message': _("Database connection is unavailable, reconnect and try again."),
        }
        alert_soup = core_forms.blank_alert(**attrs)
        div.append(alert_soup)

        return HttpResponse(soup)

    bc_database = models.BcDatabaseConnection.objects.get(pk=database_id)
    if request.method == "GET":

        message_component_id = 'div_id_upload_biochem'
        attrs = {
            'component_id': message_component_id,
            'alert_type': 'info',
            'message': _("Uploading"),
            'hx-post': request.scope['path'],  # reuse the url of whatever is calling this function
            'hx-swap': 'none',
            'hx-trigger': 'load',
            'hx-target': "#div_id_biochem_alert_biochem_db_details",
            'hx-ext': "ws",
            'ws-connect': f"/ws/biochem/notifications/{message_component_id}/"
        }
        alert_soup = core_forms.save_load_component(**attrs)

        # add a message area for websockets
        msg_div = alert_soup.find(id="div_id_upload_biochem_message")
        msg_div.string = ""

        # The core.consumer.processing_elog_message() function is going to write output to a div
        # with the 'status' id, we'll stick that in the loading alerts message area and bam! Instant notifications!
        msg_div_status = soup.new_tag('div')
        msg_div_status['id'] = 'status'
        msg_div_status.string = _("Loading")
        msg_div.append(msg_div_status)
        div.append(alert_soup)

    elif request.method == "POST":
        # have a couple second pause for the websocket to finish initializing.
        time.sleep(2)

        mission = core_models.Mission.objects.using(database).get(pk=mission_id)

        try:
            uploader = bc_database.uploader if bc_database.uploader else bc_database.account_name

            upload_function(mission, uploader)
            attrs = {
                'component_id': 'div_id_upload_biochem',
                'alert_type': 'success',
                'message': _("Success"),
            }
            alert_soup = core_forms.blank_alert(**attrs)
            div.append(alert_soup)

        except DatabaseError as e:
            logger.exception(e)

            # A 12545 Oracle error means there's an issue with the database connection. This could be because
            # the user isn't logged in on VPN so the Oracle DB can't be connected to.
            if e.args[0].code == 12545:
                caches['biochem_keys'].delete('pwd', version=database_id)
                close_old_connections()
                soup.append(update_connection_button(soup, mission_id, error=True))
                attrs = {
                    'component_id': 'div_id_upload_biochem',
                    'alert_type': 'danger',
                    'message': f'{e.args[0].code} : ' + _("Issue connecting to database, "
                                                          "this may be due to VPN. (see ./logs/error.log)."),
                }
            else:
                attrs = {
                    'component_id': 'div_id_upload_biochem',
                    'alert_type': 'danger',
                    'message': f'{e.args[0].code} : ' + _("An unknown database issue occurred (see ./logs/error.log)."),
                }

            alert_soup = core_forms.blank_alert(**attrs)
            div.append(alert_soup)
        except KeyError as e:
            attrs = {
                'component_id': 'div_id_upload_biochem',
                'alert_type': 'danger',
                'message': e.args[0],
            }

            alert_soup = core_forms.blank_alert(**attrs)
            div.append(alert_soup)

    return HttpResponse(soup)


database_urls = [
    path('<str:database>/sample/errors/biochem/<int:mission_id>/', get_biochem_errors, name="form_biochem_errors"),
    path('<str:database>/database/validate/<int:mission_id>', validate_database,
         name='form_biochem_validate_database_connection'),
]
