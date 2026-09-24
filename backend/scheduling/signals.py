"""Sinais do scheduling: cria Subscription FREE para cada salão novo."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from billing.models import Subscription
from organizations.models import Organization


@receiver(post_save, sender=Organization)
def create_subscription_for_new_organization(sender, instance, created, **kwargs):
    """Todo salão nasce com assinatura FREE (sem cobrança até upgrade)."""
    if created:
        Subscription.objects.get_or_create(organization=instance)
