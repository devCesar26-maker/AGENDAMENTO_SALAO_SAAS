import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0001_initial"),
        ("scheduling", "0003_appointment_reminder_sent_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="NotificationEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                ("kind", models.CharField(choices=[("CONFIRMATION", "Confirmação de agendamento"), ("CANCELLATION", "Cancelamento de agendamento"), ("WAITLIST_OPENING", "Vaga aberta da lista de espera")], max_length=24)),
                ("state", models.CharField(choices=[("PENDING", "Pendente"), ("PROCESSING", "Em processamento"), ("SENT", "Enviado")], default="PENDING", max_length=12)),
                ("available_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("locked_at", models.DateTimeField(blank=True, null=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("last_error", models.CharField(blank=True, max_length=500)),
                ("appointment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notification_events", to="scheduling.appointment")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="%(app_label)s_%(class)s_set", to="organizations.organization", verbose_name="salão")),
            ],
            options={
                "indexes": [models.Index(fields=["state", "available_at"], name="notification_outbox_idx")],
                "constraints": [models.UniqueConstraint(fields=("appointment", "kind"), name="uniq_notification_event_appointment_kind")],
            },
        ),
    ]
