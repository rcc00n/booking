from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models import Appointment, PaymentStatus, UserProfile
from core.signals import ensure_payment_statuses


class PaymentStatusSignalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = get_user_model().objects.create_user(username="status-client", password="pass123")
        cls.profile = getattr(user, "userprofile", None)
        if cls.profile is None:
            cls.profile = UserProfile.objects.create(user=user)

    def test_duplicate_payment_statuses_are_deduplicated(self):
        primary = PaymentStatus.objects.create(name="Not Paid")
        duplicate = PaymentStatus.objects.create(name="Not Paid")
        appointment = Appointment.objects.create(client=self.profile, payment_status=duplicate)

        ensure_payment_statuses(sender=None)

        statuses = PaymentStatus.objects.filter(name="Not Paid")
        self.assertEqual(statuses.count(), 1)
        appointment.refresh_from_db()
        self.assertEqual(appointment.payment_status, statuses.first())
