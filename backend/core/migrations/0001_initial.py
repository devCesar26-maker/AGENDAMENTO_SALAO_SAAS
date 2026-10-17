import core.models
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("organizations", "0003_organization_tema_cor_organization_vertical")
    ]

    operations = [
        migrations.CreateModel(
            name="IdempotencyKey",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("key", models.CharField(db_index=True, max_length=255)),
                ("scope_digest", models.CharField(max_length=64, unique=True)),
                ("context", models.CharField(max_length=80)),
                ("request_fingerprint", models.CharField(max_length=64)),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("PROCESSING", "Em processamento"),
                            ("COMPLETED", "Concluída"),
                        ],
                        default="PROCESSING",
                        max_length=12,
                    ),
                ),
                ("result", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "expires_at",
                    models.DateTimeField(
                        db_index=True, default=core.models.default_idempotency_expiry
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="idempotency_keys",
                        to="organizations.organization",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="idempotencykey",
            index=models.Index(
                fields=["context", "expires_at"], name="idempotency_expiry_idx"
            ),
        ),
    ]
