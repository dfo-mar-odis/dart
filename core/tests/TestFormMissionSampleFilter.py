from bs4 import BeautifulSoup
from crispy_forms.utils import render_crispy_form
from django.test import tag, RequestFactory
from django_pandas.io import read_frame

from config.tests.DartTestCase import DartTestCase
from core import form_mission_sample_filter
from core.form_mission_sample_filter import SampleFilterForm
from core import models as core_models
from core.tests import CoreFactoryFloor as core_factory

expected_card_name = 'test_form'
class MockFilterForm(SampleFilterForm):
    def get_samples_card_update_url(self):
        return "Test Samples List URL"

    def get_clear_filters_url(self):
        return "Test Clear Filters URL"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, card_name=expected_card_name, **kwargs)

@tag("forms", "filter_samples", "form_filter_samples")
class TestSampleFilterForm(DartTestCase):

    def setUp(self) -> None:
        self.form = MockFilterForm()
        self.samples_card_id = form_mission_sample_filter.SAMPLES_CARD_ID
        context = {
        }

        form_crispy = render_crispy_form(self.form, context=context)
        self.form_soup = BeautifulSoup(form_crispy, 'html.parser')

    def test_initial(self):
        # test that the form was initialized with the title
        title = self.form_soup.find(id=self.form.get_id_builder().get_card_title_id())
        self.assertEqual(title.string, "Sample Filter")

    def test_button_clear(self):
        # test that the card header has a button to clear filtered samples
        header = self.form_soup.find(id=self.form.get_id_builder().get_card_header_id())
        input = header.find('button', id=self.form.get_id_builder().get_button_clear_filters_id())
        self.assertIsNotNone(input)

    def test_hidden_mission_sample_type_input(self):
        # test that a hidden input field with the name 'mission_sample_type' exists in the body of the card
        body = self.form_soup.find(id=self.form.get_id_builder().get_card_body_id())
        input = body.find('input', id=self.form.get_id_builder().get_input_hidden_refresh_id())
        self.assertIsNotNone(input)

        attrs = input.attrs
        self.assertEqual(attrs['name'], 'refresh_samples')
        self.assertEqual(attrs['type'], 'hidden')

        # when a datatype, limit or flag is updated this element should make a request to update the visible samples
        self.assertEqual(attrs['hx-target'], f"#{self.samples_card_id}")
        self.assertEqual(attrs['hx-trigger'], 'reload_samples from:body')
        self.assertEqual(attrs['hx-swap'], 'outerHTML')
        self.assertEqual(attrs['hx-post'], self.form.get_samples_card_update_url())

    def test_event_input(self):
        # test that an input field with the name 'sample_id_start' exists in the body of the card
        body = self.form_soup.find(id=self.form.get_id_builder().get_card_body_id())
        input = body.find('select', id=self.form.get_id_builder().get_input_event_id())
        self.assertIsNotNone(input)

        attrs = input.attrs
        self.assertEqual(attrs['name'], 'event')

        # needs some HTMX calls to update the visible samples on the page
        self.assertEqual(attrs['hx-target'], f"#{self.samples_card_id}")
        self.assertEqual(attrs['hx-trigger'], "change")
        self.assertEqual(attrs['hx-swap'], 'outerHTML')
        self.assertEqual(attrs['hx-post'], self.form.get_samples_card_update_url())

    def test_sample_start_input(self):
        # test that an input field with the name 'sample_id_start' exists in the body of the card
        body = self.form_soup.find(id=self.form.get_id_builder().get_card_body_id())
        input = body.find('input', id=self.form.get_id_builder().get_input_sample_id_start_id())
        self.assertIsNotNone(input)

        attrs = input.attrs
        self.assertEqual(attrs['name'], 'sample_id_start')
        self.assertEqual(attrs['type'], 'number')

        # needs some HTMX calls to update the visible samples on the page
        self.assertEqual(attrs['hx-target'], f"#{self.samples_card_id}")
        self.assertEqual(attrs['hx-trigger'], "keyup changed delay:500ms")
        self.assertEqual(attrs['hx-swap'], 'outerHTML')
        self.assertEqual(attrs['hx-post'], self.form.get_samples_card_update_url())

    def test_sample_end_input(self):
        # test that an input field with the name 'sample_id_end' exists in the body of the card
        body = self.form_soup.find(id=self.form.get_id_builder().get_card_body_id())
        input = body.find('input', id=self.form.get_id_builder().get_input_sample_id_end_id())
        self.assertIsNotNone(input)

        attrs = input.attrs
        self.assertEqual(attrs['name'], 'sample_id_end')
        self.assertEqual(attrs['type'], 'number')

        # needs some HTMX calls to update the visible samples on the page
        self.assertEqual(attrs['hx-target'], f"#{self.samples_card_id}")
        self.assertEqual(attrs['hx-trigger'], "keyup changed delay:500ms")
        self.assertEqual(attrs['hx-swap'], 'outerHTML')
        self.assertEqual(attrs['hx-post'], self.form.get_samples_card_update_url())


@tag("forms", "filter_samples", "functions_filter_samples")
class TestMissionSampleFilterFunctions(DartTestCase):

    def setUp(self):
        pass

    def test_get_sample_card(self):
        # provided a card title, return a BeautifulSoup card that extends the core/partials/card_placeholder.html object
        expected_title = "Sample Title"
        card = form_mission_sample_filter.get_samples_card(expected_title)

        header = card.find(id=f'div_id_card_header_{form_mission_sample_filter.SAMPLES_CARD_NAME}')
        self.assertIsNotNone(header)

        title = card.find(id=f'div_id_card_title_{form_mission_sample_filter.SAMPLES_CARD_NAME}')
        self.assertEqual(title.string, "Sample Title")

        body = card.find(id=f'div_id_card_body_{form_mission_sample_filter.SAMPLES_CARD_NAME}')
        self.assertIsNotNone(body)
        self.assertEqual(body.attrs['class'], 'vertical-scrollbar')

    def test_clear_filters(self):
        # provided a form that extends a SampleFilterForm, the clear_filters function
        # adds htmx attributes to the card so when it's swapped on to the page it will call
        # a function to reload unfiltered samples.
        id_builder = MockFilterForm.get_id_builder_class()(expected_card_name)
        form = MockFilterForm()
        response = form_mission_sample_filter.clear_filters(form)

        test_card_soup = BeautifulSoup(response.content, 'html.parser')

        card = test_card_soup.find(id=id_builder.get_card_id())
        attrs = card.attrs
        self.assertEqual(attrs['hx-swap'], 'outerHTML')
        self.assertEqual(attrs['hx-swap-oob'], 'true')
        self.assertEqual(attrs['hx-trigger'], 'load')
        self.assertEqual(attrs['hx-target'], f'#{form_mission_sample_filter.SAMPLES_CARD_ID}')
        self.assertEqual(attrs['hx-get'], form.get_samples_card_update_url())

    def test_list_samples_empty_queryset(self):
        # provided an empty queryset list_samples will return an empty core/partials/card_placeholder.html card
        # as an HttpResponse with a "No Samples" Message
        expected_title = "Sample Title"
        queryset = core_models.Bottle.objects.none()
        test_card_soup = form_mission_sample_filter.list_samples(None, queryset, expected_title, '', None)

        card = test_card_soup.find(id=f"div_id_card_{form_mission_sample_filter.SAMPLES_CARD_NAME}")
        self.assertIsNotNone(card)

        title = test_card_soup.find(id=f"div_id_card_title_{form_mission_sample_filter.SAMPLES_CARD_NAME}")
        self.assertEqual(title.string, expected_title)

    def test_list_samples_not_empty_queryset_no_page(self):
        # provided a queryset and no 'page' in the request, list_samples will return a
        # core/partials/card_placeholder.html card as an HttpResponse containing a table created by the
        # process_samples_proc function

        event = core_factory.CTDEventFactory()
        core_factory.BottleFactory.create_batch(10, event=event)

        def fake_process_samples_proc(queryset, **kwargs):
            bottle_list = queryset.values(
                'bottle_id',
                'event__event_id'
            )

            df = read_frame(bottle_list)
            df.columns = ["Bottle", "Event"]

            html = df.to_html(index=False)
            return BeautifulSoup(html, 'html.parser')

        expected_title = "Sample Title"
        initial_queryset = core_models.Bottle.objects.filter(event=event)
        fake_request = RequestFactory().get('/some/path/')
        fake_delete_url = "/some/path/delete/"

        test_card_soup = form_mission_sample_filter.list_samples(fake_request, initial_queryset, expected_title, fake_delete_url, fake_process_samples_proc)

        card = test_card_soup.find(id=f"div_id_card_{form_mission_sample_filter.SAMPLES_CARD_NAME}")
        self.assertIsNotNone(card)

        title = test_card_soup.find(id=f"div_id_card_title_{form_mission_sample_filter.SAMPLES_CARD_NAME}")
        self.assertEqual(title.string, expected_title)

    @tag("test_list_samples_not_empty_queryset_page")
    def test_list_samples_not_empty_queryset_page(self):
        # provided a queryset and 'page' in the request, list_samples will return a
        # core/partials/card_placeholder.html card as an HttpResponse containing table rows from the table
        # created by the process_samples_proc function

        event = core_factory.CTDEventFactory()
        # we need more than 100 elements for the paging to take effect, otherwise we'll get nothing back.
        core_factory.BottleFactory.create_batch(150, event=event)

        def fake_process_samples_proc(queryset, **kwargs):
            bottle_list = queryset.values(
                'bottle_id',
                'event__event_id'
            )

            df = read_frame(bottle_list)
            df.columns = ["Bottle", "Event"]

            html = df.to_html(index=False)
            return BeautifulSoup(html, 'html.parser')

        # provided an empty queryset list_samples will return an empty core/partials/card_placeholder.html card
        # as an HttpResponse with a "No Samples" Message
        expected_title = "Sample Title"
        initial_queryset = core_models.Bottle.objects.filter(event=event)
        fake_request = RequestFactory().get('/some/path/', {'page': 1})
        fake_delete_url = "/some/path/delete/"

        # This should return a list of table elements
        test_card_soup = form_mission_sample_filter.list_samples(fake_request, initial_queryset, expected_title, fake_delete_url, fake_process_samples_proc)
        # trs = test_card_soup.find_all('tr')
        self.assertEqual(len(test_card_soup), 50)