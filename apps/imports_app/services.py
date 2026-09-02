import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

REQUIRED_FIELDS = ("date", "amount")
OPTIONAL_FIELDS = ("description", "counterparty")


def _read_text(file_field):
    file_field.open("rb")
    try:
        raw = file_field.read()
    finally:
        file_field.close()
    return raw.decode("utf-8-sig")


def read_headers(file_field, delimiter=","):
    text = _read_text(file_field)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return next(reader, [])


def normalize_amount(raw: str) -> Decimal:
    s = raw.strip().replace(" ", "")
    if not s:
        raise InvalidOperation("montant vide")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    return Decimal(s)


def parse_rows(file_field, column_mapping, date_format, delimiter=","):
    """Returns a list of dicts, one per CSV row: either a parsed row with
    date/amount/description/counterparty, or an error row carrying ``error``.
    """
    text = _read_text(file_field)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)

    rows = []
    for line_number, raw_row in enumerate(reader, start=2):
        try:
            date_str = raw_row.get(column_mapping["date"], "").strip()
            amount_str = raw_row.get(column_mapping["amount"], "").strip()
            description = raw_row.get(column_mapping.get("description", ""), "") or ""
            counterparty = raw_row.get(column_mapping.get("counterparty", ""), "") or ""

            parsed_date = datetime.strptime(date_str, date_format).date()
            amount = normalize_amount(amount_str)
        except (KeyError, ValueError, InvalidOperation) as exc:
            rows.append({"line": line_number, "error": str(exc), "raw": raw_row})
            continue

        rows.append(
            {
                "line": line_number,
                "date": parsed_date,
                "amount": amount,
                "description": description.strip(),
                "counterparty": counterparty.strip(),
            }
        )
    return rows


def mark_duplicates(rows, account):
    from apps.budget.models import Transaction

    existing = set(
        Transaction.objects.filter(account=account).values_list("date", "amount", "description")
    )
    for row in rows:
        if "error" in row:
            continue
        row["is_duplicate"] = (row["date"], row["amount"], row["description"]) in existing
    return rows


def import_rows(rows, batch):
    from apps.budget.models import Transaction

    imported, skipped = 0, 0
    to_create = []
    for row in rows:
        if "error" in row or row.get("is_duplicate"):
            skipped += 1
            continue
        to_create.append(
            Transaction(
                household=batch.household,
                account=batch.account,
                currency=batch.account.currency,
                date=row["date"],
                amount=row["amount"],
                description=row["description"],
                counterparty=row["counterparty"],
                import_batch=batch,
            )
        )
    Transaction.objects.bulk_create(to_create)
    imported = len(to_create)
    return imported, skipped
