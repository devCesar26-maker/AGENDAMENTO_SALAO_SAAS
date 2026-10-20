from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("analytics", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("APPOINTMENT_CANCELED", "Agendamento cancelado"),
                    ("MEMBER_REMOVED", "Membro removido"),
                    ("PLAN_CHANGED", "Plano alterado"),
                    ("COMMISSION_CHANGED", "Comissão alterada"),
                    ("CUSTOMER_ANONYMIZED", "Cliente anonimizado"),
                ],
                db_index=True,
                max_length=40,
            ),
        )
    ]
