from bs4 import BeautifulSoup

from crispy_forms.utils import render_crispy_form

from django.test import tag, Client
from django.conf import settings
from django.urls import reverse

import settingsdb.models
from config.tests.DartTestCase import DartTestCase

from core import form_biochem_database
from core.tests import CoreFactoryFloor as core_factory



@tag('forms', 'form_biochem_mission_summary')
class TestFomrBioChemMissionSummary(DartTestCase):
    def setUp(self):
        pass

    def test_get_summary_card_no_connection(self):
        # test that without a DB connection the Alert card will tell the user
        # they have to login to a database
        pass


@tag('forms', 'form_biochem_database')
class TestFormBioChemDatabase(DartTestCase):

    update_tns_details_url = "core:form_biochem_database_get_database"
    add_database_url = "core:form_biochem_database_add_database"
    remove_database_url = "core:form_biochem_database_remove_database"
    update_db_selection_url = "core:form_biochem_database_update_db_selection"
    validate_connection_url = "core:form_biochem_database_validate_connection"

    def setUp(self):
        self.client = Client()
        self.mission = core_factory.MissionFactory()

    @tag('form_biochem_database_test_initial_form')
    def test_initial_form(self):
        form = form_biochem_database.BiochemConnectionForm()

        html = render_crispy_form(form)

        soup = BeautifulSoup(html, 'html.parser')

        self.assertIsNotNone(soup)

        tns_field = soup.find(id=form.get_tns_name_field_id())
        tns_url = reverse(self.update_tns_details_url)
        self.assertIsNotNone(tns_field)

        self.assertIn('name', tns_field.attrs)
        self.assertIn(tns_field.attrs['name'], 'name')

        self.assertIn('hx-get', tns_field.attrs)
        self.assertIn(tns_field.attrs['hx-get'], tns_url)

        self.assertIn('hx-trigger', tns_field.attrs)
        self.assertIn(tns_field.attrs['hx-trigger'], 'keyup changed delay:500ms')

        # the form body needs to have a hx-trigger='database_selection_changed from:body' on it
        # to refresh the form if the database selection changes
        input_id = "div_id_biochem_db_details_input"
        input_row = soup.find(id=input_id)
        self.assertIsNotNone(input_row)
        self.assertIn('hx-trigger', input_row.attrs)
        self.assertEqual('database_selection_changed from:body', input_row.attrs['hx-trigger'])

        selected_db = soup.find(id="control_id_database_select_biochem_db_details")
        selection_change_url = reverse(self.update_db_selection_url)

        self.assertIsNotNone(selected_db)
        self.assertIn('hx-get', selected_db.attrs)
        self.assertEqual(selection_change_url, selected_db.attrs['hx-get'])

        self.assertIn('hx-target', selected_db.attrs)
        self.assertEqual(f'#{input_id}', selected_db.attrs['hx-target'])

        self.assertIn('hx-swap', selected_db.attrs)
        self.assertEqual('outerHTML', selected_db.attrs['hx-swap'])

    @tag('form_biochem_database_test_tns_name')
    def test_tns_name(self):
        # provided a tns name the Server Address and Port fields should be populated
        # from the django.conf.settings.TNS_NAME array
        ttran = settings.TNS_NAMES.get('TTRAN')

        url = reverse(self.update_tns_details_url)
        response = self.client.get(url, {'name': 'TTRAN'})

        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup)

        host = soup.find(id='input_id_host_biochem_db_details')
        self.assertIsNotNone(host)

        port = soup.find(id='input_id_port_biochem_db_details')
        self.assertIsNotNone(port)

    @tag('form_biochem_database_test_add_database_bad_post')
    def test_add_database_bad_post(self):
        # if the form is invalid the form should be returned with the invalid fields
        details = {
            # 'account_name': 'upsonp',  # this is a required field
            'uploader': 'Upsonp',
            'name': 'TTRAN',
            'host': 'VSNSBIOD78.ENT.DFO-MPO.CA',
            'port': '1521',
            'engine': '1'
        }
        url = reverse(self.add_database_url)

        response = self.client.post(url, details)
        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup)

        invalid = soup.find(attrs={'class': "is-invalid"})
        self.assertEqual('account_name', invalid.attrs['name'])

        # when a database is added, removed or updated or anytime the BiochemUploadForm is completely swapped out
        # the response should contain a 'Hx-Trigger'="biochem_db_update" to let pages using the form know they can
        # modify the form if addtional buttons are required.
        self.assertIn('Hx-Trigger', response.headers)
        self.assertEqual(response['Hx-Trigger'], 'biochem_db_update')

    @tag('form_biochem_database_test_add_database_post')
    def test_add_database_post(self):
        # provided variables and calling the add_database_url as a post request should add the database details to
        # the users Global
        details = {
            'account_name': 'upsonp',
            'uploader': 'Upsonp',
            'name': 'TTRAN',
            'host': 'VSNSBIOD78.ENT.DFO-MPO.CA',
            'port': '1521',
            'engine': '1',
        }
        url = reverse(self.add_database_url)

        response = self.client.post(url, details)
        # the response should have a database_selection_changed Hx-Trigger in the headers to notify the
        # form that it needs to populate with the selected database variables
        #
        # when a database is added, removed or updated or anytime the BiochemUploadForm is completely swapped out
        # the response should contain a 'Hx-Trigger'="biochem_db_update" to let pages using the form know they can
        # modify the form if addtional buttons are required.
        self.assertIn('Hx-Trigger', response.headers)
        self.assertEqual('database_selection_changed, biochem_db_update', response.headers['Hx-Trigger'])

        new_db = settingsdb.models.BcDatabaseConnection.objects.last()

        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup)

        # the new database should be in the selected_database field
        selected_database = soup.find(id="control_id_database_select_biochem_db_details")
        self.assertIsNotNone(selected_database)
        selected = selected_database.find(selected=True)
        self.assertIsNotNone(selected)
        self.assertEqual(str(new_db.pk), selected.attrs['value'])

    @tag('form_biochem_database_test_remove_database_post')
    def test_remove_database_post(self):
        # provided a selected_database, the remove datbase url should delete the database from the users
        # global database
        url = reverse(self.remove_database_url)
        database = settingsdb.models.BcDatabaseConnection(account_name='upsonp', uploader='Upsonp', name='TTRAN',
                                                          host='database.url.com', port='1521',
                                                          engine=settingsdb.models.EngineType.oracle)
        database.save()

        response = self.client.get(url, {'selected_database': database.pk})

        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup)

        # a blank Biochem DB form should be returned
        form = soup.find(id="div_id_card_biochem_db_details")
        self.assertIsNotNone(form)

        # when a database is added, removed or updated or anytime the BiochemUploadForm is completely swapped out
        # the response should contain a 'Hx-Trigger'="biochem_db_update" to let pages using the form know they can
        # modify the form if addtional buttons are required.
        self.assertIn('Hx-Trigger', response.headers)
        self.assertEqual(response['Hx-Trigger'], 'biochem_db_update')

    @tag('form_biochem_database_test_db_selection_changed_get')
    def test_db_selection_changed_get(self):
        # calling the db selection changed with GET variables should return the #div_id_biochem_db_details_input
        # portion of the database form with the selected database values populating the form
        url = reverse(self.update_db_selection_url)
        database = settingsdb.models.BcDatabaseConnection(account_name='upsonp', uploader='Upsonp', name='TTRAN',
                                                          host='database.url.com', port='1521',
                                                          engine=settingsdb.models.EngineType.oracle)
        database.save()
        response = self.client.get(url, {'selected_database': database.pk})

        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup)

        details = soup.find(id="div_id_biochem_db_details_input")
        self.assertIsNotNone(details)

    @tag('form_biochem_database_test_validate_connection_get')
    def test_validate_connection_get(self):
        # calling the validate connection as a get request the updated connection button which will have
        # an hx-post and hx-trigger='load'

        url = reverse(self.validate_connection_url)
        # if not connected to a database, the 'connect' button will be displayed
        # if connected the 'disconnect' button will be displayed
        response = self.client.get(url, {'connect': "true"})

        soup = BeautifulSoup(response.content, 'html.parser')
        btn = soup.find(id="btn_id_connect_biochem_db_details")
        self.assertIsNotNone(btn)
        self.assertIn('hx-swap-oob', btn.attrs)
        self.assertEqual('true', btn.attrs['hx-swap-oob'])

        self.assertIn('hx-post', btn.attrs)
        self.assertEqual(url, btn.attrs['hx-post'])

        self.assertIn('hx-trigger', btn.attrs)
        self.assertEqual('load', btn.attrs['hx-trigger'])

        pass


    def test_validate_connection_post(self):
        # this one's tricky. How do you validate a connection to a fake database?

        pass