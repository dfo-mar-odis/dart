from bs4 import BeautifulSoup
from crispy_forms.bootstrap import StrictButton
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Row, Layout, Field, Hidden, Submit
from django import forms
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _
from django.urls import path, reverse

from config.utils import load_svg
from settingsdb.models import SampleFileType, SampleTypeVariable
from settingsdb import models

class SampleVariablesForm(forms.ModelForm):

    class Meta:
        model = SampleTypeVariable
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'sample_type' in self.data:
            sample_type_id = self.data.get('sample_type')
        elif 'sample_type' in self.initial:
            sample_type_id = self.initial['sample_type']

        target_id = self.instance.pk if self.instance.pk else 0
        url = reverse('settingsdb:form_sample_file_variable_validate', args=[sample_type_id, target_id])
        target = f"#div_id_sample_card_{sample_type_id}_subform"

        submit_attrs = {
            "title": _("Update Column Details") if target_id == 0 else _("Add Column Details"),
            "hx-post": url,
            "hx-target": target
        }

        submit_icon = load_svg("check-square")
        submit = StrictButton(submit_icon, css_class="btn btn-sm btn-primary", **submit_attrs)

        clear_attrs = {
            "title": _("Cancel"),
            "hx-get": reverse('settingsdb:form_sample_file_variable_validate', args=[sample_type_id, 0]),
            "hx-target": target
        }
        clear_icon = load_svg("x-square")
        clear = StrictButton(clear_icon, css_class="btn btn-sm btn-secondary", **clear_attrs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Hidden("sample_type", sample_type_id),
            Row(
                Column(Field('name')),
                Column(Field('value_field')),
                Column(Field('flag_field')),
                Column(Field('limit_field')),
                Column(Field('datatype')),
            ),
            Row(
                Column(
                    submit,
                    clear,
                    css_class="col-auto"
                ),
            )
        )

class SampleFileTypeForm(forms.ModelForm):

    class Meta:
        model = SampleFileType
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        key = self.instance.pk if self.instance.pk else 0
        submit_id = str(self.instance.pk if self.instance.pk else "new")
        submit_attrs = {
            "title": "Add Configuration" if key == 0 else "Update Configuration",
            "hx-post": reverse('settingsdb:form_sample_file_config_validate', args=[key]),
            "hx-target": "#div_id_sample_file_card_" + submit_id
        }

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column(Field("name"), css_class="form-control-sm"),
                Column(Field("file_type"), css_class="form-control-sm"),
                Column(Field("skip"), css_class="form-control-sm"),
                Column(Field("tab"), css_class="form-control-sm"),
            ),
            Row(
                Column(Field("sample_field"), css_class="form-control-sm"),
                Column(Field("comment_field"), css_class="form-control-sm"),
                Column(Field("allowed_replicates"), css_class="form-control-sm"),
                Column(Field("are_blank_sample_ids_replicates"), css_class="form-control-sm"),
            ),
            Submit(name="submit", value="submit",
                   css_id=f"input_id_hidden_submit_{ submit_id }",
                   css_class="visually-hidden",
                   **submit_attrs)
        )


def get_sample_file_type_form(request, file_config_id):
    if file_config_id:
        sample_file_type = SampleFileType.objects.get(pk=file_config_id)

        sample_file_config_form = SampleFileTypeForm(instance=sample_file_type)
        sample_file_config_subform = SampleVariablesForm(initial={"sample_type": file_config_id})
        context = {
            "config": sample_file_type,
            "sample_card_form": sample_file_config_form,
            "sample_card_subform": sample_file_config_subform,
        }
    else:
        sample_file_config_form = SampleFileTypeForm()
        context = {
            "sample_card_form": sample_file_config_form
        }

    html = render_to_string("settingsdb/partials/sample_file_config_form.html", context=context, request=request)
    return HttpResponse(html)


def get_sample_file_type_card(request, file_config_id):
    sample_file_type = models.SampleFileType.objects.get(pk=file_config_id)
    context = {
        "config": sample_file_type
    }
    html = render_to_string("settingsdb/partials/sample_file_config_card.html", context=context, request=request)
    return HttpResponse(html)


def validate_sample_file_type(request, file_config_id):

    if file_config_id:
        sample_file_type = SampleFileType.objects.get(pk=file_config_id)
        sample_file_config_form = SampleFileTypeForm(request.POST, instance=sample_file_type)
    else:
        sample_file_type = None
        sample_file_config_form = SampleFileTypeForm(request.POST)

    if sample_file_config_form.is_valid():
        sample_file_type = sample_file_config_form.save()

        if file_config_id:
            return get_sample_file_type_card(request, sample_file_type.pk)
        else:
            soup = BeautifulSoup("", "html.parser")
            clear_form = get_sample_file_type_form(request, 0)
            clear_form_soup = BeautifulSoup(clear_form.content, 'html.parser')

            new_form = get_sample_file_type_form(request, sample_file_type.pk)
            new_form_soup = BeautifulSoup('<div hx-swap-oob="afterend:#div_id_sample_file_card_new"></div>', "html.parser")
            new_form_soup.find('div').append(BeautifulSoup(new_form.content, "html.parser"))

            soup.append(clear_form_soup.find(id="div_id_sample_file_card_new").find('div'))
            soup.append(new_form_soup)
            return HttpResponse(soup)

    context = {
        "sample_card_form": sample_file_config_form
    }
    if sample_file_type:
        context['config'] = sample_file_type

    html = render_to_string("settingsdb/partials/sample_file_config_form.html", context=context, request=request)
    return HttpResponse(html)

def delete_sample_file_type(request, file_config_id):
    models.SampleFileType.objects.get(pk=file_config_id).delete()
    return HttpResponse()

def update_variable_table(request, file_config_id):
    sample_file_type = SampleFileType.objects.get(pk=file_config_id)
    context = {
        "config": sample_file_type,
    }
    html = render_to_string("settingsdb/partials/sample_file_config_form.html", context=context)
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find(id="div_id_sample_card_variables")

    return HttpResponse(table)

def get_edit_variable_form(request, variable_id, **kwargs):
    if variable_id:
        variable = models.SampleTypeVariable.objects.get(pk=variable_id)
        sample_file_type = variable.sample_type

        form = SampleVariablesForm(instance=variable)
    else:
        sample_file_id = request.resolver_match.kwargs.get('file_config_id')
        sample_file_type = models.SampleFileType.objects.get(pk=sample_file_id)
        form = SampleVariablesForm(initial={"sample_type": sample_file_id})

    context = {
        "sample_card_subform": form,
        "config": sample_file_type
    }

    html = render_to_string("settingsdb/partials/sample_file_config_subform.html", context=context, request=request)
    soup = BeautifulSoup(html, "html.parser")
    form_soup = soup.find(id=f"div_id_sample_card_{sample_file_type.pk}_subform")
    return HttpResponse(form_soup)


def validate_sample_variable(request, **kwargs):

    if request.method == "GET":
        return get_edit_variable_form(request, 0)

    variable_id = kwargs.get("variable_id", 0)
    sample_type_id = request.POST.get("sample_type", 0)
    sample_file_type = models.SampleFileType.objects.get(pk=sample_type_id)
    if variable_id:
        variable = models.SampleTypeVariable.objects.get(pk=variable_id)
        form = SampleVariablesForm(request.POST, instance=variable)
    else:
        form = SampleVariablesForm(request.POST)

    if form.is_valid():
        variable = form.save()
        form = SampleVariablesForm(initial={"sample_type": sample_type_id})
        context = {
            "sample_card_subform": form,
            "config": sample_file_type
        }

        html = render_to_string("settingsdb/partials/sample_file_config_subform.html", context=context, request=request)
        soup = BeautifulSoup(html, "html.parser")
        form_soup = soup.find(id=f"div_id_sample_card_{sample_type_id}_subform")
        response = HttpResponse(form_soup)
        response['HX-Trigger'] = "update_variable_list"
        return response

    context = {
        "sample_card_subform": form,
        "config": sample_file_type
    }

    html = render_to_string("settingsdb/partials/sample_file_config_subform.html", context=context, request=request)
    return HttpResponse(html)


def delete_sample_sample_variable(request, variable_id):
    models.SampleTypeVariable.objects.get(pk=variable_id).delete()
    return HttpResponse()


urlpatterns = [
    path('sample_file_config/card/<int:file_config_id>/', get_sample_file_type_card, name="form_sample_file_config_get_card"),
    path('sample_file_config/form/<int:file_config_id>/', get_sample_file_type_form, name="form_sample_file_config_get_form_card"),
    path('sample_file_config/form/<int:file_config_id>/validate/', validate_sample_file_type, name="form_sample_file_config_validate"),
    path('sample_file_config/delete/<int:file_config_id>/', delete_sample_file_type, name="form_sample_file_type_variable_delete"),

    path('sample_variable/update_form/<int:variable_id>/', get_edit_variable_form, name="form_sample_file_variable_edit"),
    path('sample_variable/update_table/<int:file_config_id>/', update_variable_table, name="form_sample_file_update_vars"),
    path('sample_variable/validate/<int:file_config_id>/<int:variable_id>/', validate_sample_variable, name="form_sample_file_variable_validate"),
    path('sample_variable/delete/<int:variable_id>/', delete_sample_sample_variable, name="form_sample_file_variable_delete"),
]