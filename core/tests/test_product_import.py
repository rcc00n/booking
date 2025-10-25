from __future__ import annotations

from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from core.models import Product, ProductCategory
from core.services.product_import import ProductImportSchemaError, import_products_from_file


class ProductImportTests(TestCase):
    def test_csv_import_creates_products_and_categories(self):
        payload = (
            "Product name,SKU,Description,Measure Type,Measure Value,Cost price,Full price,Category,Brand,Supplier,Total Stock\n"
            "Hydrating Serum,SRM-1,Deep moisture,ml,30,12.50,25.00,Skin Care,GlowCo,House Spa,15\n"
        )
        uploaded = SimpleUploadedFile("products.csv", payload.encode("utf-8"))

        result = import_products_from_file(uploaded)

        self.assertEqual(result.created, 1)
        self.assertEqual(result.updated, 0)
        self.assertFalse(result.errors)

        product = Product.objects.get(sku="SRM-1")
        self.assertEqual(product.name, "Hydrating Serum")
        self.assertEqual(product.description, "Deep moisture")
        self.assertEqual(product.measure_type, "ml")
        self.assertEqual(product.measure_value, "30")
        self.assertEqual(product.brand, "GlowCo")
        self.assertEqual(product.supplier, "House Spa")
        self.assertEqual(product.cost_price, Decimal("12.50"))
        self.assertEqual(product.price, Decimal("25.00"))
        self.assertEqual(product.quantity_in_stock, 15)
        self.assertEqual(ProductCategory.objects.count(), 1)
        self.assertEqual(product.category.name, "Skin Care")

    def test_import_updates_existing_product_by_sku(self):
        category = ProductCategory.objects.create(name="Skin Care")
        product = Product.objects.create(
            name="Hydrating Serum",
            sku="SRM-1",
            category=category,
            price=Decimal("20.00"),
            quantity_in_stock=5,
        )

        payload = (
            "Product name,SKU,Description,Measure Type,Measure Value,Cost price,Full price,Category,Brand,Supplier,Total Stock\n"
            "Hydrating Serum,SRM-1,Updated desc,ml,50,15.00,32.00,Skin Care,GlowCo,New Supplier,25\n"
        )
        uploaded = SimpleUploadedFile("products.csv", payload.encode("utf-8"))

        result = import_products_from_file(uploaded)

        self.assertEqual(result.created, 0)
        self.assertEqual(result.updated, 1)
        self.assertFalse(result.errors)

        product.refresh_from_db()
        self.assertEqual(product.description, "Updated desc")
        self.assertEqual(product.measure_value, "50")
        self.assertEqual(product.brand, "GlowCo")
        self.assertEqual(product.supplier, "New Supplier")
        self.assertEqual(product.cost_price, Decimal("15.00"))
        self.assertEqual(product.price, Decimal("32.00"))
        self.assertEqual(product.quantity_in_stock, 25)

    def test_missing_required_headers_raise_schema_error(self):
        payload = (
            "SKU,Description\n"
            "ABC-1,No name column\n"
        )
        uploaded = SimpleUploadedFile("bad.csv", payload.encode("utf-8"))

        with self.assertRaises(ProductImportSchemaError):
            import_products_from_file(uploaded)
