from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from core.validators import clean_ab_postal_code


class PostalCodeValidatorTests(SimpleTestCase):
    def test_accepts_mixed_case_with_spacing(self):
        self.assertEqual(clean_ab_postal_code(" t2x 1a1 "), "T2X1A1")

    def test_rejects_non_alberta_prefix(self):
        with self.assertRaises(ValidationError):
            clean_ab_postal_code("V2X1A1")

    def test_rejects_short_values(self):
        with self.assertRaises(ValidationError):
            clean_ab_postal_code("T2X1A")
