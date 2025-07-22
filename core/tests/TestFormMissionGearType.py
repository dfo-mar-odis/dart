from bs4 import BeautifulSoup
from crispy_forms.utils import render_crispy_form
from django.test import tag, RequestFactory
from django.urls import reverse

from config.tests.DartTestCase import DartTestCase

from core import form_mission_gear_type, form_mission_sample_filter
from core import models as core_models
from core.tests import CoreFactoryFloor as core_factory


@tag("forms", "mission_gear_type", "form_filter_gear_type")
class TestMissionGearTypeFilter(DartTestCase):

    def setUp(self) -> None:

        mission = core_factory.MissionFactory.create(name='Test Mission')
        event = core_factory.CTDEventFactory(mission=mission)
        core_factory.BottleFactory.create_batch(10, event=event)

        self.form = form_mission_gear_type.GearTypeFilterForm(mission_id=mission.pk, instrument_type=event.instrument.type)
        self.expected_url = self.form.get_samples_card_update_url()

        form_crispy = render_crispy_form(self.form)
        self.form_soup = BeautifulSoup(form_crispy, 'html.parser')

    def test_button_clear(self):
        # test that the card header has a button to clear filtered samples
        header = self.form_soup.find(id=self.form.get_id_builder().get_card_header_id())
        input = header.find('button', id=self.form.get_id_builder().get_button_clear_filters_id())
        self.assertIsNotNone(input)

        attrs = input.attrs
        self.assertEqual(attrs['hx-get'], self.form.get_clear_filters_url())

    def test_hidden_mission_sample_type_input(self):
        # test that a hidden input field with the name 'mission_sample_type' exists in the body of the card
        body = self.form_soup.find(id=self.form.get_id_builder().get_card_body_id())
        input = body.find('input', id=self.form.get_id_builder().get_input_hidden_refresh_id())
        self.assertIsNotNone(input)

        attrs = input.attrs
        self.assertEqual(attrs['name'], 'refresh_samples')
        self.assertEqual(attrs['type'], 'hidden')

        # when a datatype, limit or flag is updated this element should make a request to update the visible samples
        self.assertEqual(attrs['hx-post'], self.expected_url)

    def test_sample_start_input(self):
        # test that an input field with the name 'sample_id_start' exists in the body of the card
        body = self.form_soup.find(id=self.form.get_id_builder().get_card_body_id())
        input = body.find('input', id=self.form.get_id_builder().get_input_sample_id_start_id())
        self.assertIsNotNone(input)

        attrs = input.attrs
        self.assertEqual(attrs['name'], 'sample_id_start')
        self.assertEqual(attrs['type'], 'number')

        # needs some HTMX calls to update the visible samples on the page
        self.assertEqual(attrs['hx-post'], self.expected_url)

    def test_sample_end_input(self):
        # test that an input field with the name 'sample_id_end' exists in the body of the card
        body = self.form_soup.find(id=self.form.get_id_builder().get_card_body_id())
        input = body.find('input', id=self.form.get_id_builder().get_input_sample_id_end_id())
        self.assertIsNotNone(input)

        attrs = input.attrs
        self.assertEqual(attrs['name'], 'sample_id_end')
        self.assertEqual(attrs['type'], 'number')

        # needs some HTMX calls to update the visible samples on the page
        self.assertEqual(attrs['hx-post'], self.expected_url)

    def test_select_gear_type_description(self):
        # test that an input to filter samples based on their current gear type exists
        body = self.form_soup.find(id=self.form.get_id_builder().get_card_body_id())
        input = body.find('select', id=self.form.get_id_builder().get_select_gear_type_description_id())
        self.assertIsNotNone(input)

        attrs = input.attrs
        self.assertEqual(attrs['name'], 'filter_gear_type_description')

        # needs some HTMX calls to update the visible samples on the page
        self.assertEqual(attrs['hx-post'], self.expected_url)


@tag("forms", "mission_gear_type", "gear_type_selection")
class TestGearTypeForm(DartTestCase):
    def setUp(self) -> None:
        self.mission = core_factory.MissionFactory.create(name='Test Mission')

        self.event = core_factory.CTDEventFactory(mission=self.mission)
        core_factory.BottleFactory.create_batch(10, event=self.event)
        self.instrument_type = self.event.instrument.type

        self.expected_update_url = reverse('core:form_mission_gear_type_update_gear_type', args=[self.mission.pk, self.instrument_type])
        self.expected_gear_form_url = reverse('core:form_mission_gear_type_filter_datatype', args=[self.mission.pk, self.instrument_type])

        self.form = form_mission_gear_type.GearTypeSelectionForm(mission_id=self.mission.pk, instrument_type=self.instrument_type)
        crispy = render_crispy_form(self.form)
        self.soup = BeautifulSoup(crispy, 'html.parser')

    def test_initial(self):
        id_builder = self.form.get_id_builder()

        card = self.soup.find(id=id_builder.get_card_id())
        self.assertIsNotNone(card)

        header = card.find(id=id_builder.get_card_header_id())

        title = card.find(id=id_builder.get_card_title_id())
        self.assertIsNotNone(title)
        self.assertEqual(title.string, "Gear Type Selection")

        apply_button = header.find(id=id_builder.get_button_apply_id())
        self.assertIsNotNone(apply_button)

        attrs = apply_button.attrs
        self.assertEqual(attrs['hx-swap'], 'none')
        self.assertEqual(attrs['hx-post'], self.expected_update_url)


    def test_gear_code_input(self):
        id_builder = self.form.get_id_builder()
        card_body = self.soup.find(id=id_builder.get_card_body_id())
        gear_code_field = card_body.find(id=id_builder.get_input_gear_code_id())
        self.assertIsNotNone(gear_code_field)

        attrs = gear_code_field.attrs
        self.assertEqual(attrs['name'], 'gear_type_code')
        self.assertEqual(attrs['type'], 'number')

        self.assertEqual(attrs['hx-trigger'], 'keyup changed delay:500ms')
        self.assertEqual(attrs['hx-swap'], 'none')
        self.assertEqual(attrs['hx-get'], self.expected_gear_form_url)

    def test_gear_code_description(self):
        id_builder = self.form.get_id_builder()
        card_body = self.soup.find(id=id_builder.get_card_body_id())
        gear_description_field = card_body.find(id=id_builder.get_select_gear_description_id())
        self.assertIsNotNone(gear_description_field)

        attrs = gear_description_field.attrs
        self.assertEqual(attrs['name'], 'gear_type_description')

        self.assertEqual(attrs['hx-swap'], 'none')
        self.assertEqual(attrs['hx-get'], self.expected_gear_form_url)
        self.assertEqual(attrs['hx-select-oob'], f'#{id_builder.get_input_gear_code_id()}')

    def test_update_gear_type_function_no_filter(self):
        bottles = core_models.Bottle.objects.filter(event=self.event)
        for bottle in bottles:
            self.assertEqual(bottle.gear_type.pk, 90000002)

        # 9000001 is a pressure gear type
        new_gear = 90000001
        request = RequestFactory().post(self.expected_update_url, {'gear_type_code': new_gear})

        response = form_mission_gear_type.update_gear_type_samples(request, self.mission.pk, self.instrument_type)

        # this shouldn't actually return anything, but it should have a HX-Trigger = reload_samples header
        self.assertIn('HX-Trigger', response.headers)
        self.assertEqual(response.headers['HX-Trigger'], 'reload_samples')

        bottles = core_models.Bottle.objects.filter(event=self.event)
        for bottle in bottles:
            self.assertEqual(bottle.gear_type.pk, new_gear)

    def test_update_gear_type_function_filter_sample_id(self):
        bottles = core_models.Bottle.objects.filter(event=self.event)
        first_bottle_id = bottles[0].bottle_id
        for bottle in bottles:
            self.assertEqual(bottle.gear_type.pk, 90000002)

        # 9000001 is a pressure gear type
        new_gear = 90000001
        request = RequestFactory().post(self.expected_update_url, {'sample_id_start': first_bottle_id, 'gear_type_code': new_gear})

        response = form_mission_gear_type.update_gear_type_samples(request, self.mission.pk, self.instrument_type)

        # this shouldn't actually return anything, but it should have a HX-Trigger = reload_samples header
        self.assertIn('HX-Trigger', response.headers)
        self.assertEqual(response.headers['HX-Trigger'], 'reload_samples')

        first_bottle = core_models.Bottle.objects.get(bottle_id=first_bottle_id)
        self.assertEqual(first_bottle.gear_type.pk, new_gear)

        bottles = core_models.Bottle.objects.filter(event=self.event).exclude(bottle_id=first_bottle_id)
        for bottle in bottles:
            self.assertEqual(bottle.gear_type.pk, 90000002)


@tag("forms", "mission_gear_type", "mission_gear_type_functions")
class TestMissionGearTypeFunctions(DartTestCase):

    def setUp(self):
        pass

    def test_empty_mission(self):
        # when a mission contains no events, the list_samples function should return the Samples card with a
        # "No Samples Found" message
        mission = core_factory.MissionFactory.create(name="EmptyMission001")
        request = RequestFactory().get('fake/url/')

        # testing with CTD events
        instrument_type = core_models.InstrumentType.ctd
        response = form_mission_gear_type.list_samples(request, mission.pk, instrument_type)

        soup = BeautifulSoup(response.content, 'html.parser')
        card = soup.find(id=f"div_id_card_{form_mission_sample_filter.SAMPLES_CARD_NAME}")
        self.assertIsNotNone(card)

        title = card.find(id=f"div_id_card_title_{form_mission_sample_filter.SAMPLES_CARD_NAME}")
        self.assertIsNotNone(title)
        self.assertEqual(title.string, 'Samples')

    def test_mission_ctd_samples(self):
        instrument_type = core_models.InstrumentType.ctd
        ctd_mission = core_factory.MissionFactory.create(name="TestMission001")
        for event_id in range(1, 5):
            event = core_factory.CTDEventFactory.create(mission=ctd_mission, event_id=event_id)
            core_factory.BottleFactory.create_batch(12, event=event)

        request = RequestFactory().get('fake/url/')

        # testing with CTD events
        response = form_mission_gear_type.list_samples(request, ctd_mission.pk, core_models.InstrumentType.ctd)

        soup = BeautifulSoup(response.content, 'html.parser')
        card = soup.find(id=f"div_id_card_{form_mission_sample_filter.SAMPLES_CARD_NAME}")

        # The card header should contain a delete button
        btn_delete = card.find(id=f"btn_id_delete_samples_{form_mission_sample_filter.SAMPLES_CARD_NAME}")
        self.assertIsNotNone(btn_delete)

        url = reverse('core:form_gear_type_delete_samples', args=[ctd_mission.pk, instrument_type])
        attrs = btn_delete.attrs
        self.assertEqual(attrs['hx-post'], url)

    @tag('test_mission_net_samples')
    def test_mission_net_samples(self):
        instrument_type = core_models.InstrumentType.net
        net_mission = core_factory.MissionFactory.create(name="TestMission002")
        for event_id in range(1, 5):
            event = core_factory.NetEventFactory.create(mission=net_mission, event_id=event_id)
            core_factory.BottleFactory.create(event=event)

        request = RequestFactory().get('fake/url/')

        # testing with NET events
        response = form_mission_gear_type.list_samples(request, net_mission.pk, instrument_type)

        soup = BeautifulSoup(response.content, 'html.parser')
        card = soup.find(id=f"div_id_card_{form_mission_sample_filter.SAMPLES_CARD_NAME}")

        # The card header should contain a delete button
        btn_delete = card.find(id=f"btn_id_delete_samples_{form_mission_sample_filter.SAMPLES_CARD_NAME}")
        self.assertIsNotNone(btn_delete)

        url = reverse('core:form_gear_type_delete_samples', args=[net_mission.pk, instrument_type])
        attrs = btn_delete.attrs
        self.assertEqual(attrs['hx-post'], url)

        # if this is a net mission the Samples Card should also contain a "load volumes" button
        # initially the load volumes URL should be called as a get request. It'll then return a websocket
        # alert that should be swapped onto the Samples card header.
        btn_volumes = card.find(id=f"btn_id_load_volumes_{form_mission_sample_filter.SAMPLES_CARD_NAME}")
        self.assertIsNotNone(btn_volumes)

        url = reverse('core:form_gear_type_load_volume', args=[net_mission.pk])
        attrs = btn_volumes.attrs
        self.assertEqual(attrs['hx-get'], url)
        self.assertEqual(attrs['hx-swap'], "none")
