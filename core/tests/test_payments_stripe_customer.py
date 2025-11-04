from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import stripe
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from core.models import UserProfile
from core.payments.stripe_api import (
    _get_or_create_stripe_customer,
    _stripe_customer_exists,
)


@override_settings(STRIPE_SECRET_KEY="sk_test")
class StripeCustomerUtilitiesTests(TestCase):
    def setUp(self) -> None:
        self.user_model = get_user_model()
        stripe.api_key = None  # ensure fresh state per test

    @patch("core.payments.stripe_api._require_stripe_config")
    @patch("core.payments.stripe_api.stripe.Customer.retrieve")
    def test_stripe_customer_exists_handles_missing(self, mock_retrieve, mock_require) -> None:
        mock_retrieve.side_effect = stripe.error.InvalidRequestError(
            "No such customer", param=None, code="resource_missing"
        )

        self.assertFalse(_stripe_customer_exists("cus_missing"))
        mock_retrieve.assert_called_once_with("cus_missing")

    @patch("core.payments.stripe_api.stripe.Customer.retrieve")
    def test_get_or_create_reuses_existing_customer(self, mock_retrieve) -> None:
        user = self.user_model.objects.create_user(
            username="stripe-existing",
            email="existing@example.com",
            password="pass1234",
        )
        profile = UserProfile.objects.create(user=user, stripe_customer_id="cus_existing")
        mock_retrieve.return_value = SimpleNamespace(id="cus_existing")

        customer_id = _get_or_create_stripe_customer(profile)

        self.assertEqual(customer_id, "cus_existing")
        profile.refresh_from_db()
        self.assertEqual(profile.stripe_customer_id, "cus_existing")
        mock_retrieve.assert_called_once()

    @patch("core.payments.stripe_api.stripe.Customer.create")
    @patch("core.payments.stripe_api.stripe.Customer.retrieve")
    def test_get_or_create_creates_new_when_existing_invalid(self, mock_retrieve, mock_create) -> None:
        user = self.user_model.objects.create_user(
            username="stripe-new",
            email="new@example.com",
            password="pass1234",
        )
        profile = UserProfile.objects.create(user=user, stripe_customer_id="cus_old")

        mock_retrieve.side_effect = stripe.error.InvalidRequestError(
            "No such customer", param=None, code="resource_missing"
        )
        mock_create.return_value = SimpleNamespace(id="cus_new")

        customer_id = _get_or_create_stripe_customer(profile)

        self.assertEqual(customer_id, "cus_new")
        profile.refresh_from_db()
        self.assertEqual(profile.stripe_customer_id, "cus_new")
        mock_create.assert_called_once()
