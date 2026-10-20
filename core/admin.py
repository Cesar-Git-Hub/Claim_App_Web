from django.contrib import admin

from .models import Claim, Import


@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = ("col1", "col2", "amount", "trxn_code", "merchant", "respond_code", "to_delete")
    list_filter = ("trxn_code", "respond_code", "to_delete")
    search_fields = ("col1", "col2", "col3", "merchant")


@admin.register(Import)
class ImportAdmin(admin.ModelAdmin):
    list_display = ("filename", "created_at", "uploaded_by", "row_count")
    readonly_fields = ("created_at",)
