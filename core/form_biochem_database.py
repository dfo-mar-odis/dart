import os.path

from bs4 import BeautifulSoup
from crispy_forms.bootstrap import StrictButton
from crispy_forms.layout import Column, Row, Field, HTML
from crispy_forms.utils import render_crispy_form
from django import forms
from django.conf import settings
from django.core.cache import caches
from django.db import DatabaseError
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.utils.translation import gettext as _

import biochem.upload
import dart2.settings
from core import models
from core import forms as core_forms
from dart2.utils import load_svg

import logging

logger = logging.getLogger('dart')


def get_crispy_element_attributes(element):
    attr_dict = {k: v.replace("\"", "") for k, v in [attr.split('=') for attr in element.flat_attrs.strip().split(" ")]}
    return attr_dict


class DBForm(core_forms.CollapsableCardForm, forms.ModelForm):
    selected_database = forms.ChoiceField(required=False)
    db_password = forms.CharField(widget=forms.PasswordInput(render_value=True), required=False)

    # I had to override the default Bootstrap template for fields, because someone thought putting 'mb-3'
    # as a default for field wrappers was a good idea and it creates a massive gap under the inputs when
    # used in a card title
    field_template = os.path.join(dart2.settings.TEMPLATE_DIR, "field.html")

    class Meta:
        model = models.BcDatabaseConnection
        fields = ['account_name', 'name', 'host', 'port', 'engine', 'selected_database', 'db_password']

    def get_db_select(self):
        url = reverse_lazy('core:hx_validate_database_connection')

        title_id = f"control_id_database_select_{self.card_name}"

        db_select_attributes = {
            'id': title_id,
            'class': 'form-select form-select-sm',
            'name': 'selected_database',
            'hx-get': url,
            'hx-swap': 'none'
        }
        db_select = Column(
            Row(
                Column(
                    HTML('<label class="me-2 pt-1" for="' + title_id + '">' + _("Biochem Database") + '</label>'),
                    Field('selected_database', template=self.field_template, **db_select_attributes,
                          wrapper_class='col-auto'),
                    css_class='input-group input-group-sm'
                ),
            ),
            id=f"div_id_db_select_{self.card_name}",
            css_class="col-auto"
        )

        return db_select

    def get_db_password(self):
        connect_button_icon = load_svg('plug')

        connect_button_id = f'btn_id_connect_{self.card_name}'
        url = reverse_lazy('core:hx_validate_database_connection')

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
        password_field = Column(
            Row(
                Column(
                    HTML(
                        '<label class="me-2 pt-1" for="' + password_field_label + '">' + _("Password") + '</label>'
                    ),
                    Field('db_password', id=password_field_label,
                          template=self.field_template, css_class="form-control form-control-sm"),
                    connect_button,
                    css_class='input-group input-group-sm'
                ),
            ),
            id=f"div_id_db_password_{self.card_name}"
        )

        return password_field

    def get_card_title(self):
        title = super().get_card_title()

        title.append(self.get_db_select())
        title.append(self.get_db_password())

        return title

    def get_alert_area(self):
        msg_row = Row(id=f"div_id_biochem_alert_{self.card_name}")
        return msg_row

    def get_card_header(self):
        header = super().get_card_header()
        header.append(self.get_alert_area())
        return header

    def get_card_body(self):
        body = super().get_card_body()

        button_column = Column(css_class='align-self-center mb-1')

        url = reverse_lazy('core:hx_validate_database_connection')

        input_row = Row(
            Column(Field('account_name')),
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, card_name="biochem_db_details")

        self.fields['selected_database'].label = False
        self.fields['db_password'].label = False

        databases = models.BcDatabaseConnection.objects.all()
        self.fields['selected_database'].choices = [(db.id, db) for db in databases]
        self.fields['selected_database'].choices.insert(0, (None, '--- New ---'))

        if self.initial and 'selected_database' in self.initial:
            database_id = int(self.initial['selected_database'])
            sentinel = object()
            password = caches['biochem_keys'].get('pwd', sentinel, version=database_id)
            if password is not sentinel:
                self.fields['db_password'].initial = password


def update_connection_button(soup: BeautifulSoup, post: bool = False, error: bool = False):
    url = reverse_lazy('core:hx_validate_database_connection')

    icon = BeautifulSoup(load_svg('plug'), 'html.parser').svg

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
    soup.append(button)


def validate_database(request):

    if request.method == "GET":
        if 'add_db' in request.GET or 'update_db' in request.GET:
            soup = BeautifulSoup('', 'html.parser')
            msg_div = soup.new_tag('div')
            msg_div.attrs = {
                'id': 'div_id_biochem_alert_biochem_db_details',
                'hx-swap-oob': 'true'
            }
            soup.append(msg_div)

            url = reverse_lazy('core:hx_validate_database_connection')
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
                database = models.BcDatabaseConnection.objects.get(pk=database_id)
                db_form = DBForm(instance=database)
                caches['biochem_keys'].set('database_id', database.pk, 3600)
            else:
                db_form = DBForm()
                caches['biochem_keys'].delete('database_id')

            form_html = render_crispy_form(db_form)
            soup = BeautifulSoup(form_html, 'html.parser')

            body_attrs = get_crispy_element_attributes(db_form.get_card_body())
            soup.find(id=body_attrs['id']).attrs['hx-swap-oob'] = 'true'

            password_soup = soup.find(id="control_id_password_biochem_db_details")
            password_soup.attrs['hx-swap-oob'] = 'true'
            password_soup.attrs['value'] = password

            update_connection_button(soup)

            return HttpResponse(soup)
        elif 'connect' in request.GET:
            soup = BeautifulSoup('', 'html.parser')
            update_connection_button(soup=soup, post=True)
            return HttpResponse(soup)
        elif 'disconnect' in request.GET:
            # if the user disconnects clear the password from the cache and set the connection button
            # back to it's origional state.
            soup = BeautifulSoup('', 'html.parser')

            sentinel = object()
            database_id = caches['biochem_keys'].get('database_id', sentinel)
            if database_id is not sentinel:
                caches['biochem_keys'].delete('pwd', version=database_id)

                db_form = DBForm(initial={'selected_database': database_id})
                db_form_html = render_crispy_form(db_form)

                title_attributes = get_crispy_element_attributes(db_form.get_card_title())
                soup = BeautifulSoup(db_form_html, 'html.parser')
                soup.find(id=title_attributes['id']).attrs['hx-swap-oob'] = 'true'

            update_connection_button(soup=soup)
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

            database = models.BcDatabaseConnection.objects.get(pk=database_id)
            settings.DATABASES['biochem'] = database.connect(password=password)
            connection_success = False

            # we don't care about the table name in this case, we're just checking the connection
            bcs_d = biochem.upload.get_bcs_d_model('connection_test')
            try:
                # either we'll get a 942 error indicating the connection worked by the table doesn't exist
                # or the connection worked and the table does exist. Any other reason the connection failed.
                bcs_d.objects.exists()
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
                    soup.append(alert_soup)
                elif e.args[0].code == 1017:
                    message = _("Invalid username/password; login denied")
                    alert_soup = core_forms.blank_alert(component_id="div_id_upload_biochem", alert_type="danger",
                                                        message=message)
                    soup.append(alert_soup)
                else:
                    logger.exception(e)
                    message = _("An unexpected database error occured. (see ./logs/error.log)")
                    alert_soup = core_forms.blank_alert(component_id="div_id_upload_biochem", alert_type="danger",
                                                        message=message)
                    soup.append(alert_soup)

            if connection_success:
                caches['biochem_keys'].set('database_id', database_id, 3600)
                caches['biochem_keys'].set(f'pwd', password, 3600, version=database_id)

            # since we have a DB password in the cache we'll update the page
            # to indicate we're connected or there was an issue
            update_connection_button(soup=soup, post=False, error=(not connection_success))

            return HttpResponse(soup)
        else:
            soup = BeautifulSoup('', 'html.parser')
            div = soup.new_tag('div')
            div.attrs = {
                'id': 'div_id_biochem_alert_biochem_db_details',
                'hx-swap-oob': 'true'
            }
            soup.append(div)

            update_connection_button(soup)

            if 'selected_database' in request.POST and request.POST['selected_database']:
                database = models.BcDatabaseConnection.objects.get(pk=request.POST['selected_database'])
                db_form = DBForm(request.POST, instance=database)
            else:
                db_form = DBForm(request.POST)

            if db_form.is_valid():
                # if the form is valid we'll render it then send back the elements of the form that have to change
                # basically just the selected database dropdown and clear the password field, so just the title bar
                db_details = db_form.save()

                # set the selected database to the updated/saved value
                new_db_form = DBForm(initial={'selected_database': db_details.pk})
                selected_db_block = render_crispy_form(new_db_form)

                title_attributes = get_crispy_element_attributes(new_db_form.get_card_title())

                selected_db_soup = BeautifulSoup(selected_db_block, 'html.parser')
                selected_db_soup.find(id=title_attributes['id']).attrs['hx-swap-oob'] = 'true'
                soup.append(selected_db_soup)
            else:
                form_errors = render_crispy_form(db_form)
                form_soup = BeautifulSoup(form_errors, 'html.parser')
                form_soup.find(id="div_id_biochem_db_details_input").attrs['hx-swap-oob'] = 'true'

                soup.append(form_soup)

            return HttpResponse(soup)
