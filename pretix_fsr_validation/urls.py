from django.conf.urls import url

from .views import SettingsView, CheckTicketsView

urlpatterns = [
    url(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/settings/fsr-validation/$",
        SettingsView.as_view(),
        name="settings",
    ),

url(
        r"^control/event/(?P<organizer>[^/]+)/(?P<event>[^/]+)/settings/fsr-validation/check-tickets$",
        CheckTicketsView.as_view(),
        name="check-tickets",
    ),
]
