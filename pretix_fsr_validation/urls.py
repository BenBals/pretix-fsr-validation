from django.urls import re_path

from .views import SettingsView, CheckTicketsView

urlpatterns = [
    re_path(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/settings/fsr-validation/$",
        SettingsView.as_view(),
        name="settings",
    ),
    re_path(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/settings/fsr-validation/check-tickets$",
        CheckTicketsView.as_view(),
        name="check-tickets",
    ),
]
