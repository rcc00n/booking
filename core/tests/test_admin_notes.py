from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone

from core.admin import AppointmentAdmin
from core.admin import createTable
from core.forms import AppointmentAdminForm
from core.models import (
    Appointment,
    AppointmentItem,
    AppointmentStatus,
    AppointmentStatusHistory,
    MasterProfile,
    PaymentStatus,
    Service,
    UserProfile,
)
from core.services.item_status import record_item_status
from core.tests.utils import assign_service_room


class AppointmentNotesFeatureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()

        cls.client_user = user_model.objects.create_user(username="notes-client", password="test123")
        cls.client_profile = getattr(cls.client_user, "userprofile", None)
        if cls.client_profile is None:
            cls.client_profile = UserProfile.objects.create(user=cls.client_user)

        cls.master_user = user_model.objects.create_user(
            username="notes-master",
            password="test123",
            first_name="Mia",
            last_name="Therapist",
        )
        cls.master_profile_user = getattr(cls.master_user, "userprofile", None)
        if cls.master_profile_user is None:
            cls.master_profile_user = UserProfile.objects.create(user=cls.master_user)
        cls.master_profile = MasterProfile.objects.create(user=cls.master_profile_user)

        cls.admin_user = user_model.objects.create_superuser(
            username="notes-admin",
            email="notes@example.com",
            password="pass123",
        )
        cls.admin_profile = getattr(cls.admin_user, "userprofile", None)
        if cls.admin_profile is None:
            cls.admin_profile = UserProfile.objects.create(user=cls.admin_user)

        cls.payment_status = PaymentStatus.objects.create(name="Not Paid")
        cls.status_confirmed = AppointmentStatus.objects.create(name="Confirmed")
        cls.service = Service.objects.create(
            name="Deep Tissue",
            base_price=Decimal("150.00"),
            duration_min=60,
            extra_time_min=0,
        )
        assign_service_room(cls.service, room_name="Notes Room")

    def test_notes_field_defaults_to_blank(self):
        appointment = Appointment.objects.create(
            client=self.client_profile,
            payment_status=self.payment_status,
        )
        self.assertEqual(appointment.notes, "")

    def test_admin_form_persists_notes(self):
        appointment = Appointment.objects.create(
            client=self.client_profile,
            payment_status=self.payment_status,
            start_time=timezone.now(),
        )
        start_time_str = appointment.start_time.strftime("%Y-%m-%d %H:%M:%S")

        form = AppointmentAdminForm(
            data={
                "client": str(self.client_profile.pk),
                "start_time": start_time_str,
                "payment_status": str(self.payment_status.pk),
                "notes": "Needs translator follow-up",
            },
            instance=appointment,
        )

        self.assertIn("notes", form.fields)
        self.assertTrue(form.is_valid(), form.errors.as_text())

        saved = form.save()
        saved.refresh_from_db()
        self.assertEqual(saved.notes, "Needs translator follow-up")

    def test_admin_save_model_persists_notes(self):
        appointment = Appointment.objects.create(
            client=self.client_profile,
            payment_status=self.payment_status,
            start_time=timezone.now(),
        )
        start_time_str = appointment.start_time.strftime("%Y-%m-%d %H:%M:%S")

        form = AppointmentAdminForm(
            data={
                "client": str(self.client_profile.pk),
                "start_time": start_time_str,
                "payment_status": str(self.payment_status.pk),
                "current_status": str(self.status_confirmed.pk),
                "notes": "Call before arrival",
            },
            instance=appointment,
        )
        self.assertTrue(form.is_valid(), form.errors.as_text())

        admin_instance = AppointmentAdmin(Appointment, admin.site)
        request = RequestFactory().post("/")
        request.user = self.admin_user
        admin_instance.save_model(request, form.save(commit=False), form, change=True)

        appointment.refresh_from_db()
        self.assertEqual(appointment.notes, "Call before arrival")
        self.assertTrue(
            AppointmentStatusHistory.objects.filter(
                appointment=appointment,
                status=self.status_confirmed,
            ).exists()
        )

    def test_calendar_renders_note_badge(self):
        note_text = "Bring consent form"
        start_time = timezone.now().replace(minute=0, second=0, microsecond=0)
        appointment = Appointment.objects.create(
            client=self.client_profile,
            payment_status=self.payment_status,
            start_time=start_time,
            notes=note_text,
        )
        AppointmentStatusHistory.objects.create(
            appointment=appointment,
            status=self.status_confirmed,
            set_by=self.admin_profile,
        )
        item = AppointmentItem.objects.create(
            appointment=appointment,
            service=self.service,
            master=self.master_profile,
            start_time=start_time,
            unit_price=Decimal("150.00"),
        )

        selected_date = timezone.localtime(start_time).date()
        current_tz = timezone.get_current_timezone()
        day_start = timezone.make_aware(datetime.combine(selected_date, time(8, 0)), current_tz)
        day_end = timezone.make_aware(datetime.combine(selected_date, time(21, 15)), current_tz)
        slot_times: list[str] = []

        calendar_table = createTable(
            selected_date,
            day_start,
            day_end,
            slot_times,
            [item],
            [self.master_profile],
            [],
        )

        found_badge = False
        for row in calendar_table:
            for cell in row["cells"]:
                if cell.get("appt_id") == appointment.id:
                    self.assertTrue(cell.get("has_note"))
                    self.assertIn("badge--note", cell["html"])
                    found_badge = True
                    break
            if found_badge:
                break

        self.assertTrue(found_badge, "Appointment cell with note badge not rendered")

    def test_calendar_renders_multiple_items_with_cancelled_styling(self):
        appointment = Appointment.objects.create(
            client=self.client_profile,
            payment_status=self.payment_status,
            start_time=timezone.now(),
        )
        selected_date = timezone.localtime(appointment.start_time).date()
        base_start = timezone.make_aware(datetime.combine(selected_date, time(9, 0)))


        active_item = AppointmentItem.objects.create(
            appointment=appointment,
            service=self.service,
            master=self.master_profile,
            start_time=base_start,
            unit_price=Decimal("150.00"),
        )
        record_item_status(
            active_item,
            "CONFIRMED",
            set_by_user_id=self.admin_user.id,
            note="test-confirm",
        )

        cancelled_item = AppointmentItem.objects.create(
            appointment=appointment,
            service=self.service,
            master=self.master_profile,
            start_time=base_start + timedelta(hours=2),
            unit_price=Decimal("150.00"),
        )
        record_item_status(
            cancelled_item,
            "CANCELLED",
            set_by_user_id=self.admin_user.id,
            note="test-cancel",
        )

        current_tz = timezone.get_current_timezone()
        day_start = timezone.make_aware(datetime.combine(selected_date, time(8, 0)), current_tz)
        day_end = timezone.make_aware(datetime.combine(selected_date, time(21, 15)), current_tz)
        slot_times: list[str] = []

        items = list(
            AppointmentItem.objects.filter(appointment=appointment)
            .select_related("service", "master__user", "status")
            .order_by("start_time")
        )

        calendar_table = createTable(
            selected_date,
            day_start,
            day_end,
            slot_times,
            items,
            [self.master_profile],
            [],
        )

        event_cells = []
        for row in calendar_table:
            for cell in row["cells"]:
                if cell.get("item_id"):
                    event_cells.append(cell)

        item_ids = {cell["item_id"] for cell in event_cells}
        self.assertEqual(
            item_ids,
            {str(active_item.pk), str(cancelled_item.pk)},
            "Calendar should render blocks for both items",
        )

        cancelled_cells = [cell for cell in event_cells if cell["item_id"] == str(cancelled_item.pk)]
        self.assertTrue(cancelled_cells, "Cancelled item block not present in calendar")
        self.assertTrue(
            any("status-cancelled" in cell.get("status_class", "") for cell in cancelled_cells),
            "Cancelled item block missing cancelled styling",
        )
