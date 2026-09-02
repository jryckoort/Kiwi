from datetime import date
from decimal import Decimal

import pytest
from django.core.files.base import ContentFile

from apps.accounts.tests.factories import CurrencyFactory, HouseholdFactory, UserFactory
from apps.budget.models import FinancialAccount, Transaction
from apps.imports_app.models import ImportBatch
from apps.imports_app.services import (
    import_rows,
    mark_duplicates,
    normalize_amount,
    parse_rows,
    read_headers,
)

pytestmark = pytest.mark.django_db

MAPPING = {"date": "Date", "amount": "Montant", "description": "Libellé", "counterparty": "Contrepartie"}

CSV_SAMPLE = (
    "Date;Montant;Libellé;Contrepartie\n"
    "01/03/2026;-42,50;Supermarché;Colruyt\n"
    "02/03/2026;1500,00;Salaire;Employeur SA\n"
    "03/03/2026;pas-un-montant;Ligne cassée;X\n"
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("42,50", Decimal("42.50")),
        ("42.50", Decimal("42.50")),
        ("1.234,56", Decimal("1234.56")),
        ("1,234.56", Decimal("1234.56")),
        ("-42,50", Decimal("-42.50")),
        (" 1000 ", Decimal("1000")),
    ],
)
def test_normalize_amount_handles_european_and_us_formats(raw, expected):
    assert normalize_amount(raw) == expected


def test_read_headers():
    file_field = ContentFile(CSV_SAMPLE.encode("utf-8"))
    headers = read_headers(file_field, delimiter=";")
    assert headers == ["Date", "Montant", "Libellé", "Contrepartie"]


def test_parse_rows_flags_unparseable_lines_without_dropping_them():
    file_field = ContentFile(CSV_SAMPLE.encode("utf-8"))
    rows = parse_rows(file_field, MAPPING, date_format="%d/%m/%Y", delimiter=";")

    assert len(rows) == 3
    assert rows[0]["amount"] == Decimal("-42.50")
    assert rows[0]["date"] == date(2026, 3, 1)
    assert rows[1]["amount"] == Decimal("1500.00")
    assert "error" in rows[2]


@pytest.fixture
def household_with_account():
    CurrencyFactory()
    household = HouseholdFactory()
    account = FinancialAccount.objects.create(household=household, name="Compte", currency_id="EUR")
    return household, account


def test_mark_duplicates_flags_existing_transaction(household_with_account):
    household, account = household_with_account
    Transaction.objects.create(
        household=household,
        account=account,
        currency_id="EUR",
        date=date(2026, 3, 1),
        amount=Decimal("-42.50"),
        description="Supermarché",
    )

    file_field = ContentFile(CSV_SAMPLE.encode("utf-8"))
    rows = parse_rows(file_field, MAPPING, date_format="%d/%m/%Y", delimiter=";")
    rows = mark_duplicates(rows, account)

    assert rows[0]["is_duplicate"] is True
    assert rows[1]["is_duplicate"] is False


def test_import_rows_creates_transactions_and_skips_duplicates_and_errors(household_with_account):
    household, account = household_with_account
    Transaction.objects.create(
        household=household,
        account=account,
        currency_id="EUR",
        date=date(2026, 3, 1),
        amount=Decimal("-42.50"),
        description="Supermarché",
    )

    user = UserFactory()
    batch = ImportBatch.objects.create(
        household=household,
        account=account,
        uploaded_by=user,
        file=ContentFile(CSV_SAMPLE.encode("utf-8"), name="releve.csv"),
        column_mapping=MAPPING,
        date_format="%d/%m/%Y",
        delimiter=";",
    )

    rows = parse_rows(batch.file, MAPPING, date_format="%d/%m/%Y", delimiter=";")
    rows = mark_duplicates(rows, account)
    imported, skipped = import_rows(rows, batch)

    assert imported == 1
    assert skipped == 2  # 1 duplicate + 1 parse error
    assert Transaction.objects.filter(account=account, description="Salaire").exists()
    assert Transaction.objects.filter(account=account).count() == 2  # pre-existing + newly imported


def test_upload_form_rejects_oversized_file(household_with_account):
    from django.conf import settings
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.imports_app.forms import UploadForm

    household, account = household_with_account
    oversized = SimpleUploadedFile(
        "releve.csv",
        b"x" * (settings.MAX_IMPORT_FILE_SIZE_BYTES + 1),
        content_type="text/csv",
    )
    form = UploadForm(
        data={"account": account.pk}, files={"file": oversized}, household=household
    )

    assert not form.is_valid()
    assert "trop volumineux" in str(form.errors["file"])


def test_upload_form_rejects_non_csv(household_with_account):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.imports_app.forms import UploadForm

    household, account = household_with_account
    form = UploadForm(
        data={"account": account.pk},
        files={"file": SimpleUploadedFile("releve.pdf", b"whatever")},
        household=household,
    )

    assert not form.is_valid()
    assert "CSV" in str(form.errors["file"])
