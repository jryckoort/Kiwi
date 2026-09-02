"""Pluggable market-data sources.

Which one is used is a config decision, not a code change:

    SECURITY_PRICE_PROVIDER=stooq      # in .env

A single security can override the global choice via ``price_provider`` —
useful when one holding is only quoted by one source.

Symbols are provider-specific, so switching provider generally means
revisiting the symbols too. The admin shows an example per provider.
"""

from django.conf import settings

from .base import PriceProvider, PriceUnavailable
from .stooq import StooqProvider
from .twelvedata import TwelveDataProvider
from .yahoo import YahooProvider

_PROVIDERS = {
    provider.name: provider
    for provider in (YahooProvider, StooqProvider, TwelveDataProvider)
}

DEFAULT_PROVIDER = YahooProvider.name

#: (value, label) pairs for model choices and the admin
PROVIDER_CHOICES = [
    (name, f"{name} (ex: {cls.symbol_example})") for name, cls in sorted(_PROVIDERS.items())
]


def available_providers():
    return sorted(_PROVIDERS)


def get_provider(name=None):
    """Resolve a provider by name, falling back to the configured default."""
    resolved = name or getattr(settings, "SECURITY_PRICE_PROVIDER", "") or DEFAULT_PROVIDER
    resolved = resolved.strip().lower()

    try:
        return _PROVIDERS[resolved]()
    except KeyError as exc:
        raise PriceUnavailable(
            f"Fournisseur de cours inconnu : « {resolved} ». "
            f"Valeurs possibles : {', '.join(available_providers())}."
        ) from exc


def provider_for(security):
    """The provider a given security should use — its own, else the default."""
    return get_provider(security.price_provider or None)


__all__ = [
    "DEFAULT_PROVIDER",
    "PROVIDER_CHOICES",
    "PriceProvider",
    "PriceUnavailable",
    "available_providers",
    "get_provider",
    "provider_for",
]
