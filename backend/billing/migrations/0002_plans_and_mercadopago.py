from django.db import migrations, models
import django.db.models.deletion


def seed_plans(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    Subscription = apps.get_model("billing", "Subscription")
    plans = {
        "FREE": Plan.objects.create(
            tier="FREE",
            nome_salao="Free",
            nome_barbearia="Free",
            max_professionals=1,
            max_appointments_per_month=50,
            monthly_price_cents=0,
        ),
        "PLUS": Plan.objects.create(
            tier="PLUS",
            nome_salao="Allure",
            nome_barbearia="Artisan",
            max_professionals=3,
            max_appointments_per_month=300,
            monthly_price_cents=2990,
        ),
        "PREMIUM": Plan.objects.create(
            tier="PREMIUM",
            nome_salao="Splendeur",
            nome_barbearia="Confrérie",
            max_professionals=None,
            max_appointments_per_month=None,
            monthly_price_cents=5990,
        ),
    }
    for subscription in Subscription.objects.all():
        tier = "PREMIUM" if subscription.plan == "PRO" else subscription.plan
        subscription.plan_ref_id = plans[tier].pk
        subscription.status = "ACTIVE" if subscription.is_active else "CANCELED"
        subscription.mercadopago_subscription_id = subscription.provider_subscription_id
        subscription.save(
            update_fields=["plan_ref", "status", "mercadopago_subscription_id"]
        )
    for organization in apps.get_model("organizations", "Organization").objects.all():
        Subscription.objects.get_or_create(
            organization_id=organization.pk,
            defaults={"plan_ref_id": plans["FREE"].pk, "status": "ACTIVE"},
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0001_initial"),
        ("organizations", "0003_organization_tema_cor_organization_vertical"),
    ]
    operations = [
        migrations.CreateModel(
            name="Plan",
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
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, db_index=True, verbose_name="criado em"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="atualizado em"),
                ),
                (
                    "tier",
                    models.CharField(
                        choices=[
                            ("FREE", "Free"),
                            ("PLUS", "Plus"),
                            ("PREMIUM", "Premium"),
                        ],
                        max_length=10,
                        unique=True,
                    ),
                ),
                ("nome_salao", models.CharField(max_length=80)),
                ("nome_barbearia", models.CharField(max_length=80)),
                (
                    "max_professionals",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                (
                    "max_appointments_per_month",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                ("monthly_price_cents", models.PositiveIntegerField(default=0)),
            ],
            options={"ordering": ["monthly_price_cents"]},
        ),
        migrations.AddField(
            "subscription",
            "plan_ref",
            models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="subscriptions",
                to="billing.plan",
            ),
        ),
        migrations.AddField(
            "subscription",
            "status",
            models.CharField(
                choices=[
                    ("ACTIVE", "Ativa"),
                    ("PAST_DUE", "Pagamento pendente"),
                    ("CANCELED", "Cancelada"),
                    ("TRIALING", "Em teste"),
                ],
                default="ACTIVE",
                max_length=12,
            ),
        ),
        migrations.AddField(
            "subscription",
            "mercadopago_subscription_id",
            models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            "subscription",
            "current_period_start",
            models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(seed_plans, noop),
        migrations.RenameField("subscription", "plan", "legacy_plan"),
        migrations.RenameField("subscription", "plan_ref", "plan"),
        migrations.RemoveField("subscription", "legacy_plan"),
        migrations.RemoveField("subscription", "is_active"),
        migrations.RemoveField("subscription", "provider"),
        migrations.RemoveField("subscription", "provider_customer_id"),
        migrations.RemoveField("subscription", "provider_subscription_id"),
        migrations.AlterField(
            "subscription",
            "plan",
            models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="subscriptions",
                to="billing.plan",
            ),
        ),
    ]
