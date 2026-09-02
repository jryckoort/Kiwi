from datetime import date

from django.db import migrations

# Seed values reflect the rules known at the time this app was built (2026).
# TOB rates/caps and the précompte mobilier exemption threshold are indexed
# periodically — verify current figures on the SPF Finances website before
# relying on these for a real declaration. Edit via the Django admin once
# updated, no code change needed.

TOB_RATES = [
    ("bonds", "0.12", "1300.00"),
    ("shares", "0.35", "1600.00"),
    ("capitalization", "1.32", "4000.00"),
]


def seed_tax_rules(apps, schema_editor):
    TOBRate = apps.get_model("taxes", "TOBRate")
    PrecompteMobilierRule = apps.get_model("taxes", "PrecompteMobilierRule")
    PlusValueTaxRule = apps.get_model("taxes", "PlusValueTaxRule")

    for instrument_type, rate_percent, cap_amount in TOB_RATES:
        TOBRate.objects.get_or_create(
            instrument_type=instrument_type,
            defaults={
                "rate_percent": rate_percent,
                "cap_amount": cap_amount,
                "effective_from": date(2017, 1, 1),
            },
        )

    PrecompteMobilierRule.objects.get_or_create(
        year=2026,
        defaults={"rate_percent": "30.00", "savings_account_exempt_threshold": "1100.00"},
    )

    PlusValueTaxRule.objects.get_or_create(
        year=2026,
        defaults={
            "rate_percent": "10.00",
            "annual_exemption": "10000.00",
            "reference_date": date(2025, 12, 31),
        },
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("taxes", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_tax_rules, noop),
    ]
