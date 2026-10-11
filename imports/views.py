from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction as db_transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from transactions.models import Account
from transactions.services import record_transaction

from . import pipeline
from .forms import AccountSelectForm, UploadForm, build_column_mapping_form
from .models import ImportBatch, MAX_RAW_FILE_BYTES


def _get_batch(request, pk):
    return get_object_or_404(ImportBatch, pk=pk, user=request.user)


def _parsed_rows(batch):
    text = pipeline.decode_text(bytes(batch.raw_file))
    rows = pipeline.parse_rows(text, batch.column_mapping, account_id=batch.account_id)
    pipeline.detect_duplicates(rows, batch.account)
    return rows


@login_required
def upload(request):
    if request.method == "POST":
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            upload_file = form.cleaned_data["file"]
            content = upload_file.read()
            try:
                pipeline.validate_file(upload_file.name, content, MAX_RAW_FILE_BYTES)
            except pipeline.ImportValidationError as exc:
                form.add_error("file", str(exc))
            else:
                batch = ImportBatch.objects.create(
                    user=request.user,
                    original_filename=upload_file.name[:255],
                    raw_file=content,
                    started_from_onboarding=request.GET.get("from") == "onboarding",
                )
                return redirect("imports:choose_account", pk=batch.pk)
    else:
        form = UploadForm()
    return render(request, "imports/upload.html", {"form": form})


@login_required
def choose_account(request, pk):
    batch = _get_batch(request, pk)
    if batch.status != ImportBatch.Status.DRAFT:
        return redirect("imports:history")
    if request.method == "POST":
        form = AccountSelectForm(request.POST, user=request.user)
        if form.is_valid():
            account = form.cleaned_data.get("existing_account")
            if account is None:
                account = Account.objects.create(
                    user=request.user,
                    institution_name=form.cleaned_data["institution_name"],
                    account_holder_name=request.user.get_full_name() or request.user.username,
                    account_type=form.cleaned_data["account_type"],
                    masked_number=f"••••{form.cleaned_data['masked_number']}",
                    opening_balance=form.cleaned_data["opening_balance"] or 0,
                )
            batch.account = account
            batch.save(update_fields=["account", "updated_at"])
            return redirect("imports:map_columns", pk=batch.pk)
    else:
        form = AccountSelectForm(user=request.user)
    return render(request, "imports/choose_account.html", {"form": form, "batch": batch})


@login_required
def map_columns(request, pk):
    batch = _get_batch(request, pk)
    if batch.status != ImportBatch.Status.DRAFT:
        return redirect("imports:history")
    if batch.account_id is None:
        return redirect("imports:choose_account", pk=batch.pk)
    text = pipeline.decode_text(bytes(batch.raw_file))
    headers = pipeline.read_headers(text)
    initial = batch.column_mapping or pipeline.detect_columns(headers)
    if request.method == "POST":
        form = build_column_mapping_form(headers, initial, data=request.POST)
        if form.is_valid():
            mapping = {role: value for role, value in form.cleaned_data.items() if value}
            problems = pipeline.validate_mapping(mapping)
            if problems:
                for problem in problems:
                    messages.error(request, problem)
            else:
                batch.column_mapping = mapping
                batch.save(update_fields=["column_mapping", "updated_at"])
                return redirect("imports:preview", pk=batch.pk)
    else:
        form = build_column_mapping_form(headers, initial)
    return render(request, "imports/map_columns.html", {"form": form, "batch": batch, "headers": headers})


@login_required
def preview(request, pk):
    batch = _get_batch(request, pk)
    if batch.status != ImportBatch.Status.DRAFT:
        return redirect("imports:batch_detail", pk=batch.pk)
    if batch.account_id is None:
        return redirect("imports:choose_account", pk=batch.pk)
    if not batch.column_mapping:
        return redirect("imports:map_columns", pk=batch.pk)

    rows = _parsed_rows(batch)
    summary = pipeline.summarize(rows)

    if request.method == "POST":
        included = set(request.POST.getlist("include"))
        imported = 0
        duplicates_skipped = 0
        flagged = 0
        try:
            with db_transaction.atomic():
                for row in rows:
                    if row.needs_review:
                        flagged += 1
                        continue
                    if row.is_duplicate:
                        duplicates_skipped += 1
                        continue
                    if str(row.row_number) not in included:
                        continue
                    _, created = record_transaction(
                        request.user,
                        kind=row.kind,
                        amount=row.amount,
                        occurred_on=row.occurred_on,
                        description=row.description,
                        source="imported",
                        external_id=row.external_id,
                        account=batch.account,
                    )
                    if created:
                        imported += 1
                batch.status = ImportBatch.Status.COMMITTED
                batch.rows_detected = summary.detected
                batch.rows_imported = imported
                batch.rows_duplicate_skipped = duplicates_skipped
                batch.rows_flagged = flagged
                batch.committed_at = timezone.now()
                batch.validation_summary = _warnings_for(rows)
                batch.save()
        except Exception:
            batch.status = ImportBatch.Status.FAILED
            batch.error_message = "Something went wrong while saving these transactions. Nothing was imported -- you can retry."
            batch.save(update_fields=["status", "error_message", "updated_at"])
            messages.error(request, batch.error_message)
            return redirect("imports:batch_detail", pk=batch.pk)

        messages.success(
            request,
            f"Imported {imported} transaction(s). {duplicates_skipped} duplicate(s) skipped, {flagged} row(s) need review.",
        )
        return redirect("imports:batch_detail", pk=batch.pk)

    return render(
        request,
        "imports/preview.html",
        {"batch": batch, "rows": rows, "summary": summary},
    )


def _warnings_for(rows) -> list:
    warnings = []
    for row in rows:
        for err in row.errors:
            warnings.append(f"Row {row.row_number}: {err}")
        if row.is_ambiguous:
            warnings.append(f"Row {row.row_number}: looks like it might duplicate another row -- needs review.")
    return warnings[:200]


@login_required
def batch_detail(request, pk):
    batch = get_object_or_404(ImportBatch, pk=pk, user=request.user)
    return render(request, "imports/batch_detail.html", {"batch": batch})


@login_required
def history(request):
    batches = ImportBatch.objects.filter(user=request.user).select_related("account")
    return render(request, "imports/history.html", {"batches": batches})


@login_required
@require_POST
def retry(request, pk):
    batch = get_object_or_404(ImportBatch, pk=pk, user=request.user)
    if batch.status != ImportBatch.Status.FAILED:
        messages.error(request, "Only a failed import can be retried.")
        return redirect("imports:history")
    if not batch.raw_file:
        messages.error(request, "The source file for this import was deleted, so it can't be retried. Upload it again.")
        return redirect("imports:upload")
    batch.status = ImportBatch.Status.DRAFT
    batch.error_message = ""
    batch.save(update_fields=["status", "error_message", "updated_at"])
    if batch.column_mapping:
        return redirect("imports:preview", pk=batch.pk)
    return redirect("imports:map_columns", pk=batch.pk)


@login_required
@require_POST
def delete_batch(request, pk):
    batch = get_object_or_404(ImportBatch, pk=pk, user=request.user)
    if batch.status == ImportBatch.Status.COMMITTED:
        # Keep the audit trail (counts, when, which account) but drop the
        # source file itself -- the already-imported transactions are
        # independent records and are never touched.
        batch.raw_file = None
        batch.save(update_fields=["raw_file", "updated_at"])
        messages.success(request, "Source file deleted. The import record and its transactions are kept.")
    else:
        batch.delete()
        messages.success(request, "Import discarded.")
    return redirect("imports:history")
