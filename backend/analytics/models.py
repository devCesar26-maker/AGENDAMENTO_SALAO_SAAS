"""Trilha de auditoria por organização."""

from django.db import models


class AuditLog(models.Model):
    class Action(models.TextChoices):
        APPOINTMENT_CANCELED = "APPOINTMENT_CANCELED", "Agendamento cancelado"
        MEMBER_REMOVED = "MEMBER_REMOVED", "Membro removido"
        PLAN_CHANGED = "PLAN_CHANGED", "Plano alterado"
        COMMISSION_CHANGED = "COMMISSION_CHANGED", "Comissão alterada"
        CUSTOMER_ANONYMIZED = "CUSTOMER_ANONYMIZED", "Cliente anonimizado"

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="audit_logs"
    )
    actor = models.ForeignKey(
        "organizations.Membership",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=40, choices=Action.choices, db_index=True)
    object_type = models.CharField(max_length=80)
    object_id = models.CharField(max_length=64, blank=True)
    context = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=("organization", "action", "created_at")),
            models.Index(fields=("organization", "created_at")),
        ]

    def __str__(self):
        return f"{self.action} · {self.organization_id} · {self.object_type}:{self.object_id}"
