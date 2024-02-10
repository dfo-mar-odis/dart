from bs4 import BeautifulSoup
from django.test import tag, Client
from django.urls import reverse

import settingsdb.models
from core import models
from core.form_event_details import EventForm
from core.tests import CoreFactoryFloor as core_factory
from dart.tests.DartTestCase import DartTestCase


@tag('forms', 'form_trip_event')
class TestTripEventForm(DartTestCase):
    fixtures = ['biochem_fixtures', 'default_settings_fixtures']

    def setUp(self) -> None:
        self.client = Client()
        self.trip = core_factory.TripFactory()

    @tag('form_trip_event_test_entry_point_get')
    def test_entry_point_get(self):
        # provided a trip the add button on the Event Detail card should return a form to be swapped
        # on to the card body.
        # The add button points to the event card using hx-target, so the response to the add event
        # url should be a full card
        url = reverse("core:form_event_add_event", args=('default', self.trip.pk))
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, 'html.parser')
        card_div = soup.find(recursive=False)
        self.assertIsNotNone(card_div)

        form = soup.find(id="div_event_event_details_content_id")
        self.assertIsNotNone(form.find("form"))

    @tag('form_trip_event_test_entry_point_post')
    def test_entry_point_post(self):
        # provided details for an event using the add event url should create and event
        # and pass back the event edit form and the Action and Attachment creation forms
        # as defined in the 'core/partials/event_edit_form.html' template

        station = settingsdb.models.GlobalStation.objects.get_or_create(name="HL_02")[0]
        instrument = core_factory.CTDInstrumentFactory()
        kwargs = {
            'trip': self.trip.pk,
            'event_id': 1,
            'global_station': station.pk,
            'instrument': instrument.pk,
            'sample_id': 1,
            'end_sample_id': 10
        }

        url = reverse("core:form_event_add_event", args=('default', self.trip.pk))
        response = self.client.post(url, kwargs)

        # make sure the event was created
        # using *.get(event_id=1) will throw a DoesNotExist exception if it wasn't created
        new_event = models.Event.objects.using('default').get(trip=self.trip, event_id=1)
        new_station = models.Station.objects.using('default').get(name__iexact=station.name)
        self.assertEquals(new_event.station.pk, new_station.pk)
        self.assertEquals(new_event.instrument.pk, instrument.pk)
        self.assertEquals(new_event.sample_id, kwargs['sample_id'])
        self.assertEquals(new_event.end_sample_id, kwargs['end_sample_id'])

        soup = BeautifulSoup(response.content, 'html.parser')

        event_edit_form = soup.find(id="event_form_id")
        self.assertIsNotNone(event_edit_form)
        self.assertEquals(event_edit_form.name, 'form')

        action_form = soup.find(id="actions_form_id")
        self.assertIsNotNone(action_form)
        self.assertEquals(action_form.name, 'form')

        attachment_form = soup.find(id="attachments_form_id")
        self.assertIsNotNone(attachment_form)
        self.assertEquals(attachment_form.name, 'form')

    @tag('form_trip_event_test_edit_event_post')
    def test_edit_event_post(self):
        # provided an existing event the edit event url and a set of changed args should update the event

        event = core_factory.CTDEventFactory(sample_id=1, end_sample_id=10)
        station = settingsdb.models.GlobalStation.objects.get_or_create(name="HL_02")[0]
        kwargs = {
            'trip': event.trip.pk,
            'event_id': event.event_id,
            'global_station': station.pk,
            'instrument': event.instrument.pk,
            'sample_id': 20,
            'end_sample_id': 400
        }
        url = reverse("core:form_event_edit_event", args=('default', event.pk))
        response = self.client.post(url, kwargs)

        edited_event = models.Event.objects.using('default').get(pk=event.pk)

        self.assertEquals(edited_event.sample_id, kwargs['sample_id'])
        self.assertEquals(edited_event.end_sample_id, kwargs['end_sample_id'])
        new_station = models.Station.objects.using('default').get(name__iexact=station.name)
        self.assertEquals(edited_event.station.pk, new_station.pk)

    @tag('form_trip_event_test_delete_event_post')
    def test_delete_event_post(self):
        # provided an event id the delete event url should remove an event from the database, return an empty
        # EventDetail card and contain an Hx-Trigger: event_updated action to notify listening objects they
        # should update their event lists.
        trip = core_factory.TripFactory()
        event = core_factory.CTDEventFactory(trip=trip)

        self.assertTrue(models.Event.objects.using('default').filter(pk=event.pk).exists())

        url = reverse("core:form_event_delete_event", args=('default', event.pk))
        response = self.client.post(url)

        self.assertFalse(models.Event.objects.using('default').filter(pk=event.pk).exists())

        soup = BeautifulSoup(response.content, "html.parser")
        new_detail_card = soup.find(id="div_id_card_event_details")
        self.assertIsNotNone(new_detail_card)
        self.assertIn('hx-swap-oob', new_detail_card.attrs)

        self.assertIn('Hx-Trigger', response.headers)
        self.assertEquals(response.headers['Hx-Trigger'], 'event_updated')

        # we'll also return a table and table row using an hx-swap-oob to delete the event from the selection table
        event_row = soup.find(id=f"event-{event.pk}")
        self.assertIn('hx-swap', event_row.attrs)
        self.assertEquals(event_row.attrs['hx-swap'], 'delete')

    @tag('form_trip_event_test_add_action_post')
    def test_add_action_post(self):
        # provided an existing event and args the add action url should add an action to the event
        # and return an empty action form with a table containing the new action as defined in the
        # 'core/partials/event_edit_form.html' and 'core/partials/table_action.html' templates

        event = core_factory.CTDEventFactoryBlank()
        action_vars = core_factory.ActionFactory.build()
        kwargs = {
            'event': event.pk,
            'date_time': action_vars.date_time,
            'latitude': action_vars.latitude,
            'longitude': action_vars.longitude,
            'type': action_vars.type
        }

        url = reverse("core:form_event_add_action", args=('default', event.pk))
        response = self.client.post(url, kwargs)

        action = models.Action.objects.using('default').get(event=event, date_time=action_vars.date_time)
        self.assertEquals(action.latitude, action_vars.latitude)
        self.assertEquals(action.longitude, action_vars.longitude)
        self.assertEquals(action.type, action_vars.type)

        soup = BeautifulSoup(response.content, 'html.parser')

        action_form = soup.find(id="actions_form_id")
        self.assertIsNotNone(action_form)
        self.assertEquals(action_form.name, 'form')

        action_table = soup.find(id="tbody_id_action_table")  # should be the tbody tag
        self.assertIsNotNone(action_table)
        self.assertEquals(action_table.name, 'tbody')

        # tbody should contain one tr tag
        tr_tags = action_table.find_all('tr')
        self.assertEquals(len(tr_tags), 1)

    @tag('form_trip_event_test_edit_action_get')
    def test_edit_action_get(self):
        # the 'core/partials/table_action.html' template defines several buttons for an action row
        # the edit button calls the edit action using the get method which populates the action form
        # with the data from the action row
        event = core_factory.CTDEventFactory()
        action = event.actions.first()

        url = reverse("core:form_event_edit_action", args=('default', action.pk))
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, "html.parser")
        action_form = soup.find(id="actions_form_id")
        self.assertIsNotNone(action_form)
        self.assertEquals(action_form.name, 'form')

        type_select = action_form.find(id="id_action_type_field")
        self.assertIsNotNone(type_select)
        self.assertEquals(type_select.name, 'select')

        type_select_value = type_select.find(selected=True)
        self.assertEquals(int(type_select_value.attrs['value']), action.type)

        # The action form should also have an hx-post with the edit action url
        submit = action_form.find('button', attrs={"name": "add_action"})
        self.assertIsNotNone(submit)
        self.assertIn("hx-post", submit.attrs)
        self.assertEquals(submit.attrs['hx-post'], url)

    @tag('form_trip_event_test_edit_action_post')
    def test_edit_action_post(self):
        # provided an existing action and updated arguments calling the edit action url using the post method
        # should update the action in the database and return a blank Action form and a new table to replace
        # the existing action in the table as defined by the 'core/partials/table_action.html' template

        event = core_factory.CTDEventFactory()
        deployed_action = event.actions.get(type=models.ActionType.deployed)

        kwargs = {
            'event': event.pk,
            'date_time': deployed_action.date_time,
            'latitude': 42.0,
            'longitude': -65.5,
            'type': deployed_action.type
        }

        url = reverse("core:form_event_edit_action", args=('default', deployed_action.pk))
        response = self.client.post(url, kwargs)

        updated_action = models.Action.objects.using('default').get(pk=deployed_action.pk)
        self.assertEquals(updated_action.latitude, kwargs['latitude'])
        self.assertEquals(updated_action.longitude, kwargs['longitude'])

        soup = BeautifulSoup(response.content, "html.parser")
        action_form = soup.find(id="actions_form_id")
        self.assertIsNotNone(action_form)

        type_field = action_form.find(id="id_action_type_field")
        self.assertIsNotNone(type_field)

        selected_type = type_field.find(selected=True)
        self.assertIsNotNone(selected_type)
        self.assertEquals(selected_type.attrs['value'], "")

        # because of how HTMX handles tables the
        replacement_row = soup.find(id=f"action-{ deployed_action.pk }")
        self.assertIsNotNone(replacement_row)
        self.assertEquals(replacement_row.name, 'tr')
        self.assertIn('hx-swap-oob', replacement_row.attrs)

    @tag('form_trip_event_test_delete_action_post')
    def test_delete_action_post(self):
        # provided an event and an action id, a posted delete action url should remove the action from the database
        # the intent is for the 'core/partials/table_action.html' template to use the hx-delete method
        # to call this url so the delete function should return nothing
        event = core_factory.CTDEventFactory()
        deployed = event.actions.get(type=models.ActionType.deployed)

        url = reverse("core:form_event_delete_action", args=('default', deployed.pk))
        response = self.client.delete(url)

        deployed = event.actions.filter(pk=deployed.pk)
        self.assertFalse(deployed.exists())

        soup = BeautifulSoup(response.content, "html.parser")
        self.assertEquals(soup.prettify(), '')

    @tag('form_trip_event_test_form_event_list_action_get')
    def test_form_event_list_action_get(self):
        # calling the list actions url with an event id should return table tr elements containing details for
        # the actions attached to the provided event

        event = core_factory.CTDEventFactory()
        url = reverse("core:form_event_list_action", args=('default', event.pk))

        response = self.client.get(url)
        soup = BeautifulSoup(response.content, "html.parser")

        action_table = soup.find(id='action_table_id')
        self.assertIsNotNone(action_table)

        action_table_body = action_table.find('tbody')
        trs = action_table_body.find_all('tr')
        self.assertEquals(len(trs), event.actions.count())

    @tag('form_trip_event_test_form_event_list_action_get_editable')
    def test_form_event_list_action_get_editable(self):
        # calling the list actions url with an event id should return table tr elements containing details for
        # the actions attached to the provided event. In the case where an event was manually created, as opposed
        # to being loaded from an elog file, the row should contain an edit and a delete button

        event = core_factory.CTDEventFactory()
        url = reverse("core:form_event_list_action", args=('default', event.pk, 'true'))

        response = self.client.get(url)
        soup = BeautifulSoup(response.content, "html.parser")

        action_table = soup.find(id='action_table_id')
        self.assertIsNotNone(action_table)

        action_table_body = action_table.find('tbody')
        trs = action_table_body.find_all('tr')
        self.assertEquals(len(trs), event.actions.count())

        for tr in trs:
            action_id = tr.attrs['id'].replace('action-', '')
            edit_url = reverse("core:form_event_edit_action", args=('default', action_id))

            button = tr.find('button', attrs={'name': 'edit_action'})
            self.assertIn('hx-get', button.attrs)
            self.assertEquals(button.attrs['hx-get'], edit_url)

            delete_url = reverse("core:form_event_delete_action", args=('default', action_id))

            button = tr.find('button', attrs={'name': 'delete_action'})
            self.assertIn('hx-delete', button.attrs)
            self.assertEquals(button.attrs['hx-delete'], delete_url)

    @tag('form_trip_event_test_add_attachment_post')
    def test_add_attachment_post(self):
        # provided an existing event and args the add attachment url should add an attachment to the event
        # and return an empty attachment form with a table containing the new attachment as defined in the
        # 'core/partials/event_edit_form.html' and 'core/partials/table_attachment.html' templates

        event = core_factory.CTDEventFactory()
        attachment = core_factory.AttachmentFactory()
        kwargs = {
            "event": event.pk,
            "name": attachment.name
        }

        url = reverse("core:form_event_add_attachment", args=('default', event.pk))
        response = self.client.post(url, kwargs)

        soup = BeautifulSoup(response.content, "html.parser")
        attachment_form = soup.find(id="attachments_form_id")
        self.assertIsNotNone(attachment_form)
        attachment_text = attachment_form.find(id="id_attachment_name_field")
        self.assertEquals(attachment_text.text, "")

    @tag('form_trip_event_test_edit_attachment_get')
    def test_edit_attachment_get(self):
        # the 'core/partials/table_attachments.html' template defines several buttons for an attachment row
        # the edit button calls the edit attachment url using the get method which populates the attachment form
        # with the data from the attachment row
        event = core_factory.CTDEventFactory()
        attachment = core_factory.AttachmentFactory(event=event)

        url = reverse("core:form_event_edit_attachment", args=('default', attachment.pk))
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, "html.parser")
        attachment_form = soup.find(id="attachments_form_id")
        self.assertIsNotNone(attachment_form)
        self.assertEquals(attachment_form.name, 'form')

        attachment_name = attachment_form.find(id="id_attachment_name_field")
        self.assertIsNotNone(attachment_name)
        self.assertEquals(attachment_name.name, 'input')
        self.assertEquals(attachment_name.attrs['value'], attachment.name)

        # The action form should also have an hx-post with the edit action url
        submit = attachment_form.find('button', attrs={"name": "add_attachment"})
        self.assertIsNotNone(submit)
        self.assertIn("hx-post", submit.attrs)
        self.assertEquals(submit.attrs['hx-post'], url)

    @tag('form_trip_event_test_edit_attachment_post')
    def test_edit_attachment_post(self):
        # provided an existing attachment and updated arguments calling the edit attachment url using the post method
        # should update the attachment in the database and return a blank Attachment form and a new table to replace
        # the existing attachment in the table as defined by the 'core/partials/table_attachment.html' template

        event = core_factory.CTDEventFactory()
        attachment = core_factory.AttachmentFactory(event=event)

        kwargs = {
            'event': event.pk,
            'name': 'Fake_attachment_name'
        }

        url = reverse("core:form_event_edit_attachment", args=('default', attachment.pk))
        response = self.client.post(url, kwargs)

        updated_attachment = models.Attachment.objects.using('default').get(pk=attachment.pk)
        self.assertEquals(updated_attachment.name, kwargs['name'])

        soup = BeautifulSoup(response.content, "html.parser")
        action_form = soup.find(id="attachments_form_id")
        self.assertIsNotNone(action_form)

        name_field = action_form.find(id="id_attachment_name_field")
        self.assertIsNotNone(name_field)
        self.assertNotIn('value', name_field.attrs)

        # because of how HTMX handles tables the
        replacement_row = soup.find(id=f"attachment-{ attachment.pk }")
        self.assertIsNotNone(replacement_row)
        self.assertEquals(replacement_row.name, 'tr')
        self.assertIn('hx-swap-oob', replacement_row.attrs)

    @tag('form_trip_event_test_delete_attachment_post')
    def test_delete_attachment_post(self):
        # provided an attachment belonging to an event the delete attachment url should remove the attachment from
        # the database. The intention is for the 'core/partials/table_attachment.html' to call the url with
        # hx-delete so nothing should be returned from the function
        event = core_factory.CTDEventFactory()
        attachment = core_factory.AttachmentFactory(event=event)

        self.assertTrue(event.attachments.filter(pk=attachment.pk).exists())

        url = reverse("core:form_event_delete_attachment", args=('default', attachment.pk))
        response = self.client.delete(url)

        self.assertFalse(event.attachments.filter(pk=attachment.pk).exists())

        soup = BeautifulSoup(response.content, "html.parser")
        self.assertEquals(soup.prettify(), '')

    @tag('form_trip_event_list_attachment_get')
    def test_list_attachment_get(self):
        # provided and event the get request using the list attachments url should return a table as outlined
        # in the 'core/partials/table_attachments.html' template

        event = core_factory.CTDEventFactory()
        attachment = core_factory.AttachmentFactory(event=event)

        url = reverse("core:form_event_list_attachment", args=('default', event.pk))
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, "html.parser")

        att_table = soup.find(id='attachment_table_id')
        self.assertIsNotNone(att_table)

        att_table_body = att_table.find('tbody')
        trs = att_table_body.find_all('tr')
        self.assertEquals(len(trs), event.attachments.count())

    @tag('form_trip_event_list_attachment_get_editable')
    def test_list_attachment_get_editable(self):
        # provided and event the get request using the list attachments url should return a table as outlined
        # in the 'core/partials/table_attachments.html' template. If editable, the table rows should contain
        # two buttons, one to edit the attachment, one to delete the attachment
        event = core_factory.CTDEventFactory()
        attachment = core_factory.AttachmentFactory(event=event)

        url = reverse("core:form_event_list_attachment", args=('default', event.pk, "True"))
        response = self.client.get(url)

        soup = BeautifulSoup(response.content, "html.parser")

        att_table = soup.find(id='attachment_table_id')
        self.assertIsNotNone(att_table)

        att_table_body = att_table.find('tbody')
        trs = att_table_body.find_all('tr')
        self.assertEquals(len(trs), event.attachments.count())

        for tr in trs:
            attachment_id = tr.attrs['id'].replace('attachment-', '')
            edit_url = reverse("core:form_event_edit_attachment", args=('default', attachment_id))

            button = tr.find('button', attrs={'name': 'edit_attachment'})
            self.assertIn('hx-get', button.attrs)
            self.assertEquals(button.attrs['hx-get'], edit_url)

            delete_url = reverse("core:form_event_delete_attachment", args=('default', attachment_id))

            button = tr.find('button', attrs={'name': 'delete_attachment'})
            self.assertIn('hx-delete', button.attrs)
            self.assertEquals(button.attrs['hx-delete'], delete_url)

    @tag("form_trip_event_test_global_stations")
    def test_global_stations(self):
        # when creating a new event the stations dropdown should be populated with stations from
        # the GlobalStation model

        trip = core_factory.TripFactory()
        event_form = EventForm(database='default', initial={'trip': trip.pk})
        # we have to chop off the first and last element of the choice list which will be 'none' and the 'new'
        stations = event_form.fields['global_station'].choices[1:-1]
        station_names = [station[1] for station in stations]
        global_stations = settingsdb.models.GlobalStation.objects.all()

        for station in global_stations:
            self.assertIn(station, station_names)

    @tag("form_trip_event_test_global_stations_save")
    def test_global_stations_save(self):
        # when saving an Event form the selected station will be a global station, the station should be copied to
        # the core.models.station table if it doesn't already exist and then referenced from the event

        global_station = settingsdb.models.GlobalStation.objects.get(name__iexact='hl_02')

        trip = core_factory.TripFactory()
        instrument = core_factory.InstrumentFactory(type=models.InstrumentType.ctd)
        event_data = {
            'trip': trip.pk,
            'event_id': 1,
            'global_station': global_station.pk,
            'instrument': instrument.pk,
            'sample_id': 1,
            'end_sample_id': 5,
        }
        event_form = EventForm(database='default', data=event_data)

        self.assertFalse(models.Station.objects.using('default').filter(name=global_station.name).exists())
        self.assertTrue(event_form.is_valid())
        event_form.save()
        self.assertTrue(models.Station.objects.using('default').filter(name=global_station.name).exists())

    @tag("form_trip_event_test_global_stations_delete")
    def test_add_station_get(self):
        pass