from django.db import models
from django.core.validators import MinValueValidator

class Claim(models.Model):
    col1 = models.CharField(max_length=200, blank=True, null=True)
    col2 = models.CharField(max_length=200, blank=True, null=True)
    col3 = models.CharField(max_length=200, blank=True, null=True)
    col4 = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(0)]
    )
    col5 = models.CharField(max_length=50, blank=True, null=True)
    col6 = models.CharField(max_length=50, blank=True, null=True)
    to_delete = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.col1} - {self.col5}"
