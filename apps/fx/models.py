from django.db import models


class Currency(models.Model):
    code = models.CharField(max_length=3, primary_key=True)
    name = models.CharField(max_length=50)
    symbol = models.CharField(max_length=5, blank=True)

    class Meta:
        verbose_name = "devise"
        verbose_name_plural = "devises"
        ordering = ["code"]

    def __str__(self):
        return self.code


class ExchangeRate(models.Model):
    base_currency = models.ForeignKey(
        Currency, on_delete=models.CASCADE, related_name="rates_as_base"
    )
    quote_currency = models.ForeignKey(
        Currency, on_delete=models.CASCADE, related_name="rates_as_quote"
    )
    date = models.DateField()
    rate = models.DecimalField(
        max_digits=18, decimal_places=8, help_text="1 base_currency = rate * quote_currency"
    )

    class Meta:
        verbose_name = "taux de change"
        verbose_name_plural = "taux de change"
        constraints = [
            models.UniqueConstraint(
                fields=["base_currency", "quote_currency", "date"], name="unique_rate_per_day"
            )
        ]
        ordering = ["-date"]

    def __str__(self):
        return f"{self.base_currency}/{self.quote_currency} @ {self.date} = {self.rate}"
