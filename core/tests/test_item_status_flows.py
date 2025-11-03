from __future__ import annotations

import json
from decimal import Decimal
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch, call

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse

from core.models import (
    Appointment,
    AppointmentItem,
    AppointmentItemStatusHistory,
    AppointmentStatusHistory,
    MasterProfile,
    MasterRoom,
    PaymentStatus,
    Service,
    ServiceMaster,
    UserProfile,
)
from core.services.booking import create_appointment_from_cart_items
from core.services.item_status import ensure_item_status, ensure_initial_status, EMAIL_CONFIRM_NOTE
from core.tasks import send_item_confirmation_email


class ItemStatusFlowTests(TestCase):
    def setUp(self) -> None:
        self.User = get_user_model()

    def _create_master_profile(self, username: str) -> MasterProfile:
        user = self.User.objects.create_user(username=username, password="test123")
        return MasterProfile.objects.create(user=UserProfile.objects.create(user=user))

    def _create_service(self, name: str = "Service") -> Service:
        service = Service.objects.create(name=name, base_price=Decimal("50.00"), duration_min=30)
        room = MasterRoom.objects.create(room=f"{name[:15]}")
        service.allowed_rooms.add(room)
        return service

    def _create_appointment(self, client_profile: UserProfile) -> Appointment:
        payment_status = PaymentStatus.objects.create(name="Not Paid")
        return Appointment.objects.create(
            client=client_profile,
            payment_status=payment_status,
            start_time=timezone.now(),
        )

    def test_admin_created_item_bootstrap_and_email_task(self):
        admin_user = self.User.objects.create_user(username="admin-inline", password="pw", email="admin@example.com")
        client_user = self.User.objects.create_user(username="client-inline", password="pw", email="client@example.com")
        client_profile = UserProfile.objects.create(user=client_user)
        master_profile = self._create_master_profile("master-inline")
        service = self._create_service("Therapy Session")
        appointment = self._create_appointment(client_profile)

        with patch("core.tasks.send_item_confirmation_email.delay") as mock_delay:
            item = AppointmentItem(
                appointment=appointment,
                service=service,
                master=master_profile,
                start_time=timezone.now(),
            )
            item._created_via_admin = True
            item._initial_status_code = "BOOKED"
            item._initial_status_user_id = admin_user.id
            item._initial_status_timestamp = timezone.now()
            item._initial_status_note = "admin-initial"
            item.full_clean()
            item.save()

        item.refresh_from_db()
        self.assertEqual(item.status.code, "BOOKED")
        histories = AppointmentItemStatusHistory.objects.filter(item=item)
        self.assertEqual(histories.count(), 1)
        self.assertEqual(histories.first().status.code, "BOOKED")
        self.assertEqual(histories.first().note, "admin-initial")
        mock_delay.assert_called_once_with(str(item.pk))

    def test_checkout_items_start_confirmed(self):
        client_user = self.User.objects.create_user(username="checkout-client", password="pw", email="client@example.com")
        client_profile = UserProfile.objects.create(user=client_user)
        master_profile = self._create_master_profile("checkout-master")
        service = self._create_service("Facial Treatment")

        cart_item = SimpleNamespace(
            service=service,
            master=master_profile,
            start_time=timezone.now(),
        )

        with patch("core.tasks.send_item_confirmation_email.delay") as mock_delay:
            appointment = create_appointment_from_cart_items(profile=client_profile, items=[cart_item])

        item = appointment.items.select_related("status").first()
        self.assertIsNotNone(item)
        self.assertEqual(item.status.code, "CONFIRMED")
        history = AppointmentItemStatusHistory.objects.filter(item=item).first()
        self.assertIsNotNone(history)
        self.assertEqual(history.status.code, "CONFIRMED")
        self.assertEqual(history.note, "checkout-confirmed")
        mock_delay.assert_not_called()

    def test_checkout_multiple_items_start_confirmed(self):
        client_user = self.User.objects.create_user(username="checkout-multi", password="pw", email="client@example.com")
        client_profile = UserProfile.objects.create(user=client_user)
        master_one = self._create_master_profile("checkout-master-one")
        master_two = self._create_master_profile("checkout-master-two")
        service_one = self._create_service("Facial A")
        service_two = self._create_service("Facial B")

        cart_items = [
            SimpleNamespace(service=service_one, master=master_one, start_time=timezone.now()),
            SimpleNamespace(service=service_two, master=master_two, start_time=timezone.now() + timedelta(hours=1)),
        ]

        with patch("core.tasks.send_item_confirmation_email.delay") as mock_delay:
            appointment = create_appointment_from_cart_items(profile=client_profile, items=cart_items)

        items = list(appointment.items.select_related("status"))
        self.assertEqual(len(items), 2)
        for item in items:
            self.assertEqual(item.status.code, "CONFIRMED")
            history = AppointmentItemStatusHistory.objects.filter(item=item).first()
            self.assertIsNotNone(history)
            self.assertEqual(history.status.code, "CONFIRMED")
            self.assertEqual(history.note, "checkout-confirmed")
        mock_delay.assert_not_called()

    def test_cancelled_history_enqueues_item_notification(self):
        client_profile = UserProfile.objects.create(user=self.User.objects.create_user(username="cancel-client", password="pw"))
        master_profile = self._create_master_profile("cancel-master")
        service = self._create_service("Massage")
        appointment = self._create_appointment(client_profile)

        item = AppointmentItem.objects.create(
            appointment=appointment,
            service=service,
            master=master_profile,
            start_time=timezone.now(),
        )
        ensure_initial_status(item, "BOOKED")
        cancelled_status = ensure_item_status("CANCELLED")

        with patch("core.tasks.send_item_cancellation_email.delay") as mock_delay:
            AppointmentItemStatusHistory.objects.create(
                item=item,
                status=cancelled_status,
                set_at=timezone.now(),
                note="manual-cancel",
            )

        mock_delay.assert_called_once_with(str(item.pk))

    def test_confirmation_email_failure_keeps_booked(self):
        client_profile = UserProfile.objects.create(
            user=self.User.objects.create_user(username="confirm-client", password="pw", email="client@example.com")
        )
        master_profile = self._create_master_profile("confirm-master")
        service = self._create_service("Nail Art")
        appointment = self._create_appointment(client_profile)

        item = AppointmentItem.objects.create(
            appointment=appointment,
            service=service,
            master=master_profile,
            start_time=timezone.now(),
        )
        item.refresh_from_db()
        self.assertEqual(item.status.code, "BOOKED")

        with patch("core.tasks._send_email", side_effect=Exception("fail")), patch("core.tasks.send_sms", return_value=None):
            result = send_item_confirmation_email(str(item.pk))

        self.assertFalse(result)
        item.refresh_from_db()
        self.assertEqual(item.status.code, "BOOKED")
        notes = list(AppointmentItemStatusHistory.objects.filter(item=item).values_list("note", flat=True))
        self.assertEqual(notes, ["initial-status"])

    def test_confirmation_email_success_marks_confirmed(self):
        client_profile = UserProfile.objects.create(
            user=self.User.objects.create_user(username="confirm-success", password="pw", email="client@example.com")
        )
        master_profile = self._create_master_profile("confirm-master-success")
        service = self._create_service("Massage")
        appointment = self._create_appointment(client_profile)

        item = AppointmentItem.objects.create(
            appointment=appointment,
            service=service,
            master=master_profile,
            start_time=timezone.now(),
        )
        item.refresh_from_db()
        self.assertEqual(item.status.code, "BOOKED")

        with patch("core.tasks.send_sms", return_value=None):
            result = send_item_confirmation_email(str(item.pk))

        self.assertTrue(result)
        item.refresh_from_db()
        self.assertEqual(item.status.code, "CONFIRMED")
        notes = list(
            AppointmentItemStatusHistory.objects.filter(item=item).order_by("set_at").values_list("note", flat=True)
        )
        self.assertIn(EMAIL_CONFIRM_NOTE, notes)


class AdminItemStatusEndpointTests(TestCase):
    def setUp(self) -> None:
        self.User = get_user_model()
        self.admin_password = "test123"
        self.admin_user = self.User.objects.create_superuser(
            username="admin-status",
            email="admin-status@example.com",
            password=self.admin_password,
        )
        UserProfile.objects.get_or_create(user=self.admin_user)
        self.payment_status = PaymentStatus.objects.create(name="Not Paid")
        for code in ("BOOKED", "CONFIRMED", "CANCELLED", "COMPLETED"):
            ensure_item_status(code)

    def _create_master_profile(self, username: str) -> MasterProfile:
        user = self.User.objects.create_user(username=username, password="pw")
        return MasterProfile.objects.create(user=UserProfile.objects.create(user=user))

    def _create_service(self, name: str = "Service") -> Service:
        service = Service.objects.create(name=name, base_price=Decimal("80.00"), duration_min=45)
        room = MasterRoom.objects.create(room=f"{name[:20]}")
        service.allowed_rooms.add(room)
        return service

    def _build_appointment_with_item(self) -> tuple[Appointment, AppointmentItem, MasterProfile]:
        client_user = self.User.objects.create_user(username="client-admin", password="pw")
        client_profile, _ = UserProfile.objects.get_or_create(user=client_user)
        master_profile = self._create_master_profile("master-admin")
        service = self._create_service("Facial")
        ServiceMaster.objects.create(service=service, master=master_profile)
        appointment = Appointment.objects.create(
            client=client_profile,
            payment_status=self.payment_status,
            start_time=timezone.now(),
        )
        booked_status = ensure_item_status("BOOKED")
        item = AppointmentItem.objects.create(
            appointment=appointment,
            service=service,
            master=master_profile,
            start_time=timezone.now(),
            status=booked_status,
        )
        AppointmentItemStatusHistory.objects.create(
            item=item,
            status=booked_status,
            note="initial",
        )
        return appointment, item, master_profile

    @patch("core.admin.send_item_cancellation_email.delay")
    def test_admin_update_status_to_cancelled(self, mock_delay):
        appointment, item, _ = self._build_appointment_with_item()
        self.assertTrue(self.client.login(username=self.admin_user.username, password=self.admin_password))
        url = reverse("admin-item-status-update", args=[item.pk])
        self.client.get("/admin/")
        csrftoken = self.client.cookies.get("csrftoken")
        token_value = csrftoken.value if csrftoken else ""
        response = self.client.post(
            url,
            data=json.dumps({"status": "CANCELLED"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token_value,
        )
        self.assertEqual(
            response.status_code,
            200,
            f"status={response.status_code}, location={response.headers.get('Location')}",
        )
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["item"]["status"]["code"], "CANCELLED")
        item.refresh_from_db()
        self.assertEqual(item.status.code, "CANCELLED")
        self.assertTrue(
            AppointmentItemStatusHistory.objects.filter(item=item, status__code="CANCELLED").exists()
        )
        self.assertGreaterEqual(mock_delay.call_count, 1)
        self.assertEqual(mock_delay.call_args_list[-1], call(str(item.pk), reason=None))
        aggregated = data["appointment"]["aggregated_status"]
        self.assertEqual(aggregated["code"], "CANCELLED")

    @patch("core.views.__init__.send_item_cancellation_email.delay")
    def test_api_cancel_item(self, mock_delay):
        appointment, item, _ = self._build_appointment_with_item()
        self.assertTrue(self.client.login(username=self.admin_user.username, password=self.admin_password))
        url = reverse("api-appt-cancel", args=[appointment.pk])
        response = self.client.post(
            url,
            data=json.dumps({"item_id": str(item.pk)}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["appointment_id"], str(appointment.pk))
        self.assertEqual(payload["item_id"], str(item.pk))
        self.assertIn("item_status", payload)
        self.assertEqual(payload["item_status"]["code"], "CANCELLED")
        self.assertIn("appointment_aggregated_status", payload)
        self.assertEqual(payload["appointment_aggregated_status"]["code"], "CANCELLED")
        item.refresh_from_db()
        self.assertEqual(item.status.code, "CANCELLED")
        self.assertEqual(
            AppointmentStatusHistory.objects.filter(appointment=appointment, status__name__iexact="Cancelled").count(),
            0,
        )
        self.assertGreaterEqual(mock_delay.call_count, 1)
        self.assertEqual(mock_delay.call_args_list[-1], call(str(item.pk), reason=None))

    @patch("core.views.__init__.send_item_cancellation_email.delay")
    def test_api_cancel_one_item_leaves_siblings(self, mock_delay):
        appointment, item, _ = self._build_appointment_with_item()
        sibling = AppointmentItem.objects.create(
            appointment=appointment,
            service=item.service,
            master=item.master,
            start_time=timezone.now() + timedelta(hours=1),
            status=ensure_item_status("BOOKED"),
        )
        AppointmentItemStatusHistory.objects.create(
            item=sibling,
            status=ensure_item_status("BOOKED"),
            note="initial",
        )
        self.assertTrue(self.client.login(username=self.admin_user.username, password=self.admin_password))
        url = reverse("api-appt-cancel", args=[appointment.pk])
        response = self.client.post(
            url,
            data=json.dumps({"item_id": str(item.pk)}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        item.refresh_from_db()
        sibling.refresh_from_db()
        self.assertEqual(item.status.code, "CANCELLED")
        self.assertEqual(sibling.status.code, "BOOKED")
        called_item_ids = [args[0][0] for args in mock_delay.call_args_list]
        self.assertIn(str(item.pk), called_item_ids)
        self.assertNotIn(str(sibling.pk), called_item_ids)

    @patch("core.views.__init__.send_item_cancellation_email.delay")
    def test_api_legacy_cancel_applies_to_all_items(self, mock_delay):
        appointment, item, _ = self._build_appointment_with_item()
        second = AppointmentItem.objects.create(
            appointment=appointment,
            service=item.service,
            master=item.master,
            start_time=timezone.now() + timedelta(hours=1),
            status=ensure_item_status("BOOKED"),
        )
        AppointmentItemStatusHistory.objects.create(
            item=second,
            status=ensure_item_status("BOOKED"),
            note="initial",
        )
        self.assertTrue(self.client.login(username=self.admin_user.username, password=self.admin_password))
        url = reverse("api-appt-cancel", args=[appointment.pk])
        response = self.client.post(url, data=json.dumps({}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload.get("deprecated"))
        item.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(item.status.code, "CANCELLED")
        self.assertEqual(second.status.code, "CANCELLED")
        called_item_ids = sorted({args[0][0] for args in mock_delay.call_args_list})
        self.assertEqual(called_item_ids, sorted([str(item.pk), str(second.pk)]))

    def test_api_reschedule_item_returns_status_payload(self):
        appointment, item, master = self._build_appointment_with_item()
        self.assertTrue(self.client.login(username=self.admin_user.username, password=self.admin_password))
        url = reverse("api-appt-reschedule", args=[appointment.pk])
        new_start = (timezone.now() + timedelta(hours=1)).isoformat()
        response = self.client.post(
            url,
            data=json.dumps({"item_id": str(item.pk), "start_time": new_start, "master": str(master.pk)}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["item_id"], str(item.pk))
        self.assertIn("item_status", payload)
        self.assertIn("appointment_aggregated_status", payload)
        self.assertIn("appointment", payload)
        self.assertFalse(payload.get("deprecated"))
        item.refresh_from_db()
        self.assertEqual(payload["item"]["start_time"], item.start_time.isoformat())

    def test_admin_api_reschedule_item_returns_item_payload(self):
        appointment, item, master = self._build_appointment_with_item()
        self.assertTrue(self.client.login(username=self.admin_user.username, password=self.admin_password))
        self.client.get("/admin/")
        csrf = self.client.cookies.get("csrftoken")
        token_value = csrf.value if csrf else ""
        url = reverse("admin-item-reschedule", args=[item.pk])
        new_start = (timezone.now() + timedelta(hours=2)).isoformat()
        response = self.client.post(
            url,
            data=json.dumps(
                {
                    "start_time": new_start,
                    "master": str(master.pk),
                }
            ),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token_value,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("item", payload)
        returned_item = payload["item"]
        self.assertEqual(returned_item["id"], str(item.pk))
        item.refresh_from_db()
        self.assertEqual(item.master_id, master.pk)
        self.assertEqual(returned_item["start_time"], item.start_time.isoformat())
