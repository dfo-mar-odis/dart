from django import forms
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.urls import path

from dart import models

class AttachmentsForm(forms.ModelForm):
    event = forms.ModelChoiceField(
        queryset=models.Event.objects.all(),
        required=True,
        widget=forms.HiddenInput()
    )

    class Meta:
        model = models.Attachment
        fields = "__all__"


def get_form(request, event_id):
    event = models.Event.objects.get(pk=event_id)

    context = {
        'event': event,
    }
    initial = {
        "event": event.pk,
    }

    if request.method == "POST":
        context['form'] = AttachmentsForm(request.POST or None, initial=initial)
        if context['form'].is_valid():
            attachment = context['form'].save()
            context['form'] = AttachmentsForm(initial=initial)
    else:
        context['form'] = AttachmentsForm(initial=initial)

    html = render_to_string('dart/forms/attachment_form.html', context=context)

    response = HttpResponse(html)
    return response

def delete_attachment(request, event_id, attachment_id):

    event = models.Event.objects.get(pk=event_id)
    if request.method == "POST":
        attachment = event.attachments.filter(pk=attachment_id)
        if attachment.exists():
            attachment.delete()

    context = {
        'event': event,
        'form': AttachmentsForm(initial={'event': event})
    }
    html = render_to_string('dart/forms/attachment_form.html', context)
    response = HttpResponse(html)
    return response

urlpatterns = [
    path("event/attachment/<int:event_id>", get_form, name="form_event_attachment_new"),
    path("event/attachment/delete/<int:event_id>/<int:attachment_id>", delete_attachment, name="form_event_attachment_delete"),
]