from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.wealth.models import SecurityTransaction

from .services import recompute_capital_gains_for


@receiver(post_save, sender=SecurityTransaction)
def on_security_transaction_saved(sender, instance, **kwargs):
    recompute_capital_gains_for(instance.account_id, instance.security_id)


@receiver(post_delete, sender=SecurityTransaction)
def on_security_transaction_deleted(sender, instance, **kwargs):
    recompute_capital_gains_for(instance.account_id, instance.security_id)
