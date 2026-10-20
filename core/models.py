from django.conf import settings
from django.db import models


class Import(models.Model):
    """One uploaded file. Lets you see where rows came from and undo an import."""

    filename = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    row_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.filename} ({self.row_count} filas)"


class Claim(models.Model):
    # col1..col3 are columns A..C of the source file (meaning not defined yet; rename when known)
    col1 = models.CharField(max_length=200, blank=True, default="")
    col2 = models.CharField(max_length=200, blank=True, default="")
    col3 = models.CharField(max_length=200, blank=True, default="")
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    trxn_code = models.CharField(max_length=50, blank=True, default="", db_index=True)
    merchant = models.CharField(max_length=200, blank=True, default="")
    respond_code = models.CharField(max_length=20, blank=True, default="", db_index=True)
    # Rows flagged by an action; they are only deleted after an explicit confirmation.
    to_delete = models.BooleanField(default=False)
    batch = models.ForeignKey(Import, null=True, blank=True, on_delete=models.CASCADE, related_name="claims")

    class Meta:
        indexes = [models.Index(fields=["amount", "merchant"], name="core_claim_amount_merchant_idx")]

    def __str__(self):
        return f"{self.col1} - {self.trxn_code}"
