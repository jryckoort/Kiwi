from django.contrib import admin

from .models import ImportBatch, ImportMappingTemplate


@admin.register(ImportMappingTemplate)
class ImportMappingTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "household")
    list_filter = ("household",)


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ("account", "household", "uploaded_by", "status", "imported_count", "created_at")
    list_filter = ("household", "status")
