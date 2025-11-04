from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.forms.models import model_to_dict
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.utils import timezone

from core.filters import ClientStatusFilter, MasterRoleFilter, StaffSetByFilter
from core.forms import AppointmentItemAdminForm, EDITABLE_FIELDS_FOR_MASTER, _normalize_phone
from core.models import (
    Appointment,
    AppointmentItem,
    AppointmentItemStatus,
    AppointmentItemStatusHistory,
    MasterProfile,
    MasterRoom,
    PaymentStatus,
    Role,
    Service,
    ServiceMaster,
    UserProfile,
    UserRole,
)


def _create_appointment_item(prefix: str) -> tuple[AppointmentItem, MasterProfile, MasterProfile]:
    """Helper to construct an appointment item with two masters for form/filter tests."""
    user_model = get_user_model()

    client_user = user_model.objects.create_user(username=f"{prefix}-client", password="pass123")
    client_profile = UserProfile.objects.create(user=client_user)

    owner_user = user_model.objects.create_user(username=f"{prefix}-owner", password="pass123")
    owner_profile = UserProfile.objects.create(user=owner_user)
    owner_master = MasterProfile.objects.create(user=owner_profile)

    other_user = user_model.objects.create_user(username=f"{prefix}-other", password="pass123")
    other_profile = UserProfile.objects.create(user=other_user)
    other_master = MasterProfile.objects.create(user=other_profile)

    payment_status, _ = PaymentStatus.objects.get_or_create(name="Not Paid")

    service = Service.objects.create(
        name=f"Service {prefix}",
        base_price=Decimal("95.00"),
        duration_min=45,
    )
    room = MasterRoom.objects.create(room=f"Room {prefix}")
    service.allowed_rooms.add(room)
    ServiceMaster.objects.create(service=service, master=owner_master)

    appointment = Appointment.objects.create(
        client=client_profile,
        payment_status=payment_status,
        start_time=timezone.now(),
    )

    item = AppointmentItem.objects.create(
        appointment=appointment,
        service=service,
        master=owner_master,
        start_time=timezone.now(),
        unit_price=Decimal("95.00"),
    )
    return item, owner_master, other_master


class NormalizePhoneTests(SimpleTestCase):
    def test_normalizes_e164(self) -> None:
        normalized = _normalize_phone("(403) 555-0101")
        self.assertEqual(normalized, "+14035550101")

    def test_rejects_invalid_numbers(self) -> None:
        with self.assertRaises(ValidationError):
            _normalize_phone("invalid-number")


class AppointmentItemAdminFormTests(TestCase):
    def setUp(self) -> None:
        self.item, self.owner_master, self.other_master = _create_appointment_item("admin-form")

    def _form_payload(self, *, new_start=None, **overrides) -> dict[str, object]:
        base_dict = model_to_dict(self.item, fields=["appointment", "service", "master", "start_time", "unit_price"])
        start_time = new_start or self.item.start_time
        data = {
            "appointment": str(base_dict["appointment"]),
            "service": str(base_dict["service"]),
            "master": str(base_dict["master"]),
            "status": "",
            "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "unit_price": str(base_dict["unit_price"]),
            "validation_enabled": "on",
            "duration_override_min": "",
            "manual_discount_percent": "0",
        }
        data.update({key: value for key, value in overrides.items() if value is not None})
        return data

    def test_master_cannot_edit_other_users_item(self) -> None:
        payload = self._form_payload(unit_price="150.00")
        form = AppointmentItemAdminForm(
            data=payload,
            instance=self.item,
            user=self.other_master.user,
        )
        for field_name in EDITABLE_FIELDS_FOR_MASTER:
            if field_name in form.fields:
                form.fields[field_name].disabled = False

        self.assertFalse(form.is_valid())
        self.assertIn("Вы не можете редактировать позиции другого мастера.", form.non_field_errors())

    def test_master_can_edit_own_item(self) -> None:
        payload = self._form_payload(unit_price="110.00")
        form = AppointmentItemAdminForm(
            data=payload,
            instance=self.item,
            user=self.owner_master.user,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["master"], self.owner_master)


class AdminFilterTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.user_model = get_user_model()

    def test_client_status_filter_matches_new_clients(self) -> None:
        new_user = self.user_model.objects.create_user(username="new-client", password="pass123")
        UserProfile.objects.create(user=new_user)

        regular_user = self.user_model.objects.create_user(username="regular-client", password="pass123")
        regular_user.date_joined = timezone.now() - timedelta(days=60)
        regular_user.save(update_fields=["date_joined"])
        UserProfile.objects.create(user=regular_user)

        request = self.factory.get("/", {"client_status": "new"})
        filt = ClientStatusFilter(request, request.GET.copy(), self.user_model, None)
        qs = filt.queryset(request, self.user_model.objects.order_by("id"))

        self.assertEqual(list(qs), [new_user])

    def test_master_role_filter_returns_profiles_with_role(self) -> None:
        role = Role.objects.create(name="Master")
        master_user = self.user_model.objects.create_user(username="master-role", password="pass123")
        master_profile = UserProfile.objects.create(user=master_user)
        UserRole.objects.create(user=master_profile, role=role)

        other_user = self.user_model.objects.create_user(username="non-master", password="pass123")
        other_profile = UserProfile.objects.create(user=other_user)

        request = self.factory.get("/", {"is_master": "yes"})
        filt = MasterRoleFilter(request, request.GET.copy(), UserProfile, None)
        qs = filt.queryset(request, UserProfile.objects.order_by("pk"))

        self.assertEqual(list(qs), [master_profile])

    def test_staff_set_by_filter_limits_queryset(self) -> None:
        item, owner_master, other_master = _create_appointment_item("status-filter")
        status, _ = AppointmentItemStatus.objects.update_or_create(code="BOOKED", defaults={"name": "Booked"})

        staff_user = owner_master.user.user
        staff_user.is_staff = True
        staff_user.save(update_fields=["is_staff"])

        entry_staff = AppointmentItemStatusHistory.objects.create(
            item=item,
            status=status,
            set_by=staff_user,
        )
        AppointmentItemStatusHistory.objects.create(
            item=item,
            status=status,
            set_by=None,
        )

        request = self.factory.get("/", {"set_by": str(owner_master.user.pk)})
        filt = StaffSetByFilter(request, request.GET.copy(), AppointmentItemStatusHistory, None)
        qs = filt.queryset(request, AppointmentItemStatusHistory.objects.order_by("id"))

        self.assertEqual(list(qs), [entry_staff])
