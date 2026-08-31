from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.decorators import household_required

from .forms import MappingForm, UploadForm
from .models import ImportBatch, ImportMappingTemplate
from .services import import_rows, mark_duplicates, parse_rows, read_headers


@household_required
def upload(request):
    if request.method == "POST":
        form = UploadForm(request.POST, request.FILES, household=request.household)
        if form.is_valid():
            batch = ImportBatch.objects.create(
                household=request.household,
                account=form.cleaned_data["account"],
                uploaded_by=request.user,
                file=form.cleaned_data["file"],
            )
            template = form.cleaned_data.get("template")
            if template:
                batch.column_mapping = template.column_mapping
                batch.date_format = template.date_format
                batch.delimiter = template.delimiter
                batch.save(update_fields=["column_mapping", "date_format", "delimiter"])
            return redirect("imports_app:map_columns", pk=batch.pk)
    else:
        form = UploadForm(household=request.household)
    return render(request, "imports_app/upload.html", {"form": form})


@household_required
def map_columns(request, pk):
    batch = get_object_or_404(ImportBatch.objects.for_household(request.household), pk=pk)
    headers = read_headers(batch.file, delimiter=batch.delimiter)

    initial = {}
    if batch.column_mapping:
        initial = {
            "date_column": batch.column_mapping.get("date"),
            "amount_column": batch.column_mapping.get("amount"),
            "description_column": batch.column_mapping.get("description", ""),
            "counterparty_column": batch.column_mapping.get("counterparty", ""),
            "date_format": batch.date_format,
        }

    if request.method == "POST":
        form = MappingForm(request.POST, headers=headers, initial=initial)
        if form.is_valid():
            mapping = {
                "date": form.cleaned_data["date_column"],
                "amount": form.cleaned_data["amount_column"],
            }
            if form.cleaned_data.get("description_column"):
                mapping["description"] = form.cleaned_data["description_column"]
            if form.cleaned_data.get("counterparty_column"):
                mapping["counterparty"] = form.cleaned_data["counterparty_column"]

            batch.column_mapping = mapping
            batch.date_format = form.cleaned_data["date_format"]
            batch.status = ImportBatch.Status.MAPPED
            batch.save(update_fields=["column_mapping", "date_format", "status"])

            if form.cleaned_data.get("save_as_template"):
                ImportMappingTemplate.objects.update_or_create(
                    household=request.household,
                    name=form.cleaned_data["template_name"],
                    defaults={
                        "column_mapping": mapping,
                        "date_format": batch.date_format,
                        "delimiter": batch.delimiter,
                    },
                )
            return redirect("imports_app:preview", pk=batch.pk)
    else:
        form = MappingForm(headers=headers, initial=initial)

    return render(request, "imports_app/map_columns.html", {"form": form, "batch": batch, "headers": headers})


@household_required
def preview(request, pk):
    batch = get_object_or_404(ImportBatch.objects.for_household(request.household), pk=pk)
    if not batch.column_mapping:
        return redirect("imports_app:map_columns", pk=batch.pk)

    rows = parse_rows(batch.file, batch.column_mapping, batch.date_format, delimiter=batch.delimiter)
    rows = mark_duplicates(rows, batch.account)

    if request.method == "POST":
        imported, skipped = import_rows(rows, batch)
        batch.status = ImportBatch.Status.CONFIRMED
        batch.imported_count = imported
        batch.skipped_duplicate_count = skipped
        batch.save(update_fields=["status", "imported_count", "skipped_duplicate_count"])
        messages.success(
            request, f"{imported} transactions importées, {skipped} lignes ignorées (doublons/erreurs)."
        )
        return redirect("budget:account_detail", pk=batch.account_id)

    error_count = sum(1 for r in rows if "error" in r)
    duplicate_count = sum(1 for r in rows if r.get("is_duplicate"))
    return render(
        request,
        "imports_app/preview.html",
        {
            "batch": batch,
            "rows": rows,
            "error_count": error_count,
            "duplicate_count": duplicate_count,
        },
    )
