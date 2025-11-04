from __future__ import annotations

from decimal import Decimal

from django.test import SimpleTestCase

from core.utils.fees import (
    CARD_PROCESSING_FIXED,
    CARD_PROCESSING_PERCENT,
    card_processing_fee,
    quantize,
    total_with_processing_fee,
)


class FeeUtilsTests(SimpleTestCase):
    def test_quantize_handles_multiple_input_types(self) -> None:
        self.assertEqual(quantize(10), Decimal("10.00"))
        self.assertEqual(quantize(Decimal("3.456")), Decimal("3.46"))
        self.assertEqual(quantize("2.3"), Decimal("2.30"))
        self.assertEqual(quantize(None), Decimal("0.00"))

    def test_card_processing_fee_applies_percent_and_fixed_components(self) -> None:
        base = Decimal("120.00")
        fee = card_processing_fee(base)
        expected = quantize(base * CARD_PROCESSING_PERCENT + CARD_PROCESSING_FIXED)
        self.assertEqual(fee, expected)

    def test_card_processing_fee_clamps_non_positive_values(self) -> None:
        self.assertEqual(card_processing_fee(0), Decimal("0.00"))
        self.assertEqual(card_processing_fee(-50), Decimal("0.00"))

    def test_total_with_processing_fee_combines_amount_and_fee(self) -> None:
        amount = Decimal("80.00")
        result = total_with_processing_fee(amount)
        self.assertEqual(result, amount + card_processing_fee(amount))
