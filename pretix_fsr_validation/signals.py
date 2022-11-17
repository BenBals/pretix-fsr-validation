from django.core.validators import RegexValidator
from django.dispatch import receiver
from django.urls import resolve, reverse
from django.utils.translation import gettext_lazy as _
from i18nfield.strings import LazyI18nString
from pretix.base.settings import settings_hierarkey
from pretix.control.signals import nav_event_settings
from pretix.base.signals import validate_cart, validate_order
from pretix.presale.signals import (
    contact_form_fields_overrides,
    question_form_fields_overrides,
)
from pretix.base.services.cart import CartError
from pretix.base.services.orders import OrderError, Order
from django.core.exceptions import ValidationError
import json
from i18nfield.utils import I18nJSONEncoder


@receiver(nav_event_settings, dispatch_uid="fsr_validation_nav")
def navbar_info(sender, request, **kwargs):
    url = resolve(request.path_info)
    if not request.user.has_event_permission(
            request.organizer, request.event, "can_change_event_settings", request=request
    ):
        return []
    return [
        {
            "label": _("FSR validation"),
            "url": reverse(
                "plugins:pretix_fsr_validation:settings",
                kwargs={
                    "event": request.event.slug,
                    "organizer": request.organizer.slug,
                },
            ),
            "active": url.namespace == "plugins:pretix_fsr_validation",
        }
    ]


@receiver(
    contact_form_fields_overrides, dispatch_uid="fsr_validation_fields_overrides"
)
def fsr_email_overwrite(sender, request, **kwargs):
    o = {
        "email": {
            "validators": [
                may_order_validator_for_request(sender, request, "TODO You are bad.")
            ]
        }
    }

    return o


def may_order_validator_for_request(event, request, message):
    def validator(email):
        print("Validating mail!")
        email = normalize_hpi_email(email)

        if cart_contains_engel_ticket(event, request):
            if not is_engel(email):
                config = get_config(event)

                raise ValidationError(
                    LazyI18nString(get_config(event).get("engel_ticket:no_shift:messages"))
                )

            if tries_to_double_book_engel_ticket(event, email):
                raise ValidationError(
                    LazyI18nString(get_config(event).get("engel_ticket:double_booking:messages"))
                )

    return validator


def cart_contains_engel_ticket(event, request):
    does = False

    # TODO Maybe rewrite to any(lambda: ...)
    for position in request.event.cartposition_set.all():
        if position_is_engel_ticket(event, position):
            does = True

    return does


def is_engel(email):
    if email == "ben.bals@student.hpi.de":
        return False
    return True


def get_config(event):
    return event.settings.fsr_validation_config


def tries_to_double_book_engel_ticket(event, email):
    # email should be normalized with normalize_hpi_email
    for order in event.orders.all():
        if order.email == email and order.status != Order.STATUS_CANCELED and order.status != Order.STATUS_EXPIRED:
            for position in order.positions.all():
                if position_is_engel_ticket(event, position):
                    return True

    return False


def position_is_engel_ticket(event, position):
    helper_ticket_names = get_config(event).get("engel_ticket_names").lower().split(',')
    return position.item.name.localize('en').lower() in helper_ticket_names


def normalize_hpi_email(email):
    return email.replace("@student.hpi.uni-potsdam.de", "@student.hpi.de").replace("@hpi.uni-potsdam.de", "@hpi.de")


default_config = {
    'engel_ticket_names': 'Helper ticket',
    'engel_ticket:no_shift:messages': LazyI18nString({
        'en': 'Make sure you are enrolled in a shift at engelsystem.hpi.de before you buy a helper ticket.',
        # TODO: Why does it not default correctly?
        'de-informal': 'Wir können Dich nicht im Engelsystem finden. Bitte stelle sicher, dass Du Dich unter engelsystem.hpi.de für eine Schicht eingetragen hast, bevor Du ein Ticket kaufst.'
    }),
    "engel_ticket:double_booking:messages": LazyI18nString({
        'en': 'You have previously bought a helper ticket. If you want more tickets, please buy normal tickets.',
        # TODO: Why does it not default correctly?
        'de-informal': 'Du hast schon ein Engelticket gekauft. Wenn Du weitere Tickets möchtest, wähle bitte normale Tickets.'
    }),
}

settings_hierarkey.add_default("fsr_validation_config", json.dumps(default_config, cls=I18nJSONEncoder), dict)
