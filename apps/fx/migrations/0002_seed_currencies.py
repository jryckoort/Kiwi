from django.db import migrations

CURRENCIES = [
    ("EUR", "Euro", "€"),
    ("USD", "Dollar américain", "$"),
    ("GBP", "Livre sterling", "£"),
    ("CHF", "Franc suisse", "CHF"),
]


def seed_currencies(apps, schema_editor):
    Currency = apps.get_model("fx", "Currency")
    for code, name, symbol in CURRENCIES:
        Currency.objects.get_or_create(code=code, defaults={"name": name, "symbol": symbol})


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("fx", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_currencies, noop),
    ]
