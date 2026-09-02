from django.db import migrations, models


class Migration(migrations.Migration):
    """Make the price symbol provider-agnostic.

    Written as a RenameField rather than the drop-and-add Django proposed:
    symbols already entered must survive, and dropping the column would throw
    them away silently.
    """

    dependencies = [
        ("wealth", "0004_security_last_sync_error_security_last_synced_at_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="security",
            old_name="yahoo_symbol",
            new_name="price_symbol",
        ),
        migrations.AlterField(
            model_name="security",
            name="price_symbol",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Distinct de l'ISIN : les fournisseurs ne savent pas chercher par ISIN, "
                    "et chacun a sa propre notation (IWDA.AS chez Yahoo, iwda.nl chez Stooq). "
                    "Laissez vide pour saisir les cours à la main."
                ),
                max_length=30,
                verbose_name="symbole du fournisseur de cours",
            ),
        ),
        migrations.AddField(
            model_name="security",
            name="price_provider",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Laissez vide pour utiliser le fournisseur configuré dans "
                    "SECURITY_PRICE_PROVIDER."
                ),
                max_length=20,
                verbose_name="fournisseur de cours",
            ),
        ),
    ]
