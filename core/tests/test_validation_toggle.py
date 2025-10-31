from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import Appointment, AppointmentItem
from core.tests.test_room_allocation import ServiceRoomTestMixin
from core.validators import validate_no_time_overlap_for_same_master


class ValidationToggleTests(ServiceRoomTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.master = self._make_master("toggle-master")
        self.appointment = Appointment.objects.create(
            client=self.client_profile,
            start_time=self.base_start,
        )

    def _create_item(self, start, validation_enabled=True):
        return AppointmentItem.objects.create(
            appointment=self.appointment,
            service=self.service,
            master=self.master,
            start_time=start,
            validation_enabled=validation_enabled,
        )

    def test_validator_respects_validation_toggle(self):
        self._create_item(self.base_start)
        overlapping_item = self._create_item(
            self.base_start + timedelta(minutes=5),
            validation_enabled=False,
        )
        AppointmentItem.objects.filter(pk=overlapping_item.pk).update(
            validation_enabled=True
        )

        with self.assertRaises(ValidationError):
            validate_no_time_overlap_for_same_master(self.appointment)

        AppointmentItem.objects.filter(pk=overlapping_item.pk).update(
            validation_enabled=False
        )
        overlapping_item.refresh_from_db()

        try:
            validate_no_time_overlap_for_same_master(self.appointment)
        except ValidationError as exc:
            self.fail(f"Validator raised unexpectedly when validation disabled: {exc}")
