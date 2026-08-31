from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.wealth.models import SecurityTransaction

from .services import compute_and_store_capital_gain


@receiver(post_save, sender=SecurityTransaction)
def on_security_transaction_saved(sender, instance, **kwargs):
    if instance.type == SecurityTransaction.Type.SELL:
        compute_and_store_capital_gain(instance)
