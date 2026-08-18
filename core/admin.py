from django.contrib import admin
from .models import Claim

@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = ("col1", "col2", "col4", "col5", "to_delete")
    search_fields = ("col1", "col2", "col5")

