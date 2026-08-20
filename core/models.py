from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal

class Claim(models.Model):
    col1 = models.CharField(max_length=200, blank=True, null=True)   # Date Marked
    col2 = models.CharField(max_length=200, blank=True, null=True)   # Dated and Time
    col3 = models.CharField(max_length=200, blank=True, null=True)   # Account
    col4 = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    col5 = models.CharField(max_length=200, blank=True, null=True)   # Mark Type
    col6 = models.CharField(max_length=200, blank=True, null=True)   # Trxn Code
    col7 = models.CharField(max_length=200, blank=True, null=True)   # Merchants
    col8 = models.CharField(max_length=200, blank=True, null=True)   # Entry Mode
    col9 = models.CharField(max_length=200, blank=True, null=True)   # Respond Code
    col10 = models.CharField(max_length=200, blank=True, null=True)  # ECI
    col11 = models.CharField(max_length=200, blank=True, null=True)  # Approval Code
    col12 = models.CharField(max_length=200, blank=True, null=True)  # Customer ID

    to_delete = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.col3} - {self.col4} ({'Eliminar' if self.to_delete else 'OK'})"

