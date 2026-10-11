from django.contrib import admin

from .models import ImportBatch


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    # raw_file excluded on purpose -- never render a statement's bytes in
    # the admin list/detail view.
    list_display = ["id", "user", "account", "status", "source_format", "rows_imported", "created_at"]
    list_filter = ["status", "source_format"]
    exclude = ["raw_file"]
    readonly_fields = [
        "user", "account", "source_format", "original_filename", "column_mapping",
        "rows_detected", "rows_imported", "rows_duplicate_skipped", "rows_flagged",
        "validation_summary", "error_message", "committed_at",
    ]
