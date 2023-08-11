from django.apps import AppConfig
from django.utils.translation import gettext_lazy
from . import __version__
from pathlib import Path


class PluginApp(AppConfig):
    name = 'pretix_fsr_validation'
    verbose_name = 'FSR Validation'

    class PretixPluginMeta:
        name = gettext_lazy("FSR Validation")
        author = "Ben Bals"
        description = gettext_lazy("Custom validation for orders built for the FSR Digital Engineering an Uni Potsdam")
        visible = True
        version = __version__
        category = "CUSTOMIZATION"
        compatibility = "pretix>=4.20.0"


    def ready(self):
        script_path = Path( __file__ ).absolute()
        print("Running fsr validation ready from ", script_path)
        from . import signals  # NOQA

default_app_config = "pretix_fsr_validation.PluginApp"
