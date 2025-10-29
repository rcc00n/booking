from __future__ import annotations

import json
from decimal import Decimal
from datetime import datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import (
    Appointment,
    BookingCart,
    BookingCartItem,
    ClientCard,
    MasterProfile,
    MasterWorkDay,
    Payment,
    Service,
    ServiceCategory,
    ServiceMaster,
)
from core.tests.utils import assign_service_room
from core.payments import stripe_api
from core.payments.stripe_api import _ensure_appointment_from_cart


class MetadataUtilityTests(TestCase):
    def test_safe_meta_truncates_and_stringifies(self):
        oversized = "x" * (stripe_api._MAX_META_LEN + 80)
        payload = {
            "user_id": 42,
            "details": {"nested": ["a", "b"]},
            "oversized": oversized,
        }

        safe = stripe_api._safe_meta(payload)

        self.assertEqual(safe["user_id"], "42")
        self.assertEqual(safe["details"], json.dumps({"nested": ["a", "b"]}, separators=(",", ":")))
        self.assertLessEqual(len(safe["oversized"]), stripe_api._MAX_META_LEN + 1)
        self.assertTrue(safe["oversized"].endswith("…") or safe["oversized"].endswith("..."))

    def test_safe_meta_prioritizes_core_keys(self):
        payload = {f"extra_{idx}": str(idx) for idx in range(60)}
        payload.update(
            {
                "appointment_id": "appt-1",
                "user_id": "user-1",
                "cart_id": "cart-1",
                "grand_total_minor": 1234,
            }
        )

        safe = stripe_api._safe_meta(payload)

        self.assertLessEqual(len(safe), 45)
        for key in ("appointment_id", "user_id", "cart_id", "grand_total_minor"):
            self.assertIn(key, safe)

    def test_compact_cart_metadata_generates_compact_summary(self):
        pricing = {
            "currency": "cad",
            "grand_total_minor": 15000,
            "tax_minor": 900,
            "processing_fee_minor": 300,
            "service_fee_minor": 0,
            "subtotal_minor": 13800,
            "discount_minor": 0,
            "item_count": 5,
            "items": [
                {"name": "Service A", "total_minor": 5000, "base_minor": 5000, "discount_minor": 0},
                {"name": "Service B", "total_minor": 4000, "base_minor": 4500, "discount_minor": 500},
                {"name": "Service C", "total_minor": 3000, "base_minor": 3000, "discount_minor": 0},
            ],
        }

        meta = stripe_api._compact_cart_metadata(
            user_id=7,
            cart_id=11,
            pricing=pricing,
            prepayment_percent=50,
            partial_total_minor=7500,
            appointment_id="appt-7",
            cart_finalized=True,
        )

        self.assertTrue(all(isinstance(value, str) for value in meta.values()))
        self.assertEqual(meta["user_id"], "7")
        self.assertEqual(meta["cart_finalized"], "true")
        summary = json.loads(meta["cart_pricing"])
        self.assertLessEqual(len(summary.get("items", [])), 3)


class DummyStripeObject:
    """Lightweight stand-in for stripe resources."""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def to_dict_recursive(self):
        def convert(value):
            if isinstance(value, DummyStripeObject):
                return value.to_dict_recursive()
            if isinstance(value, SimpleNamespace):
                return {k: convert(getattr(value, k)) for k in vars(value)}
            if isinstance(value, list):
                return [convert(v) for v in value]
            if isinstance(value, dict):
                return {k: convert(v) for k, v in value.items()}
            return value

        return {k: convert(v) for k, v in self.__dict__.items()}


@override_settings(STRIPE_SECRET_KEY='sk_test', STRIPE_WEBHOOK_SECRET='wh_test')
class StripeWebhookTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('client@example.com', password='pass123', email='client@example.com')
        self.profile = self.user.userprofile

        master_user = User.objects.create_user('master@example.com', password='pass123', email='master@example.com')
        master_user.first_name = 'Master'
        master_user.last_name = 'Stylist'
        master_user.save(update_fields=['first_name', 'last_name'])
        master_user.userprofile.username = master_user.username
        self.master_profile = MasterProfile.objects.create(user=master_user.userprofile)
        for weekday in range(7):
            MasterWorkDay.objects.create(
                master=self.master_profile,
                weekday=weekday,
                start_time=time(8, 0),
                end_time=time(20, 0),
            )

        category = ServiceCategory.objects.create(name='Cuts')
        self.service = Service.objects.create(
            name='Service',
            base_price=Decimal('50.00'),
            duration_min=30,
            category=category,
        )
        assign_service_room(self.service, room_name="Stripe Webhook Room")
        ServiceMaster.objects.create(service=self.service, master=self.master_profile)

        cart = BookingCart.for_user(self.profile)
        start_dt = timezone.make_aware(
            datetime.combine((timezone.now() + timedelta(days=1)).date(), time(12, 0)),
            timezone.get_current_timezone(),
        )
        BookingCartItem.objects.create(
            cart=cart,
            service=self.service,
            master=self.master_profile,
            start_time=start_dt,
        )

    def _fake_intent(self, metadata: dict, *, payment_method: str = 'pm_card_visa', amount_minor: int = 5200):
        charges = SimpleNamespace(data=[{
            'id': 'ch_test',
            'amount_refunded': 0,
            'receipt_url': 'https://stripe.test/receipt',
            'payment_method': payment_method,
            'created': int(timezone.now().timestamp()),
        }])
        intent = DummyStripeObject(
            id='pi_test',
            amount=amount_minor,
            amount_received=amount_minor,
            currency='cad',
            customer='cus_test',
            metadata=metadata,
            livemode=False,
            payment_method=payment_method,
        )
        intent.charges = charges
        return intent

    def _fake_payment_method(self, funding: str = 'credit'):
        return DummyStripeObject(
            id='pm_card_visa',
            card={
                'brand': 'visa',
                'last4': '4242',
                'exp_month': 12,
                'exp_year': 2030,
                'funding': funding,
            },
        )

    @patch('core.payments.stripe_api.stripe.PaymentMethod.retrieve')
    @patch('core.payments.stripe_api.stripe.PaymentIntent.retrieve')
    @patch('core.payments.stripe_api.stripe.Webhook.construct_event')
    def test_webhook_succeeded_creates_payment_and_appointment(self, mock_construct, mock_retrieve_intent, mock_retrieve_pm):
        metadata = {
            'user_id': str(self.profile.pk),
            'cart_id': str(self.profile.booking_cart.pk),
        }
        mock_construct.return_value = {
            'type': 'payment_intent.succeeded',
            'data': {'object': {'id': 'pi_test'}},
        }
        mock_retrieve_intent.return_value = self._fake_intent(metadata)
        mock_retrieve_pm.return_value = self._fake_payment_method()

        response = self.client.post(
            '/stripe/webhook/',
            data=b'{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='sig',
        )
        self.assertEqual(response.status_code, 200)

        payment = Payment.objects.get(stripe_payment_intent_id='pi_test')
        self.assertEqual(payment.amount, Decimal('52.00'))
        self.assertEqual(payment.method.name, 'Credit card')
        self.assertEqual(payment.receipt_url, 'https://stripe.test/receipt')

        appointment = payment.appointment
        self.assertIsNotNone(appointment)
        self.assertEqual(appointment.client, self.profile)
        self.assertEqual(appointment.items.count(), 1)

        cart = BookingCart.for_user(self.profile)
        self.assertEqual(cart.items.count(), 0)

        card = ClientCard.objects.get(stripe_payment_method_id='pm_card_visa')
        self.assertEqual(card.last4, '4242')
        self.assertTrue(card.is_default)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.stripe_customer_id, 'cus_test')

    @patch('core.payments.stripe_api.stripe.PaymentIntent.retrieve')
    @patch('core.payments.stripe_api.stripe.Webhook.construct_event')
    def test_webhook_payment_failed_creates_failed_payment(self, mock_construct, mock_retrieve_intent):
        metadata = {'user_id': str(self.profile.pk)}
        mock_construct.return_value = {
            'type': 'payment_intent.payment_failed',
            'data': {'object': {'id': 'pi_fail'}},
        }
        intent = self._fake_intent(metadata, payment_method='pm_card_visa', amount_minor=5200)
        intent.id = 'pi_fail'
        intent.status = 'payment_failed'
        intent.amount_received = 0
        intent.charges = SimpleNamespace(data=[])
        intent.payment_method = None
        mock_retrieve_intent.return_value = intent

        response = self.client.post(
            '/stripe/webhook/',
            data=b'{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='sig',
        )
        self.assertEqual(response.status_code, 200)

        payment = Payment.objects.get(stripe_payment_intent_id='pi_fail')
        self.assertEqual(payment.status, 'payment_failed')
        self.assertIsNone(payment.appointment)
        self.assertEqual(payment.amount, Decimal('52.00'))

    @override_settings(STRIPE_SECRET_KEY='sk_test', STRIPE_WEBHOOK_SECRET='wh_test')
    @patch('core.payments.stripe_api.stripe.PaymentMethod.retrieve')
    @patch('core.payments.stripe_api.stripe.PaymentIntent.create')
    def test_no_show_charge_creates_payment(self, mock_create_intent, mock_retrieve_pm):
        User = get_user_model()
        staff = User.objects.create_user('staff@example.com', password='pass123', email='staff@example.com', is_staff=True)
        self.client.force_login(staff)

        appointment = Appointment.objects.create(
            client=self.profile,
            start_time=timezone.now(),
            final_price=Decimal('120.00'),
        )
        ClientCard.objects.create(
            client=self.profile,
            stripe_customer_id='cus_test',
            stripe_payment_method_id='pm_card_visa',
            brand='visa',
            last4='4242',
            exp_month=12,
            exp_year=2030,
            funding='credit',
            is_default=True,
        )

        charges = SimpleNamespace(data=[{
            'id': 'ch_no_show',
            'amount_refunded': 0,
            'receipt_url': 'https://stripe.test/no-show',
            'payment_method': 'pm_card_visa',
            'created': int(timezone.now().timestamp()),
        }])
        intent = DummyStripeObject(
            id='pi_no_show',
            client_secret='secret',
            status='succeeded',
            livemode=False,
            payment_method='pm_card_visa',
            amount=6000,
            amount_received=6000,
            currency='cad',
            metadata={'appointment_id': str(appointment.pk), 'user_id': str(self.profile.pk)},
        )
        intent.charges = charges
        mock_create_intent.return_value = intent
        mock_retrieve_pm.return_value = self._fake_payment_method()

        response = self.client.post(
            '/accounts/api/payments/no-show/charge/',
            data=json.dumps({'appointment_id': str(appointment.pk)}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.json())

        payment = Payment.objects.get(stripe_payment_intent_id='pi_no_show')
        self.assertEqual(payment.amount, Decimal('60.00'))
        self.assertEqual(payment.method.name, 'Credit card')
        self.assertEqual(payment.receipt_url, 'https://stripe.test/no-show')
        self.assertEqual(payment.appointment, appointment)

        appointment.refresh_from_db()
        self.assertEqual(appointment.payment_status.name, 'Paid')

        expected_minor = int(Decimal('120.00') * Decimal('0.5') * Decimal('100'))
        self.assertEqual(mock_create_intent.call_args.kwargs['amount'], expected_minor)


@override_settings(STRIPE_SECRET_KEY='sk_test', STRIPE_WEBHOOK_SECRET='wh_test')
class StripeFinalizeCartTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('finalize@example.com', password='pass123', email='finalize@example.com')
        self.client.force_login(self.user)
        self.profile = self.user.userprofile

        master_user = User.objects.create_user('finalize-master@example.com', password='pass123', email='finalize-master@example.com')
        master_user.first_name = 'Master'
        master_user.last_name = 'Finalizer'
        master_user.save(update_fields=['first_name', 'last_name'])
        self.master_profile = MasterProfile.objects.create(user=master_user.userprofile)
        for weekday in range(6):
            MasterWorkDay.objects.create(
                master=self.master_profile,
                weekday=weekday,
                start_time=time(8, 0),
                end_time=time(20, 0),
            )

        category = ServiceCategory.objects.create(name='Finalize')
        self.service = Service.objects.create(
            name='Finalize Service',
            base_price=Decimal('75.00'),
            duration_min=30,
            category=category,
        )
        assign_service_room(self.service, room_name="Stripe Finalize Room")
        ServiceMaster.objects.create(service=self.service, master=self.master_profile)

    def _next_available_start(self):
        base = timezone.now()
        for offset in range(1, 8):
            candidate = base + timedelta(days=offset)
            if candidate.weekday() < 6:  # masters work Mon-Sat in tests
                local_dt = datetime.combine(candidate.date(), time(12, 0))
                return timezone.make_aware(local_dt, timezone.get_current_timezone())
        local_dt = datetime.combine((base + timedelta(days=1)).date(), time(12, 0))
        return timezone.make_aware(local_dt, timezone.get_current_timezone())

    def _create_cart_item(self, start=None):
        cart = BookingCart.for_user(self.profile)
        start_time = start or self._next_available_start()
        return BookingCartItem.objects.create(
            cart=cart,
            service=self.service,
            master=self.master_profile,
            start_time=start_time,
        )

    @patch('core.payments.stripe_api.stripe.PaymentIntent.modify')
    @patch('core.payments.stripe_api._fetch_intent')
    def test_finalize_cart_creates_appointment(self, mock_fetch_intent, mock_modify):
        item = self._create_cart_item()
        cart = item.cart
        intent = DummyStripeObject(
            id='pi_finalize',
            metadata={
                'user_id': str(self.profile.pk),
                'cart_id': str(cart.pk),
            },
        )
        mock_fetch_intent.return_value = intent

        with patch('core.signals._send_email'):
            response = self.client.post(
                '/accounts/api/payments/cart/finalize/',
                data=json.dumps({
                    'payment_intent_id': 'pi_finalize',
                    'cart_id': str(cart.pk),
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload.get('ok'))
        self.assertFalse(payload.get('already_finalized'))

        appointment_id = payload['appointment']['id']
        appointment = Appointment.objects.get(pk=appointment_id)
        self.assertEqual(appointment.client, self.profile)
        self.assertFalse(cart.items.exists())
        mock_modify.assert_called_once()

    @patch('core.payments.stripe_api.stripe.PaymentIntent.modify')
    @patch('core.payments.stripe_api._fetch_intent')
    def test_finalize_cart_returns_existing_appointment(self, mock_fetch_intent, mock_modify):
        item = self._create_cart_item()
        cart = item.cart
        with patch('core.signals._send_email'):
            appointment, _ = _ensure_appointment_from_cart(
                self.profile,
                {"cart_id": str(cart.pk)},
            )
        self.assertIsNotNone(appointment)
        self.assertFalse(cart.items.exists())

        intent = DummyStripeObject(
            id='pi_finalize_existing',
            metadata={
                'user_id': str(self.profile.pk),
                'cart_id': str(cart.pk),
                'appointment_id': str(appointment.pk),
            },
        )
        mock_fetch_intent.return_value = intent

        response = self.client.post(
            '/accounts/api/payments/cart/finalize/',
            data=json.dumps({
                'payment_intent_id': 'pi_finalize_existing',
                'cart_id': str(cart.pk),
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload.get('already_finalized'))
        self.assertEqual(payload['appointment']['id'], str(appointment.pk))
        mock_modify.assert_called_once()
