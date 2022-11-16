from django.utils.translation import gettext_lazy

try:
    from pretix.base.plugins import PluginConfig
except ImportError:
    raise RuntimeError("Please use pretix 2.7 or above to run this plugin!")

__version__ = "1.0.1"


class PluginApp(PluginConfig):
    name = "pretix_fsr_validation"
    verbose_name = "FSR Validation"

    class PretixPluginMeta:
        name = gettext_lazy("FSR Validation")
        author = "pretix team"
        description = gettext_lazy("Custom validation for orders built for the FSR Digital Engineering an Uni Potsdam")
        visible = True
        version = __version__
        category = "CUSTOMIZATION"
        compatibility = "pretix>=3.18.0.dev0"

    def ready(self):
        print("Running fsr validation ready")
        from . import signals  # NOQA


default_app_config = "pretix_fsr_validation.PluginApp"
