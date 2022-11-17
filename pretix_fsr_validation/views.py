import json
import logging
import re
from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import escape
from django.utils.translation import gettext_lazy as _, gettext_noop
from django.views.generic import FormView
from i18nfield.forms import I18nFormField, I18nTextInput
from i18nfield.strings import LazyI18nString
from i18nfield.utils import I18nJSONEncoder
from pretix.base.models import Event, Question
from pretix.control.views.event import EventSettingsViewMixin

from pretix_fsr_validation.signals import default_config

logger = logging.getLogger(__name__)


def valid_regex(val):
    try:
        re.compile(val)
    except re.error:
        raise ValidationError(_("Not a valid Python regular expression."))


class FsrValidationSettingsForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.obj = kwargs.pop("obj")
        super().__init__(*args, **kwargs)

        self.fields["engel_ticket_names"] = forms.CharField(
            label="Which tickets should be restricted to Engels? (Comma-seperated list of English names)",
            required=False,
        )

        self.fields["engel_ticket:double_booking:messages"] = I18nFormField(
            label='Error message for Engel double booking',
            required=False,
            locales=self.obj.settings.locales,
            initial=default_config['engel_ticket:double_booking:messages'],
            widget=I18nTextInput,
        )

        self.fields["engel_ticket:no_shift:messages"] = I18nFormField(
            label='Error message for Engels without shifts',
            required=False,
            locales=self.obj.settings.locales,
            initial=default_config['engel_ticket:no_shift:messages'],
            widget=I18nTextInput,
        )

class SettingsView(EventSettingsViewMixin, FormView):
    model = Event
    form_class = FsrValidationSettingsForm
    template_name = "pretix_fsr_validation/settings.html"
    permission = "can_change_event_settings"

    def get_success_url(self) -> str:
        return reverse(
            "plugins:pretix_fsr_validation:settings",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
            },
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["obj"] = self.request.event
        kwargs["initial"] = self.request.event.settings.fsr_validation_config
        return kwargs

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            if form.has_changed():
                self.request.event.settings.fsr_validation_config = json.dumps(
                    form.cleaned_data, cls=I18nJSONEncoder
                )
                self.request.event.log_action(
                    "pretix.event.settings",
                    user=self.request.user,
                    data={"fsr_validation_config": form.cleaned_data},
                )
            messages.success(self.request, _("Your changes have been saved."))
            return redirect(self.get_success_url())
        else:
            messages.error(
                self.request,
                _("We could not save your changes. See below for details."),
            )
            return self.render_to_response(self.get_context_data(form=form))
