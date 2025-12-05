from typing import Tuple
from unittest.mock import patch, MagicMock

from bs4 import BeautifulSoup
from crispy_forms.utils import render_crispy_form
from django.core.cache import caches

from config.tests.DartTestCase import DartTestCase
from core.tests.CoreFactoryFloor import MissionFactory
from settingsdb.tests import utilities
from settingsdb.tests import SettingsFactoryFloor as settings_factory

from django.test import tag, RequestFactory
from django.urls import reverse_lazy
from django.contrib.sessions.middleware import SessionMiddleware

from core import models as core_models, form_biochem_batch2_plankton
from core.tests import CoreFactoryFloor
from core.tests.TestBioChemUpload import AbstractTestDatabase

from biochem import models as bio_models, upload
from biochem.tests import BCFactoryFloor

from core import form_biochem_discrete, form_biochem_plankton
from core import form_biochem_batch2, form_biochem_batch2_discrete

import logging

logger = logging.getLogger('dart.test')
test_logger = logging.getLogger('dart.test.batchform')

class MockBiochemBatchForm(form_biochem_batch2.BiochemDBBatchForm):
    def get_header_update_url(self):
        return "test/"

    def get_download_url(self):
        return "test/"

    def get_upload_url(self):
        return "test/"

    def get_batch_update_url(self):
        return "test/"

    def get_stage1_validate_url(self):
        return "test/"

    def get_stage2_validate_url(self):
        return "test/"

    def is_batch_stage1_validated(self) -> bool | None:
        return None

    def is_batch_stage2_validated(self) -> bool | None:
        return None

    def get_batch_choices(self) -> list[Tuple[int, str]]:
        return [(1, "Test 1"), (2, "Test 2")]


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


@tag('batch_form_2')
class TestDiscreteBatchForm2(DartTestCase):

    def setUp(self):
        self.mission: core_models.Mission = CoreFactoryFloor.MissionFactory()

    def test__descriptor_form_has_descriptor(self):
        # if a descriptor is provided this function should return none
        response = form_biochem_batch2._descriptor_form("test", self.mission.id, "14DES25001")
        self.assertIsNone(response, f"A descriptor was provided, we expect the function to return None")

    def test__descriptor_form_no_descriptor(self):
        # if no descriptor is provided this function should return a form to set the descriptor
        expected_trigger = "test"
        response = form_biochem_batch2._descriptor_form(expected_trigger, self.mission.id, None)
        self.assertIsNotNone(response.content, "A descriptor was not provided, we expect the function to return a MissionDescriptorForm as HTML")

        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup)
        self.assertIsNotNone(soup.find(id="div_id_data_alert_message_container"))
        self.assertIsNotNone(form:=soup.find("form"))
        self.assertIsNotNone(descriptor:=form.find(id="id_mission_descriptor"), f"No mission descriptor field found\n{form.prettify()}")
        self.assertIsNotNone(trigger:=form.find(id="id_trigger_action"), f"No trigger action field found\n{form.prettify()}")
        self.assertEqual(trigger.attrs['value'], expected_trigger)

    def test_set_descriptor_no_descriptor(self):
        # upon filling out the form and submitting it, if a descriptor is not provided the user should get
        # back a form highlighting that the mission descriptor is required
        url = reverse_lazy("core:form_biochem_batch_mission_descriptor", args=[self.mission.pk])
        factory = RequestFactory()
        request = factory.post(url, data={})
        response = form_biochem_batch2.set_descriptor(request, mission_id=self.mission.pk)

        # Check the response
        soup = BeautifulSoup(response.content, 'html.parser')
        # the set_descriptor function will only return the form that's intended to be swapped into the
        # div_id_data_alert_message_container. It doesn't return the container itself.
        self.assertIsNotNone(soup, "Expected to get something, but nothing was in the response.content")
        self.assertIsNotNone(soup.find("form"), "No form was returned when the mission descriptor was mission")
        self.assertIsNotNone(soup.find(id="error_1_id_mission_descriptor"), "No error found on the mission descriptor input field")


    def test_set_descriptor_with_descriptor(self):
        # upon filling out the form and submitting it, if a descriptor is provided, the mission should be saved
        # with the provided descriptor. A blank response should be returned with an 'HX-Trigger-After-Settle' =
        # download_mission_bcs_bcd
        expected_trigger = "download_mission_bcs_bcd"
        expected_descriptor = "11DE25001"
        url = reverse_lazy("core:form_biochem_batch_mission_descriptor", args=[self.mission.pk])
        factory = RequestFactory()
        request = factory.post(url, data={"trigger_action": expected_trigger,
                                          "mission_descriptor": expected_descriptor})

        # I just want to make sure
        self.assertIsNone(self.mission.mission_descriptor)

        response = form_biochem_batch2.set_descriptor(request, mission_id=self.mission.pk)

        # Check the response
        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertEqual(soup.prettify(), '', f"The response should have been empty\n{soup.prettify()}")

        self.assertIsNotNone(response.headers.get('HX-Trigger-After-Settle', None), "There should be an HX-Trigger-After-Settle that triggers a call to the download function")
        self.assertEqual(response.headers.get('HX-Trigger-After-Settle'), expected_trigger, "This wasn't the expected trigger")

        mission = core_models.Mission.objects.get(pk=self.mission.pk)
        self.assertEqual(mission.mission_descriptor, expected_descriptor, "The mission descriptor wasn't updated.")

    def test__uploader_form(self):
        # if an uploader is provided this function should return none
        response = form_biochem_batch2._descriptor_form("test", self.mission.id, "upsonp")
        self.assertIsNone(response, f"An uploader was provided, we expect the function to return None")

    def test__uploader_form_no_uploader(self):
        # if no uploader is provided this function should return a form to set the uploader
        expected_trigger = "test"
        response = form_biochem_batch2._uploader_form(expected_trigger, self.mission.id, None)
        self.assertIsNotNone(response.content,
                             "An uploader was not provided, we expect the function to return a MissionDescriptorForm as HTML")

        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup)
        self.assertIsNotNone(soup.find(id="div_id_data_alert_message_container"))
        self.assertIsNotNone(form:=soup.find("form"))
        self.assertIsNotNone(uploader:=form.find(id="id_uploader2"), f"No uploader found\n{form.prettify()}")
        self.assertIsNotNone(trigger:=form.find(id="id_trigger_action"), f"No trigger action found found\n{form.prettify()}")
        self.assertEqual(trigger.attrs['value'], expected_trigger)

    def test_set_uploader_no_uploader(self):
        # upon filling out the form and submitting it, if an uploader is not provided the user should get
        # back a form highlighting that the uploader is required
        url = reverse_lazy("core:form_biochem_batch_uploader", args=[self.mission.pk])
        factory = RequestFactory()
        request = factory.post(url, data={})
        response = form_biochem_batch2.set_uploader(request, mission_id=self.mission.pk)

        # Check the response
        soup = BeautifulSoup(response.content, 'html.parser')
        # the set_descriptor function will only return the form that's intended to be swapped into the
        # div_id_data_alert_message_container. It doesn't return the container itself.
        self.assertIsNotNone(soup, "Expected to get something, but nothing was in the response.content")
        self.assertIsNotNone(form:=soup.find("form"), f"No form was returned when the uploader was mission.\n{soup.prettify()}")
        self.assertIsNotNone(form.find(id="error_1_id_uploader2"), f"No error found on the uploader input field.\n{form.prettify()}")

    def test_set_uploader_with_uploader(self):
        # upon filling out the form and submitting it, if a descriptor is provided, the mission should be saved
        # with the provided descriptor. A blank response should be returned with an 'HX-Trigger-After-Settle' =
        # download_mission_bcs_bcd
        expected_trigger = "download_mission_bcs_bcd"
        expected_uploader = "upsonp"
        url = reverse_lazy("core:form_biochem_batch_mission_descriptor", args=[self.mission.pk])
        factory = RequestFactory()
        request = factory.post(url, data={"trigger_action": expected_trigger,
                                          "uploader2": expected_uploader})

        # This particular middleware doesn't call a get_response function, but it still requires the function
        middleware = SessionMiddleware(lambda request: None)
        middleware.process_request(request)
        request.session.save()

        response = form_biochem_batch2.set_uploader(request, mission_id=self.mission.pk)

        # Check the response
        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertEqual(soup.prettify(), '', f"The response should have been empty\n{soup.prettify()}")

        self.assertIsNotNone(response.headers.get('HX-Trigger-After-Settle', None), "There should be an HX-Trigger-After-Settle that triggers a call to the download function")
        self.assertEqual(response.headers.get('HX-Trigger-After-Settle'), expected_trigger, "This wasn't the expected trigger")

        # Check that the session variable is set
        self.assertEqual(request.session.get('uploader2'), expected_uploader, "The session variable 'uploader2' was not set correctly")

    def test_download_batch_no_mission_descriptor(self):
        # if no mission descriptor is provided for the mission the download batch function should return a
        # MissionDescriptor form that's intended to be placed in the form_biochem_batch alert area.

        # Create a fake request
        factory = RequestFactory()
        # by default the MissionFactory will create a mission without a mission descriptor
        mission_id = self.mission.pk

        # This is an abstract class that expects its extending classes to provide a url to access the function
        request = factory.post("/test/", data={})

        # Call the function
        response = form_biochem_batch2.download_batch(request, mission_id, logger_name=test_logger)

        # Check the response
        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup)
        self.assertIsNotNone(soup.find(id="div_id_data_alert_message_container"))
        self.assertIsNotNone(soup.find("form"))
        self.assertIsNotNone(soup.find(id="id_mission_descriptor"))

    def test_download_batch_no_uploader(self):
        # if a mission descriptor is provided for the mission the download batch function should next check
        # for an uploader

        # Create a fake request
        factory = RequestFactory()
        # by default the MissionFactory will create a mission without a mission descriptor
        mission_id = self.mission.pk

        # This is an abstract class that expects its extending classes to provide a url to access the function
        request = factory.get("/test/")

        # Call the function
        response = form_biochem_batch2.download_batch(request, mission_id, logger_name=test_logger)

        # Check the response
        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup)
        self.assertIsNotNone(soup.find(id="div_id_data_alert_message_container"))
        self.assertIsNotNone(soup.find("form"))

    @tag("batch_form_2_test_download_batch_all_good")
    @patch('core.form_biochem_batch2.core_forms.StatusAlert')
    def test_download_batch_all_good(self, mock_status_alert):
        # if a mission descriptor and uploader are provided, the download batch function should next call the provided
        # download_batch_func that an extending module will provide

        # by default the MissionFactory will create a mission without a mission descriptor
        expected_descriptor = "11DE25002"
        expected_uploader = "upsonp"

        mission: core_models.Mission = CoreFactoryFloor.MissionFactory(mission_descriptor=expected_descriptor)
        mission_id = mission.pk

        # Create a fake request
        factory = RequestFactory()
        request = factory.post("/test/")

        # This is an abstract class that expects its extending classes to provide a url to access the function
        middleware = SessionMiddleware(lambda request: None)
        middleware.process_request(request)
        request.session['uploader2'] = expected_uploader  # Set the required session variable
        request.session.save()

        mock_download_func = MagicMock()

        # Mock msg_alert to make is_socket_connected() return True
        mock_msg_alert_instance = mock_status_alert.return_value
        mock_msg_alert_instance.is_socket_connected.return_value = True

        response = form_biochem_batch2.download_batch(request, mission_id, logger_name=test_logger, download_batch_func=mock_download_func)

        # Verify that the mock function was called
        mock_download_func.assert_called_once_with(mission, expected_uploader)

        self.assertIsNotNone(response)

    def test_upload_batch_no_mission_descriptor(self):
        # if no mission descriptor is provided for the mission the download batch function should return a
        # MissionDescriptor form that's intended to be placed in the form_biochem_batch alert area.

        # Create a fake request
        factory = RequestFactory()
        # by default the MissionFactory will create a mission without a mission descriptor
        mission_id = self.mission.pk

        # This is an abstract class that expects its extending classes to provide a url to access the function
        request = factory.post("/test/", data={})

        # Call the function
        response = form_biochem_batch2.upload_batch(request, mission_id, logger_name=test_logger)

        # Check the response
        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup)
        self.assertIsNotNone(soup.find(id="div_id_data_alert_message_container"))
        self.assertIsNotNone(soup.find("form"))
        self.assertIsNotNone(soup.find(id="id_mission_descriptor"))

    def test_upload_batch_no_uploader(self):
        # if a mission descriptor is provided for the mission the download batch function should next check
        # for an uploader

        # Create a fake request
        factory = RequestFactory()
        # by default the MissionFactory will create a mission without a mission descriptor
        mission_id = self.mission.pk

        # This is an abstract class that expects its extending classes to provide a url to access the function
        request = factory.get("/test/")

        # Call the function
        response = form_biochem_batch2.upload_batch(request, mission_id, logger_name=test_logger)

        # Check the response
        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNotNone(soup)
        self.assertIsNotNone(soup.find(id="div_id_data_alert_message_container"))
        self.assertIsNotNone(soup.find("form"))

    # when the batch selection changes we need to reload the header.
    # the body will be its own thing, but the header will have to HX-Trigger a batch_header_updated
    # if "New" is selected we clear the header back to the download/upload buttons
    # if the user selected a batch that's passed validation we show the check-in button
    # if the user selected a batch that's failed validation we show the validation buttons as red
    # If the user selected a batch in the BCS/BCD tables we should get the validate buttons

    def test_batch_selection_default(self):
        # testing when the "new" option is selected
        data={
            "batch_selection": ""
        }
        request = RequestFactory().get("/test/", data=data)

        # test for if the selection is "new"
        response = form_biochem_batch2.get_batch_list(request, self.mission.pk, MockBiochemBatchForm)
        soup = BeautifulSoup(response.content, 'html.parser')

        selection = soup.find(id="div_id_input_batch_selection")
        self.assertIsNotNone(selection)

        option = selection.find("option", selected=True)
        self.assertIsNotNone(option)
        self.assertEqual("--- NEW ---", option.string)

        buttons = soup.find(id=form_biochem_batch2.BIOCHEM_BATCH_CONTROL_ROW_ID)
        self.assertIsNotNone(buttons)

        # Only the download and upload buttons should be present.
        download_btn = buttons.find(id="btn_id_batch_download")
        self.assertIsNotNone(download_btn)

        upload_btn = buttons.find(id="btn_id_batch_upload")
        self.assertIsNotNone(upload_btn)

    def test_batch_selection_no_validation_run(self):

        class MockTest(MockBiochemBatchForm):
            def is_batch_stage1_validated(self) -> bool | None:
                return None

        data={
            "batch_selection": 1
        }
        request = RequestFactory().get("/test/", data=data)

        # test for if the selection is "Test 1"
        response = form_biochem_batch2.get_batch_list(request, self.mission.pk, MockTest)
        soup = BeautifulSoup(response.content, 'html.parser')

        selection = soup.find(id="div_id_input_batch_selection")
        self.assertIsNotNone(selection)

        option = selection.find("option", selected=True)
        self.assertIsNotNone(option)
        self.assertEqual("Test 1", option.string)

        # we should see buttons Delete, stage 1 validate, stage 2 validate
        # stage 1 should be a btn-secondary, stage 2 validate should be disabled

        buttons = soup.find(id=form_biochem_batch2.BIOCHEM_BATCH_CONTROL_ROW_ID)
        self.assertIsNotNone(buttons)

        btn1 = buttons.find(id="btn_id_batch_delete")
        self.assertIsNotNone(btn1)

        btn2 = buttons.find(id="btn_id_batch_stage1_validate")
        self.assertIsNotNone(btn2)
        self.assertTrue("btn-secondary" in btn2.attrs["class"])

        btn3 = buttons.find(id="btn_id_batch_stage2_validate")
        self.assertIsNotNone(btn3)
        self.assertTrue("btn-secondary" in btn3.attrs["class"])
        self.assertIn("disabled", btn3.attrs)

    def test_batch_selection_stage_1_failed(self):

        # we should see buttons Delete, stage 1 validate, stage 2 validate
        # stage 1 should be a btn-danger and disabled, stage 2 validate should be disabled
        class MockTest(MockBiochemBatchForm):
            def is_batch_stage1_validated(self) -> bool | None:
                return False

        data={
            "batch_selection": 1
        }
        request = RequestFactory().get("/test/", data=data)

        # test for if the selection is "Test 1"
        response = form_biochem_batch2.get_batch_list(request, self.mission.pk, MockTest)
        soup = BeautifulSoup(response.content, 'html.parser')

        selection = soup.find(id="div_id_input_batch_selection")
        self.assertIsNotNone(selection)

        option = selection.find("option", selected=True)
        self.assertIsNotNone(option)
        self.assertEqual("Test 1", option.string)

        buttons = soup.find(id=form_biochem_batch2.BIOCHEM_BATCH_CONTROL_ROW_ID)
        self.assertIsNotNone(buttons)

        btn1 = buttons.find(id="btn_id_batch_delete")
        self.assertIsNotNone(btn1)

        btn2 = buttons.find(id="btn_id_batch_stage1_validate")
        self.assertIsNotNone(btn2)
        self.assertTrue("btn-danger" in btn2.attrs["class"])
        self.assertIn("disabled", btn2.attrs)

        btn3 = buttons.find(id="btn_id_batch_stage2_validate")
        self.assertIsNotNone(btn3)
        self.assertTrue("btn-secondary" in btn3.attrs["class"])
        self.assertIn("disabled", btn3.attrs)

    def test_batch_selection_stage_1_passed(self):

        # we should see buttons Delete, stage 1 validate, stage 2 validate
        # stage 1 should be a btn-success and disabled, stage 2 validate should be btn-secondary enabled
        class MockTest(MockBiochemBatchForm):
            def is_batch_stage1_validated(self) -> bool | None:
                return True

        data={
            "batch_selection": 1
        }
        request = RequestFactory().get("/test/", data=data)

        # test for if the selection is "Test 1"
        response = form_biochem_batch2.get_batch_list(request, self.mission.pk, MockTest)
        soup = BeautifulSoup(response.content, 'html.parser')

        selection = soup.find(id="div_id_input_batch_selection")
        self.assertIsNotNone(selection)

        option = selection.find("option", selected=True)
        self.assertIsNotNone(option)
        self.assertEqual("Test 1", option.string)

        buttons = soup.find(id=form_biochem_batch2.BIOCHEM_BATCH_CONTROL_ROW_ID)
        self.assertIsNotNone(buttons)

        btn1 = buttons.find(id="btn_id_batch_delete")
        self.assertIsNotNone(btn1)

        btn2 = buttons.find(id="btn_id_batch_stage1_validate")
        self.assertIsNotNone(btn2)
        self.assertTrue("btn-success" in btn2.attrs["class"])
        self.assertIn("disabled", btn2.attrs)

        btn3 = buttons.find(id="btn_id_batch_stage2_validate")
        self.assertIsNotNone(btn3)
        self.assertTrue("btn-secondary" in btn3.attrs["class"])
        self.assertNotIn("disabled", btn3.attrs)

    @tag("batch_form_2_test_batch_selection_stage_2_failed")
    def test_batch_selection_stage_2_failed(self):

        # we should see buttons Delete, stage 1 validate, stage 2 validate
        # stage 1 should be a btn-success and disabled, stage 2 validate should be btn-danger and disabled
        class MockTest(MockBiochemBatchForm):
            def is_batch_stage1_validated(self) -> bool | None:
                return True

            def is_batch_stage2_validated(self) -> bool | None:
                return False

        data={
            "batch_selection": 1
        }
        request = RequestFactory().get("/test/", data=data)

        # test for if the selection is "Test 1"
        response = form_biochem_batch2.get_batch_list(request, self.mission.pk, MockTest)
        soup = BeautifulSoup(response.content, 'html.parser')

        selection = soup.find(id="div_id_input_batch_selection")
        self.assertIsNotNone(selection)

        option = selection.find("option", selected=True)
        self.assertIsNotNone(option)
        self.assertEqual("Test 1", option.string)

        buttons = soup.find(id=form_biochem_batch2.BIOCHEM_BATCH_CONTROL_ROW_ID)
        self.assertIsNotNone(buttons)

        btn1 = buttons.find(id="btn_id_batch_delete")
        self.assertIsNotNone(btn1)

        btn2 = buttons.find(id="btn_id_batch_stage1_validate")
        self.assertIsNotNone(btn2)
        self.assertTrue("btn-success" in btn2.attrs["class"])
        self.assertIn("disabled", btn2.attrs)

        btn3 = buttons.find(id="btn_id_batch_stage2_validate")
        self.assertIsNotNone(btn3)
        self.assertTrue("btn-danger" in btn3.attrs["class"])
        self.assertIn("disabled", btn3.attrs)

    def test_batch_selection_stage_2_passed(self):

        # we should see buttons Delete, stage 1 validate, stage 2 validate, and the check-in button
        # stage 1 should be a btn-success and disabled, stage 2 validate should be btn-success and disabled
        class MockTest(MockBiochemBatchForm):
            def is_batch_stage1_validated(self) -> bool | None:
                return True

            def is_batch_stage2_validated(self) -> bool | None:
                return True

        data={
            "batch_selection": 1
        }
        request = RequestFactory().get("/test/", data=data)

        # test for if the selection is "Test 1"
        response = form_biochem_batch2.get_batch_list(request, self.mission.pk, MockTest)
        soup = BeautifulSoup(response.content, 'html.parser')

        selection = soup.find(id="div_id_input_batch_selection")
        self.assertIsNotNone(selection)

        option = selection.find("option", selected=True)
        self.assertIsNotNone(option)
        self.assertEqual("Test 1", option.string)

        buttons = soup.find(id=form_biochem_batch2.BIOCHEM_BATCH_CONTROL_ROW_ID)
        self.assertIsNotNone(buttons)

        btn1 = buttons.find(id="btn_id_batch_delete")
        self.assertIsNotNone(btn1)

        btn2 = buttons.find(id="btn_id_batch_stage1_validate")
        self.assertIsNotNone(btn2)
        self.assertTrue("btn-success" in btn2.attrs["class"])
        self.assertIn("disabled", btn2.attrs)

        btn3 = buttons.find(id="btn_id_batch_stage2_validate")
        self.assertIsNotNone(btn3)
        self.assertTrue("btn-success" in btn3.attrs["class"])
        self.assertIn("disabled", btn3.attrs)

        btn3 = buttons.find(id="btn_id_batch_checkin")
        self.assertIsNotNone(btn3)
        self.assertTrue("btn-secondary" in btn3.attrs["class"])


@tag("batch_form_2", "batch_form_2_discrete")
class TestBatchFormDiscrete(DartTestCase):

    def setUp(self):
        self.mission: core_models.Mission = MissionFactory(mission_descriptor='11DE25003')

    @patch('core.form_biochem_batch2.is_locked', return_value=True)
    def test_download_batch_func_lock_exception(self, mock_is_locked):
        # Test that an IOError is raised when the file is locked
        with self.assertRaises(IOError, msg="Expected IOError when file is locked"):
            form_biochem_batch2_discrete.download_batch_func(self.mission, 'upsonp')


@tag("batch_form_2", "batch_form_2_plankton")
class TestBatchFormPlankton(DartTestCase):

    def setUp(self):
        self.mission: core_models.Mission = MissionFactory(mission_descriptor='11DE25003')

    @patch('core.form_biochem_batch2.is_locked', return_value=True)
    def test_download_batch_func_lock_exception(self, mock_is_locked):
        # Test that an IOError is raised when the file is locked
        with self.assertRaises(IOError, msg="Expected IOError when file is locked"):
            form_biochem_batch2_plankton.download_batch_func(self.mission, 'upsonp')


# We're updating the form_biochem_batch class to use better, more readable practices
# everything below this is being kept for reference until the replacement tests for the
# new class is complete because we want to keep the same kinds of test for the new form
# but the code is complete different.
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
        bio_model = upload.get_model("BCDISCRETESTATNEDITS", bio_models.BcsD)
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
        bio_model = upload.get_model("BCPLANKTONSTATNEDITS", bio_models.BcsP)
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
    @patch('core.form_biochem_database.get_uploader')
    def test_validation2_proc_failure(self, mock_get_uploader, mock_connections):
        # Mock the cursor and its methods
        mock_cursor = MagicMock()
        mock_connections.__getitem__.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        batch_id = 123
        user = self.database_connection.uploader.upper()
        mock_get_uploader.return_value = user
        logger.debug(f"test user: {mock_get_uploader.return_value}")

        # Simulate validation failure
        mock_cursor.callfunc.side_effect = ['T', 'T', 'T', 'T', 'T', 'T', 'T']  # stn_pass_var, data_pass_var

        # Call the function
        form_biochem_plankton.validation2_proc(batch_id=batch_id)

        # Assertions
        logger.debug(mock_cursor.callfunc.__dict__)
        mock_cursor.callfunc.assert_any_call("BATCH_VALIDATION_PKG.CHECK_BATCH_MISSION_ERRORS", str, [batch_id, user])
        mock_cursor.callfunc.assert_any_call("BATCH_VALIDATION_PKG.CHECK_BATCH_EVENT_ERRORS", str, [batch_id, user])
        mock_cursor.callfunc.assert_any_call("BATCH_VALIDATION_PKG.CHECK_BATCH_PLANK_HEDR_ERRORS", str, [batch_id, user])
        mock_cursor.callfunc.assert_any_call("BATCH_VALIDATION_PKG.CHECK_BATCH_PLANK_GENERL_ERRS", str, [batch_id, user])
        mock_cursor.callfunc.assert_any_call("BATCH_VALIDATION_PKG.CHECK_BATCH_PLANK_DTAIL_ERRS", str, [batch_id, user])
        mock_cursor.callfunc.assert_any_call("BATCH_VALIDATION_PKG.CHECK_BATCH_PLANK_FREQ_ERRS", str, [batch_id, user])
        mock_cursor.callfunc.assert_any_call("BATCH_VALIDATION_PKG.CHECK_BATCH_PLANK_INDIV_ERRS", str, [batch_id, user])
