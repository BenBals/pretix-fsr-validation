import json
import re

import requests
from django.core.exceptions import ValidationError
from django.dispatch import receiver
from django.urls import resolve, reverse
from django.utils.translation import gettext_lazy as _
from i18nfield.strings import LazyI18nString
from i18nfield.utils import I18nJSONEncoder

from pretix.base.services.orders import Order
from pretix.base.settings import settings_hierarkey
from pretix.control.signals import nav_event_settings
from pretix.presale.signals import (
    contact_form_fields_overrides,
)
from pretix.presale.views import get_cart


@receiver(nav_event_settings, dispatch_uid="fsr_validation_nav")
def navbar_info(sender, request, **kwargs):
    url = resolve(request.path_info)
    if not request.user.has_event_permission(
            request.organizer, request.event, "can_change_event_settings", request=request
    ):
        return []
    return [
        {
            "label": _("FSR Validation"),
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
                may_order_validator_for_request(sender, request)
            ]
        }
    }

    return o


def may_order_validator_for_request(event, request):
    def validator(email):
        email = normalize_hpi_email(email)
        config = get_config(event)
        cart = get_cart(request)

        if cart_contains_unverified_engel_ticket(event, cart):
            if tries_to_double_book_engel_ticket(event, email):
                raise ValidationError(
                    LazyI18nString(config.get("engel_ticket:double_booking:messages"))
                )

            if not is_engel(config, email):
                raise ValidationError(
                    LazyI18nString(config.get("engel_ticket:no_shift:messages"))
                )

    return validator


def cart_contains_unverified_engel_ticket(event, cart):
    does = False

    # TODO Maybe rewrite to any(lambda: ...)
    for position in cart:
        if position_is_unverified_engel_ticket(event, position):
            does = True

    return does


def is_engel(config, email):
    for possible_email in list_of_possible_hpi_email(email):
        if check_email_in_engelsystem(config, possible_email):
            return True
    return False


def check_email_in_engelsystem(config, email):
    headers = {'api_key': config.get('engelsystem:api_key')}
    x = requests.get(f"{config.get('engelsystem:url')}/api/usershifts/{email}", headers=headers)
    if x.status_code != 200:
        return False
    try:
        if x.json().get("count") >= 1:
            return True
    except:
        return False


def get_config(event):
    return event.settings.fsr_validation_config


def tries_to_double_book_engel_ticket(event, email):
    # email should be normalized with normalize_hpi_email
    for order in event.orders.all():
        if order.email == email and order.status != Order.STATUS_CANCELED and order.status != Order.STATUS_EXPIRED:
            for position in order.positions.all():
                if position_is_unverified_engel_ticket(event, position):
                    return True

    return False


def position_has_engel_voucher(event, position):
    config = get_config(event)
    if position.voucher is None:
        return False
    code = position.voucher.code
    prefix = config.get('engel_voucher:prefix')
    if code is None or prefix is None:
        return False
    return code.startswith(prefix)


def position_is_unverified_engel_ticket(event, position):
    helper_ticket_names = get_config(event).get("engel_ticket_names").lower().split(',')
    ticket_name = position.item.name.localize('en').lower()
    if position_has_engel_voucher(event, position):
        return False
    print("Voucher", position.voucher)
    return ticket_name in helper_ticket_names


def is_hpi_email(email):
    return re.search(".*(@hpi.de|@student.hpi.de|@hpi.uni-potsdam.de|@student.hpi.uni-potsdam.de)$", email) is not None


def normalize_hpi_email(email):
    if is_hpi_email(email):
        return email.replace("@student.hpi.uni-potsdam.de", "@student.hpi.de").replace("@hpi.uni-potsdam.de", "@hpi.de")
    else:
        return email


def list_of_possible_hpi_email(email):
    if is_hpi_email(email):
        return [normalize_hpi_email(email), normalize_hpi_email(email).replace(".hpi.de", ".hpi.uni-potsdam.de")]
    else:
        return [email]


default_config = {
    'engel_ticket_names': 'Helper ticket',
    'engel_ticket:no_shift:messages': LazyI18nString({
        'en': 'Make sure you are enrolled in a shift at engelsystem.hpi.de before you buy a helper ticket.',
        'de-informal': 'Wir können Dich nicht im Engelsystem finden. Bitte stelle sicher, dass Du Dich unter engelsystem.hpi.de für eine Schicht eingetragen hast, bevor Du ein Ticket kaufst.'
    }),
    'engel_ticket:double_booking:messages': LazyI18nString({
        'en': 'You have previously bought a helper ticket. If you want more tickets, please buy normal tickets.',
        'de-informal': 'Du hast schon ein Engelticket gekauft. Wenn Du weitere Tickets möchtest, wähle bitte normale Tickets.'
    }),
    'engelsystem:url': 'https://engelsystem.myhpi.de',
    'engel_voucher:prefix': 'ENGEL-'
}

settings_hierarkey.add_default("fsr_validation_config", json.dumps(default_config, cls=I18nJSONEncoder), dict)
