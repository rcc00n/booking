from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0016_userprofile_email_verified_at_emailverification"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="receipt_pdf",
            field=models.FileField(blank=True, null=True, upload_to="receipts/%Y/%m/"),
        ),
        migrations.AddField(
            model_name="payment",
            name="receipt_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

