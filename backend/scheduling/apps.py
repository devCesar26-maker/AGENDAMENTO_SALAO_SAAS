from django.apps import AppConfig


class SchedulingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "scheduling"
    verbose_name = "Agendamentos"

    def ready(self):
        from scheduling import signals  # noqa: F401  (registro de sinais)
