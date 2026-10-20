"""Rename col4/5/6, add respond_code, make text columns NOT NULL, add Import batches and indexes.

Hand-written so renames keep the data. Apply with: python manage.py migrate
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def clean_existing(apps, schema_editor):
    """NULL -> '' and the literal text 'nan' (left by the old import) -> ''."""
    Claim = apps.get_model("core", "Claim")
    for field in ("col1", "col2", "col3", "trxn_code", "merchant"):
        Claim.objects.filter(**{f"{field}__isnull": True}).update(**{field: ""})
        Claim.objects.filter(**{field: "nan"}).update(**{field: ""})


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameField("claim", "col4", "amount"),
        migrations.RenameField("claim", "col5", "trxn_code"),
        migrations.RenameField("claim", "col6", "merchant"),
        migrations.AddField(
            "claim", "respond_code",
            models.CharField(blank=True, db_index=True, default="", max_length=20),
        ),
        migrations.RunPython(clean_existing, migrations.RunPython.noop),
        migrations.AlterField("claim", "col1", models.CharField(blank=True, default="", max_length=200)),
        migrations.AlterField("claim", "col2", models.CharField(blank=True, default="", max_length=200)),
        migrations.AlterField("claim", "col3", models.CharField(blank=True, default="", max_length=200)),
        migrations.AlterField("claim", "trxn_code", models.CharField(blank=True, db_index=True, default="", max_length=50)),
        migrations.AlterField("claim", "merchant", models.CharField(blank=True, default="", max_length=200)),
        migrations.CreateModel(
            name="Import",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("filename", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("row_count", models.PositiveIntegerField(default=0)),
                ("uploaded_by", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddField(
            "claim", "batch",
            models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name="claims", to="core.import"),
        ),
        migrations.AddIndex(
            "claim",
            models.Index(fields=["amount", "merchant"], name="core_claim_amount_merchant_idx"),
        ),
    ]
