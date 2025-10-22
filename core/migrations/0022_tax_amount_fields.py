from decimal import Decimal

from django.conf import settings
from django.db import migrations, models


TWOPLACES = Decimal("0.01")


def populate_tax_fields(apps, schema_editor):
    Appointment = apps.get_model("core", "Appointment")
    AppointmentItem = apps.get_model("core", "AppointmentItem")
    ProductSale = apps.get_model("core", "ProductSale")

    percent = getattr(settings, "GST_PERCENT", Decimal("5.0"))
    enabled = getattr(settings, "GST_ENABLED", True)

    def compute_tax(amount: Decimal) -> Decimal:
        if not enabled:
            return Decimal("0.00")
        return (amount * percent / Decimal("100")).quantize(TWOPLACES)

    for item in AppointmentItem.objects.select_related("service"):
        base = Decimal(getattr(item, "final_price", Decimal("0.00")) or Decimal("0.00"))
        service = getattr(item, "service", None)
        taxable = bool(getattr(service, "is_taxable", False))
        tax = compute_tax(base) if taxable else Decimal("0.00")
        item.tax_amount = tax
        item.save(update_fields=["tax_amount"])

    for sale in ProductSale.objects.all():
        base = Decimal(getattr(sale, "total_amount", Decimal("0.00")) or Decimal("0.00"))
        tax = compute_tax(base)
        sale.tax_amount = tax
        sale.save(update_fields=["tax_amount"])

    for appointment in Appointment.objects.all():
        subtotal = Decimal("0.00")
        tax_total = Decimal("0.00")
        for item in appointment.items.all():
            subtotal += Decimal(getattr(item, "final_price", Decimal("0.00")) or Decimal("0.00"))
            tax_total += Decimal(getattr(item, "tax_amount", Decimal("0.00")) or Decimal("0.00"))
        for sale in appointment.product_sales.all():
            subtotal += Decimal(getattr(sale, "total_amount", Decimal("0.00")) or Decimal("0.00"))
            tax_total += Decimal(getattr(sale, "tax_amount", Decimal("0.00")) or Decimal("0.00"))
        appointment.tax_amount = tax_total.quantize(TWOPLACES)
        appointment.final_price = (subtotal + tax_total).quantize(TWOPLACES)
        appointment.save(update_fields=["tax_amount", "final_price"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0021_service_is_taxable"),
    ]

    operations = [
        migrations.AddField(
            model_name="appointmentitem",
            name="tax_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), editable=False, max_digits=10),
        ),
        migrations.AddField(
            model_name="appointment",
            name="tax_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), editable=False, max_digits=10),
        ),
        migrations.AddField(
            model_name="productsale",
            name="tax_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), editable=False, max_digits=12),
        ),
        migrations.RunPython(populate_tax_fields, migrations.RunPython.noop),
    ]
