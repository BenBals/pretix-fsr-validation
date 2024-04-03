import datetime
import json
import logging
import re
from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms import MultipleChoiceField, CheckboxSelectMultiple, SelectMultiple
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.html import escape
from django.utils.translation import gettext_lazy as _, gettext_noop
from django.views.generic import FormView, TemplateView
from django.views import View
from i18nfield.forms import I18nFormField, I18nTextInput
from i18nfield.strings import LazyI18nString
from i18nfield.utils import I18nJSONEncoder

from pretix.base.forms.widgets import SplitDateTimePickerWidget
from pretix.base.models import Event, Question
from pretix.control.views.event import EventSettingsViewMixin
from django.http import HttpResponse

import pretix_fsr_validation.signals as signals

logger = logging.getLogger(__name__)


def valid_regex(val):
    try:
        re.compile(val)
    except re.error:
        raise ValidationError(_("Not a valid Python regular expression."))


def datetime_to_isoformat(dt):
    return dt.astimezone().isoformat()


class FsrValidationSettingsForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.obj = kwargs.pop("obj")
        super().__init__(*args, **kwargs)

        product_choices = list(map(lambda product: (str(product.pk), product.name), self.obj.items.all()))

        self.fields["engel_ticket_names"] = MultipleChoiceField(
                widget=CheckboxSelectMultiple,
                label = _("Which tickets should be restricted to Engels?"),
                required=False,
                initial=[0],
                choices=product_choices)

        self.fields["engel_ticket:double_booking:messages"] = I18nFormField(
            label=_('Error message for Engel double booking'),
            required=False,
            locales=self.obj.settings.locales,
            initial=signals.default_config['engel_ticket:double_booking:messages'],
            widget=I18nTextInput,
        )

        self.fields["engel_ticket:no_shift:messages"] = I18nFormField(
            label=_('Error message for Engels without shifts'),
            required=False,
            locales=self.obj.settings.locales,
            initial=signals.default_config['engel_ticket:no_shift:messages'],
            widget=I18nTextInput,
        )

        self.fields["ephios:url"] = forms.CharField(
            label="Ephios URL",
            initial=signals.default_config['ephios:url'],
            required=True,
        )

        self.fields["ephios:api_key"] = forms.CharField(
            label="Ephios API Key",
            required=True,
        )

        self.fields["engel_voucher:prefix"] = forms.CharField(
            label=_("Orders with a voucher with this prefix are allowed to buy engel tickets"),
            initial=signals.default_config['engel_voucher:prefix'],
            required=False,
        )

        self.fields["engel_ticket:allow_ticket_download_without_email_verification"] = forms.BooleanField(
            label=_("Allow downloading engel tickets without email verification"),
            help_text=_(
                'This only applies to order pages. In emails, tickets will always be send as per the event settings'),
            initial=signals.default_config['engel_ticket:allow_ticket_download_without_email_verification'],
            required=False,
        )

        self.fields["shifts:after"] = forms.SplitDateTimeField(
            label=_("Shifts starts after"),
            help_text=_("Only consider shifts after this date time  when determining engel ticket eligibility"),
            initial=signals.default_config['shifts:after'],
            required=False,
            widget = SplitDateTimePickerWidget(),
            validators=[datetime_to_isoformat]
        )

        self.fields["shifts:before"] = forms.SplitDateTimeField(
            label=_("Shift starts before"),
            help_text=_("Only consider shifts before this date time when determining engel ticket eligibility"),
            initial=signals.default_config['shifts:before'],
            required=False,
            widget = SplitDateTimePickerWidget(),
            validators=[datetime_to_isoformat]
        )

        self.fields["shifts:ephios_event_types"] = forms.CharField(
            label=_(
                "Which ephios event types should count towards Engel status? (Comma-seperated list of ids)"),
            help_text=_('Leave empty to allow all types'),
            required=False,
        )


class SettingsView(EventSettingsViewMixin, FormView):
    model = Event
    form_class = FsrValidationSettingsForm
    template_name = "pretix_fsr_validation/settings.html"
    permission = "can_change_event_settings"

    def get_check_tickets_url(self) -> str:
        return reverse(
            "plugins:pretix_fsr_validation:check-tickets",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
            },
        )

    def get_success_url(self) -> str:
        return reverse(
            "plugins:pretix_fsr_validation:settings",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
            },
        )

    def get_form_kwargs(self):
        current_config = self.request.event.settings.fsr_validation_config

        # Pretix settings are always converted to strings automatically…
        if current_config["shifts:before"]:
            current_config["shifts:before"] = datetime.datetime.fromisoformat(current_config["shifts:before"])
        if current_config["shifts:after"]:
            current_config["shifts:after"] = datetime.datetime.fromisoformat(current_config["shifts:after"])

        if current_config["engel_ticket_names"] is not None:
            try:
                # current_config["engel_ticket_names"] = list(map(int, current_config["engel_ticket_names"].split(',')))
                pass
            except ValueError:
                current_config["engel_ticket_names"] = []

        kwargs = super().get_form_kwargs()
        kwargs["obj"] = self.request.event
        kwargs["initial"] = current_config
        return kwargs

    def get_context_data(self, **kwargs):
        """Insert the form into the context dict."""
        if "check_tickets_url" not in kwargs:
            kwargs["check_tickets_url"] = self.get_check_tickets_url()
        return super().get_context_data(**kwargs)

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


class CheckTicketsView(EventSettingsViewMixin, TemplateView):
    model = Event
    template_name = "pretix_fsr_validation/check_tickets.html"

    def get(self, request, *args, **kwargs):
        fallen_angels = []
        config = signals.get_config(request.event)

        engel_orders = []

        for order in request.event.orders.all():
            for position in order.positions.all():
                if signals.position_is_unverified_engel_ticket(request.event, position):
                    engel_orders.append(order)

        for order in engel_orders:
            if not signals.is_engel(config, order.email):
                fallen_angels.append(order.email)

        return render(request, self.template_name, {'fallen_angels': fallen_angels})
