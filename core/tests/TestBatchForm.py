from unittest.mock import patch, MagicMock

from bs4 import BeautifulSoup
from crispy_forms.utils import render_crispy_form
from django.core.cache import caches

from config.tests.DartTestCase import DartTestCase
from settingsdb.tests import utilities
from settingsdb.tests import SettingsFactoryFloor as settings_factory

from django.test import tag
from django.urls import reverse_lazy

from core.tests import CoreFactoryFloor
from core.tests.TestBioChemUpload import AbstractTestDatabase

from biochem import models as bio_models, upload
from biochem.tests import BCFactoryFloor

from core import form_biochem_discrete, form_biochem_plankton


class BatchTestDatabase(AbstractTestDatabase):
    form = None
    bio_model = None

    def setup(self, sample_database, bio_model):
        self.bio_model = bio_model
        self.mission = CoreFactoryFloor.MissionFactory()
        self.database_connection = sample_database

        utilities.create_model_table([bio_models.Bcbatches], 'biochem')

        caches['biochem_keys'].set('database_id', sample_database.pk, 3600)

        upload.create_model('biochem', self.bio_model)

    def tearDown(self):
        delete_db = True
        if delete_db:
            utilities.delete_model('biochem', self.bio_model)

        utilities.delete_model_table([bio_models.Bcbatches], 'biochem')


@tag('batch_form', 'discrete_batch_form_no_db')
class TestDiscreteBatchFormNoDB(DartTestCase):
    # When there's no database connection this form should still be visible to the user

    def setUp(self):
        self.mission = CoreFactoryFloor.MissionFactory()

    def test_no_connection_visible(self):
        form = form_biochem_discrete.BiochemDiscreteBatchForm(mission_id=self.mission.pk)
        html = render_crispy_form(form)
        soup = BeautifulSoup(html, 'html.parser')

        self.assertIsNotNone(soup.find(id=form.get_card_id()))


@tag('batch_form', 'discrete_batch_form')
class TestDiscreteBatchForm(BatchTestDatabase):

    # this is here for a quick "CRTL" click to jump to the URLs in the form module
    urls = form_biochem_discrete.url_patterns

    download_url = 'core:form_biochem_discrete_download_batch'
    upload_url = 'core:form_biochem_discrete_upload_batch'
    validate_1_url = 'core:form_biochem_discrete_validation1'
    validate_2_url = 'core:form_biochem_discrete_validation2'
    merge_url = 'core:form_biochem_discrete_merge'
    checkin_url = 'core:form_biochem_discrete_checkin'
    delete_batch_url = 'core:form_biochem_discrete_delete'

    def setUp(self):
        self.form = form_biochem_discrete.BiochemDiscreteBatchForm
        sample_database = settings_factory.BcDatabaseConnection()
        bio_model = upload.get_model(sample_database.bc_discrete_station_edits, bio_models.BcsP)
        super().setup(sample_database, bio_model)

    @tag('discrete_test_form_components')
    def test_form_components(self):
        form = self.form(mission_id=self.mission.pk)

        crispy_form = render_crispy_form(form)
        soup = BeautifulSoup(crispy_form, 'html.parser')
        self.assertIsNotNone(soup)

        self.assertIsNotNone(soup.find(id=form.get_batch_select_id()))
        self.assertIsNotNone(soup.find(id=form.get_validate_stage2_button_id()))
        self.assertIsNotNone(soup.find(id=form.get_merge_batch_button_id()))
        self.assertIsNotNone(soup.find(id=form.get_checkin_batch_button_id()))
        self.assertIsNotNone(soup.find(id=form.get_delete_batch_button_id()))

    @tag('discrete_test_download_button')
    def test_download_button(self):
        form = self.form(mission_id=self.mission.pk)

        crispy_form = render_crispy_form(form)
        soup = BeautifulSoup(crispy_form, 'html.parser')
        self.assertIsNotNone(soup)

        self.assertIsNotNone(btn:=soup.find(id=form.get_download_button_id()))

        url = reverse_lazy(self.download_url, args=(self.mission.pk,))
        self.assertEqual(btn['hx-get'], url)

    @tag('discrete_test_upload_button')
    def test_upload_button(self):
        form = self.form(mission_id=self.mission.pk)

        crispy_form = render_crispy_form(form)
        soup = BeautifulSoup(crispy_form, 'html.parser')

        self.assertIsNotNone(soup)
        self.assertIsNotNone(btn := soup.find(id=form.get_upload_button_id()))

        url = reverse_lazy(self.upload_url, args=(self.mission.pk,))
        self.assertEqual(btn['hx-get'], url)

    @tag('discrete_test_validate_1_button')
    def test_validate_1_button(self):
        batch_factory = BCFactoryFloor.BcBatchesFactory
        batch_factory._meta.database = 'biochem'
        batch = batch_factory()

        form = self.form(mission_id=self.mission.pk, batch_id=batch.pk)

        crispy_form = render_crispy_form(form)
        soup = BeautifulSoup(crispy_form, 'html.parser')

        self.assertIsNotNone(soup)
        self.assertIsNotNone(btn:=soup.find(id=form.get_validate_stage1_button_id()))

        url = reverse_lazy(self.validate_1_url, args=(batch.pk,))
        self.assertEqual(btn['hx-get'], url)

    @tag('discrete_test_validate_2_button')
    def test_validate_2_button(self):
        batch_factory = BCFactoryFloor.BcBatchesFactory
        batch_factory._meta.database = 'biochem'
        batch = batch_factory()

        form = self.form(mission_id=self.mission.pk, batch_id=batch.pk)

        crispy_form = render_crispy_form(form)
        soup = BeautifulSoup(crispy_form, 'html.parser')

        self.assertIsNotNone(soup)
        self.assertIsNotNone(btn:=soup.find(id=form.get_validate_stage2_button_id()))

        url = reverse_lazy(self.validate_2_url, args=(batch.pk,))
        self.assertEqual(btn['hx-get'], url)

    @tag('discrete_test_merge_button')
    def test_merge_button(self):
        batch_factory = BCFactoryFloor.BcBatchesFactory
        batch_factory._meta.database = 'biochem'
        batch = batch_factory()

        form = self.form(mission_id=self.mission.pk, batch_id=batch.pk)

        crispy_form = render_crispy_form(form)
        soup = BeautifulSoup(crispy_form, 'html.parser')

        self.assertIsNotNone(soup)
        self.assertIsNotNone(btn:=soup.find(id=form.get_merge_batch_button_id()))

        url = reverse_lazy(self.merge_url, args=(self.mission.pk, batch.pk,))
        self.assertEqual(btn['hx-get'], url)

    @tag('discrete_test_checkin_button')
    def test_checkin_button(self):
        batch_factory = BCFactoryFloor.BcBatchesFactory
        batch_factory._meta.database = 'biochem'
        batch = batch_factory()

        form = self.form(mission_id=self.mission.pk, batch_id=batch.pk)

        crispy_form = render_crispy_form(form)
        soup = BeautifulSoup(crispy_form, 'html.parser')

        self.assertIsNotNone(soup)
        self.assertIsNotNone(btn:=soup.find(id=form.get_checkin_batch_button_id()))

        url = reverse_lazy(self.checkin_url, args=(batch.pk,))
        self.assertEqual(btn['hx-get'], url)

    @tag('discrete_test_delete_batch_button')
    def test_delete_batch_button(self):
        batch_factory = BCFactoryFloor.BcBatchesFactory
        batch_factory._meta.database = 'biochem'
        batch = batch_factory()

        form = self.form(mission_id=self.mission.pk, batch_id=batch.pk)

        crispy_form = render_crispy_form(form)
        soup = BeautifulSoup(crispy_form, 'html.parser')

        self.assertIsNotNone(soup)
        self.assertIsNotNone(btn := soup.find(id=form.get_delete_batch_button_id()))

        url = reverse_lazy(self.delete_batch_url, args=(self.mission.pk, batch.pk,))
        self.assertEqual(btn['hx-get'], url)


@tag('batch_form', 'plankton_batch_form')
class TestPlanktonBatchForm(BatchTestDatabase):

    def setUp(self):
        self.form = form_biochem_plankton.BiochemPlanktonBatchForm
        sample_database = settings_factory.BcDatabaseConnection()
        bio_model = upload.get_model(sample_database.bc_plankton_station_edits, bio_models.BcsP)
        super().setup(sample_database, bio_model)

    # this is here for a quick "CRTL" click to jump to the URLs in the form module
    urls = form_biochem_plankton.urls

    download_url = 'core:form_biochem_plankton_download_batch'
    upload_url = 'core:form_biochem_plankton_upload_batch'
    validate_1_url = 'core:form_biochem_plankton_validation1'
    validate_2_url = 'core:form_biochem_plankton_validation2'
    merge_url = 'core:form_biochem_plankton_merge'
    checkin_url = 'core:form_biochem_plankton_checkin'
    delete_batch_url = 'core:form_biochem_plankton_delete'

    @tag('plankton_test_form_components')
    def test_form_components(self):
        form = self.form(mission_id=self.mission.pk)
        crispy_form = render_crispy_form(form)
        soup = BeautifulSoup(crispy_form, 'html.parser')
        self.assertIsNotNone(soup)

        self.assertIsNotNone(soup.find(id=form.get_batch_select_id()))
        self.assertIsNotNone(soup.find(id=form.get_checkin_batch_button_id()))
        self.assertIsNotNone(soup.find(id=form.get_delete_batch_button_id()))

    @tag('plankton_test_download_button')
    def test_download_button(self):
        form = self.form(mission_id=self.mission.pk)

        crispy_form = render_crispy_form(form)
        soup = BeautifulSoup(crispy_form, 'html.parser')

        self.assertIsNotNone(soup)
        self.assertIsNotNone(btn:=soup.find(id=form.get_download_button_id()))

        url = reverse_lazy(self.download_url, args=(self.mission.pk,))
        self.assertEqual(btn['hx-get'], url)

    @tag('plankton_test_upload_button')
    def test_upload_button(self):
        form = self.form(mission_id=self.mission.pk)

        crispy_form = render_crispy_form(form)
        soup = BeautifulSoup(crispy_form, 'html.parser')

        self.assertIsNotNone(soup)
        self.assertIsNotNone(btn:=soup.find(id=form.get_upload_button_id()))

        url = reverse_lazy(self.upload_url, args=(self.mission.pk,))
        self.assertEqual(btn['hx-get'], url)

    @tag('plankton_test_validate_1_button')
    def test_validate_1_button(self):
        batch_factory = BCFactoryFloor.BcBatchesFactory
        batch_factory._meta.database = 'biochem'
        batch = batch_factory()

        form = self.form(mission_id=self.mission.pk, batch_id=batch.pk)

        crispy_form = render_crispy_form(form)
        soup = BeautifulSoup(crispy_form, 'html.parser')

        self.assertIsNotNone(soup)
        self.assertIsNotNone(btn:=soup.find(id=form.get_validate_stage1_button_id()))

        url = reverse_lazy(self.validate_1_url, args=(batch.pk,))
        self.assertEqual(btn['hx-get'], url)

    @tag('plankton_test_validate_2_button')
    def test_validate_2_button(self):
        batch_factory = BCFactoryFloor.BcBatchesFactory
        batch_factory._meta.database = 'biochem'
        batch = batch_factory()

        form = self.form(mission_id=self.mission.pk, batch_id=batch.pk)

        crispy_form = render_crispy_form(form)
        soup = BeautifulSoup(crispy_form, 'html.parser')

        self.assertIsNotNone(soup)
        self.assertIsNotNone(btn:=soup.find(id=form.get_validate_stage2_button_id()))

        url = reverse_lazy(self.validate_2_url, args=(batch.pk,))
        self.assertEqual(btn['hx-get'], url)

    @tag('plankton_test_merge_button')
    def test_merge_button(self):
        batch_factory = BCFactoryFloor.BcBatchesFactory
        batch_factory._meta.database = 'biochem'
        batch = batch_factory()

        form = self.form(mission_id=self.mission.pk, batch_id=batch.pk)

        crispy_form = render_crispy_form(form)
        soup = BeautifulSoup(crispy_form, 'html.parser')

        self.assertIsNotNone(soup)
        self.assertIsNotNone(btn:=soup.find(id=form.get_merge_batch_button_id()))

        url = reverse_lazy(self.merge_url, args=(self.mission.pk, batch.pk,))
        self.assertEqual(btn['hx-get'], url)

    @tag('plankton_test_checkin_button')
    def test_checkin_button(self):
        batch_factory = BCFactoryFloor.BcBatchesFactory
        batch_factory._meta.database = 'biochem'
        batch = batch_factory()

        form = self.form(mission_id=self.mission.pk, batch_id=batch.pk)

        crispy_form = render_crispy_form(form)
        soup = BeautifulSoup(crispy_form, 'html.parser')

        self.assertIsNotNone(soup)
        self.assertIsNotNone(btn:=soup.find(id=form.get_checkin_batch_button_id()))

        url = reverse_lazy(self.checkin_url, args=(batch.pk,))
        self.assertEqual(btn['hx-get'], url)

    @tag('plankton_test_delete_batch_button')
    def test_delete_batch_button(self):
        batch_factory = BCFactoryFloor.BcBatchesFactory
        batch_factory._meta.database = 'biochem'
        batch = batch_factory()

        form = self.form(mission_id=self.mission.pk, batch_id=batch.pk)

        crispy_form = render_crispy_form(form)
        soup = BeautifulSoup(crispy_form, 'html.parser')

        self.assertIsNotNone(soup)
        self.assertIsNotNone(btn:=soup.find(id=form.get_delete_batch_button_id()))

        url = reverse_lazy(self.delete_batch_url, args=(self.mission.pk, batch.pk,))
        self.assertEqual(btn['hx-get'], url)

    @tag('form_plankton_test_biochem_validation_pass')
    @patch('core.form_biochem_plankton.connections')
    def test_validation_proc_success(self, mock_connections):
        # Mock the cursor and its methods
        mock_cursor = MagicMock()
        mock_connections.__getitem__.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        # Simulate successful validation
        mock_cursor.callfunc.side_effect = ['T', 'T', 'T']  # stn_pass_var, data_pass_var

        # Call the function
        form_biochem_plankton.validation_proc(batch_id=123)

        # Assertions
        mock_cursor.callfunc.assert_any_call("VALIDATE_PLANKTON_STATN_DATA.VALIDATE_PLANKTON_STATION", str,
                                             [123])
        mock_cursor.callfunc.assert_any_call("VALIDATE_PLANKTON_STATN_DATA.VALIDATE_PLANKTON_DATA", str, [123])
        mock_cursor.callfunc.assert_any_call("POPULATE_PLANKTON_EDITS_PKG.POPULATE_PLANKTON_EDITS", str, [123])
        mock_cursor.execute.assert_called_once_with('commit')

    @tag('form_plankton_test_biochem_validation_fail')
    @patch('core.form_biochem_plankton.connections')
    def test_validation_proc_failure(self, mock_connections):
        # Mock the cursor and its methods
        mock_cursor = MagicMock()
        mock_connections.__getitem__.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        # Simulate validation failure
        mock_cursor.callfunc.side_effect = ['F', 'T']  # stn_pass_var, data_pass_var

        # Call the function
        form_biochem_plankton.validation_proc(batch_id=123)

        # Assertions
        mock_cursor.callfunc.assert_any_call("VALIDATE_PLANKTON_STATN_DATA.VALIDATE_PLANKTON_STATION", str,
                                             [123])
        mock_cursor.callfunc.assert_any_call("VALIDATE_PLANKTON_STATN_DATA.VALIDATE_PLANKTON_DATA", str, [123])
        mock_cursor.execute.assert_called_once_with('commit')

    @tag('form_plankton_test_biochem_validation_2')
    @patch('core.form_biochem_plankton.connections')
    def test_validation2_proc_failure(self, mock_connections):
        # Mock the cursor and its methods
        mock_cursor = MagicMock()
        mock_connections.__getitem__.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        batch_id = 123
        user = self.database_connection.uploader.upper()

        # Simulate validation failure
        mock_cursor.callfunc.side_effect = ['T', 'T', 'T', 'T', 'T', 'T', 'T']  # stn_pass_var, data_pass_var

        # Call the function
        form_biochem_plankton.validation2_proc(batch_id=batch_id)

        # Assertions
        mock_cursor.callfunc.assert_any_call("BATCH_VALIDATION_PKG.CHECK_BATCH_MISSION_ERRORS", str, [batch_id, user])
        mock_cursor.callfunc.assert_any_call("BATCH_VALIDATION_PKG.CHECK_BATCH_EVENT_ERRORS", str, [batch_id, user])
        mock_cursor.callfunc.assert_any_call("BATCH_VALIDATION_PKG.CHECK_BATCH_PLANK_HEDR_ERRORS", str, [batch_id, user])
        mock_cursor.callfunc.assert_any_call("BATCH_VALIDATION_PKG.CHECK_BATCH_PLANK_GENERL_ERRS", str, [batch_id, user])
        mock_cursor.callfunc.assert_any_call("BATCH_VALIDATION_PKG.CHECK_BATCH_PLANK_DTAIL_ERRS", str, [batch_id, user])
        mock_cursor.callfunc.assert_any_call("BATCH_VALIDATION_PKG.CHECK_BATCH_PLANK_FREQ_ERRS", str, [batch_id, user])
        mock_cursor.callfunc.assert_any_call("BATCH_VALIDATION_PKG.CHECK_BATCH_PLANK_INDIV_ERRS", str, [batch_id, user])
