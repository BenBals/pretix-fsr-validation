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
from pretix.base.services.orders import OrderError

print("FSR Signals are registered!")


@receiver(nav_event_settings, dispatch_uid="fsr_validation_nav")
def navbar_info(sender, request, **kwargs):
    print("FSR wants into the sidebar!")
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

@receiver(validate_order, dispatch_uid="fsr_validate_order")
def fsr_validate_order(event, payment_provider, positions, email, locale, invoice_address, meta_info, customer, **kwargs):
    print("FSR validates cart for order!")

    # Throw if double booking

    print(event.settings.fsr_validation_config)

    if email == "paula.marten@student.hpi.de":
        raise OrderError('The FSR does not want Paula to buy a ticket with this order')


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
    def validator(value):
        print("Validating mail!")
        if contains_engel_ticket(event, request):
            return False
        return True

    return validator

def contains_engel_ticket(event, request):
    does = False

    helper_ticket_names = event.settings.fsr_validation_config.get("engel_ticket_names").lower().split(',')

    for position in request.event.cartposition_set.all():
        if position.item.name.lower() in helper_ticket_names:
            does = True

    return does


def is_angel(user):
    return True

settings_hierarkey.add_default("fsr_validation_config", "{}", dict)
