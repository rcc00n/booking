from __future__ import annotations

import unittest
from collections import defaultdict
from datetime import datetime, timedelta, time

from django.contrib import admin as django_admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from core.admin import AppointmentAdmin
from core.models import (
    Appointment,
    AppointmentItem,
    AppointmentItemStatus,
    MasterProfile,
    MasterWorkDay,
    MasterRoom,
    Service,
    UserProfile,
)


class RoomAllocationTests(TransactionTestCase):
    reset_sequences = True

    @classmethod
    def setUpClass(cls):
        if connection.vendor != "postgresql":
            raise unittest.SkipTest("Room allocation relies on PostgreSQL-specific constraints")
        super().setUpClass()

    def setUp(self):
        super().setUp()
        self.user_model = get_user_model()
        self.client_profile = self._make_client("room-client")

    def _make_client(self, username: str) -> UserProfile:
        user = self.user_model.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="pass1234",
        )
        return getattr(user, "userprofile", None) or UserProfile.objects.create(user=user)

    def _make_master(self, username: str, first_name: str) -> MasterProfile:
        user = self.user_model.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="pass1234",
            first_name=first_name,
            last_name="Master",
        )
        profile = getattr(user, "userprofile", None) or UserProfile.objects.create(user=user)
        return MasterProfile.objects.create(user=profile, profession="Stylist")

    def _make_service(self, name: str, rooms: list[MasterRoom]) -> Service:
        service = Service.objects.create(
            name=name,
            description="Test service",
            base_price="50.00",
            duration_min=60,
            extra_time_min=0,
        )
        service.allowed_rooms.set(rooms)
        return service

    def _make_appointment(self, start) -> Appointment:
        return Appointment.objects.create(client=self.client_profile, start_time=start)

    def _create_item(self, appointment, service, master, start):
        return AppointmentItem.objects.create(
            appointment=appointment,
            service=service,
            master=master,
            start_time=start,
        )

    def test_auto_assigns_free_room(self):
        room_a = MasterRoom.objects.create(room="Room A")
        room_b = MasterRoom.objects.create(room="Room B")
        service = self._make_service("Facial", [room_a, room_b])

        master_one = self._make_master("master1", "Alice")
        master_two = self._make_master("master2", "Brenda")
        start = timezone.now().replace(minute=0, second=0, microsecond=0)
        appt_one = self._make_appointment(start)
        appt_two = self._make_appointment(start)

        first_item = self._create_item(appt_one, service, master_one, start)
        second_item = self._create_item(appt_two, service, master_two, start + timedelta(minutes=15))

        self.assertEqual(first_item.room, room_a)
        self.assertEqual(second_item.room, room_b)

    def test_blocks_when_all_busy(self):
        room_a = MasterRoom.objects.create(room="Room A")
        room_b = MasterRoom.objects.create(room="Room B")
        service = self._make_service("Massage", [room_a, room_b])

        master_one = self._make_master("master1", "Alice")
        master_two = self._make_master("master2", "Brenda")
        master_three = self._make_master("master3", "Cara")
        base_start = timezone.now().replace(minute=0, second=0, microsecond=0)
        appt_one = self._make_appointment(base_start)
        appt_two = self._make_appointment(base_start)
        appt_three = self._make_appointment(base_start)

        self._create_item(appt_one, service, master_one, base_start)
        self._create_item(appt_two, service, master_two, base_start)

        pending = AppointmentItem(
            appointment=appt_three,
            service=service,
            master=master_three,
            start_time=base_start,
        )
        with self.assertRaises(ValidationError):
            pending.full_clean()

    def test_different_services_share_same_rooms(self):
        room_a = MasterRoom.objects.create(room="Room A")
        room_b = MasterRoom.objects.create(room="Room B")
        service_one = self._make_service("Laser A", [room_a, room_b])
        service_two = self._make_service("Laser B", [room_a, room_b])

        master_one = self._make_master("master1", "Alice")
        master_two = self._make_master("master2", "Brenda")
        master_three = self._make_master("master3", "Cara")
        base_start = timezone.now().replace(minute=0, second=0, microsecond=0)

        appt_one = self._make_appointment(base_start)
        appt_two = self._make_appointment(base_start)
        appt_three = self._make_appointment(base_start)

        first_item = self._create_item(appt_one, service_one, master_one, base_start)
        second_item = self._create_item(appt_two, service_two, master_two, base_start)

        self.assertEqual({first_item.room, second_item.room}, {room_a, room_b})

        conflict = AppointmentItem(
            appointment=appt_three,
            service=service_two,
            master=master_three,
            start_time=base_start,
            end_time=base_start + timedelta(minutes=60),
            room=room_a,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AppointmentItem.objects.bulk_create([conflict])

    def test_update_reallocates_or_blocks(self):
        room_a = MasterRoom.objects.create(room="Room A")
        room_b = MasterRoom.objects.create(room="Room B")
        service = self._make_service("Peel", [room_a, room_b])

        m1 = self._make_master("master1", "Alice")
        m2 = self._make_master("master2", "Brenda")
        m3 = self._make_master("master3", "Cara")
        m4 = self._make_master("master4", "Daria")

        slot_one = timezone.now().replace(minute=0, second=0, microsecond=0)
        slot_two = slot_one + timedelta(hours=2)

        appt_a = self._make_appointment(slot_one)
        appt_b = self._make_appointment(slot_one)
        appt_c = self._make_appointment(slot_two)
        appt_d = self._make_appointment(slot_one)

        self._create_item(appt_a, service, m1, slot_one)
        moving = self._create_item(appt_b, service, m2, slot_one)
        blocker_future = self._create_item(appt_c, service, m3, slot_two)

        moving.start_time = slot_two
        moving.save()
        moving.refresh_from_db()
        self.assertNotEqual(moving.room, blocker_future.room)

        self._create_item(appt_d, service, m4, slot_one)

        moving.start_time = slot_one
        with self.assertRaises(ValidationError):
            moving.full_clean()


class ServiceRoomTestMixin:
    def setUp(self):
        super().setUp()
        self.user_model = get_user_model()
        self.client_profile = self._make_client("clean-client")
        today = timezone.localdate()
        current_tz = timezone.get_current_timezone()
        self.base_start = timezone.make_aware(datetime.combine(today, time(12, 0)), current_tz)
        self.service = Service.objects.create(
            name="Clean Service",
            description="",
            base_price="75.00",
            duration_min=60,
            extra_time_min=0,
        )
        self.room_a = MasterRoom.objects.create(room="Clean Room A")
        self.room_b = MasterRoom.objects.create(room="Clean Room B")
        self.service.allowed_rooms.set([self.room_a, self.room_b])

    def _make_client(self, username: str) -> UserProfile:
        user = self.user_model.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="pass1234",
        )
        profile = getattr(user, "userprofile", None)
        if profile is None:
            profile = UserProfile.objects.create(user=user)
        return profile

    def _make_master(self, username: str) -> MasterProfile:
        user = self.user_model.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="pass1234",
            first_name=username.title(),
            last_name="Test",
        )
        profile = getattr(user, "userprofile", None)
        if profile is None:
            profile = UserProfile.objects.create(user=user)
        master = MasterProfile.objects.create(user=profile, profession="Tester")
        self._ensure_workweek(master)
        return master

    def _ensure_workweek(self, master: MasterProfile, *, start_hour: int = 8, end_hour: int = 20):
        master.workdays.all().delete()
        for weekday in range(7):
            MasterWorkDay.objects.create(
                master=master,
                weekday=weekday,
                start_time=time(start_hour, 0),
                end_time=time(end_hour, 0),
            )

    def _appointment(self, start=None) -> Appointment:
        return Appointment.objects.create(
            client=self.client_profile,
            start_time=start or self.base_start,
        )

    def _create_item(self, appointment, master, start):
        item = AppointmentItem(
            appointment=appointment,
            service=self.service,
            master=master,
            start_time=start,
        )
        item.full_clean()
        item.save()
        return item

    def _start_at(self, hour: int, minute: int = 0):
        base_date = timezone.localtime(self.base_start).date()
        naive = datetime.combine(base_date, time(hour, minute))
        return timezone.make_aware(naive, timezone.get_current_timezone())


class AppointmentItemCleanTests(ServiceRoomTestMixin, TestCase):

    @classmethod
    def setUpClass(cls):
        if connection.vendor != "postgresql":
            raise unittest.SkipTest("Room allocation validation relies on PostgreSQL-specific constraints")
        super().setUpClass()

    def test_clean_assigns_room_when_available(self):
        master = self._make_master("clean-master")
        appointment = self._appointment(self.base_start)

        item = AppointmentItem(
            appointment=appointment,
            service=self.service,
            master=master,
            start_time=self.base_start,
        )
        item.full_clean()

        self.assertIsNotNone(item.room)
        self.assertIn(item.room, {self.room_a, self.room_b})

    def test_clean_raises_when_all_rooms_occupied(self):
        master_one = self._make_master("clean-master-one")
        master_two = self._make_master("clean-master-two")
        master_three = self._make_master("clean-master-three")

        slot = self.base_start
        self._create_item(self._appointment(slot), master_one, slot)
        self._create_item(self._appointment(slot), master_two, slot)

        pending = AppointmentItem(
            appointment=self._appointment(slot),
            service=self.service,
            master=master_three,
            start_time=slot,
        )
        with self.assertRaises(ValidationError) as ctx:
            pending.full_clean()
        self.assertIn("All rooms", str(ctx.exception))

    def test_clean_blocks_master_overlap(self):
        if connection.vendor != "postgresql":
            self.skipTest("Master overlap constraint relies on PostgreSQL-specific indexes")
        master = self._make_master("overlap-master")
        slot = self.base_start
        self._create_item(self._appointment(slot), master, slot)

        overlapping = AppointmentItem(
            appointment=self._appointment(slot + timedelta(minutes=15)),
            service=self.service,
            master=master,
            start_time=slot + timedelta(minutes=15),
        )
        with self.assertRaises(ValidationError) as ctx:
            overlapping.full_clean()
        self.assertIn("start_time", ctx.exception.message_dict)

    def test_clean_respects_working_hours(self):
        master = self._make_master("hours-master")
        self._ensure_workweek(master, start_hour=10, end_hour=18)
        early_start = self._start_at(8, 0)

        item = AppointmentItem(
            appointment=self._appointment(early_start),
            service=self.service,
            master=master,
            start_time=early_start,
        )
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn("start_time", ctx.exception.message_dict)

    def test_appointment_clean_detects_room_overage(self):
        self.service.allowed_rooms.set([self.room_a])
        master_one = self._make_master("clean-master-one")
        master_two = self._make_master("clean-master-two")
        appt = self._appointment(self.base_start)
        self._create_item(appt, master_one, self.base_start)
        conflicting = self._create_item(appt, master_two, self.base_start + timedelta(hours=2))
        AppointmentItem.objects.filter(pk=conflicting.pk).update(room=None)
        AppointmentItem.objects.filter(pk=conflicting.pk).update(start_time=self.base_start)
        appt.refresh_from_db()
        with self.assertRaises(ValidationError):
            appt.clean()


class AppointmentAdminRoomValidationTests(ServiceRoomTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.admin_view = AppointmentAdmin(Appointment, django_admin.site)
        self.cancelled_status, _ = AppointmentItemStatus.objects.get_or_create(
            code="CANCELLED",
            defaults={"name": "Cancelled"},
        )

    def _empty_bag(self):
        return {
            "__all__": [],
            "fields": defaultdict(list),
            "items": defaultdict(lambda: defaultdict(list)),
            "intake": defaultdict(lambda: defaultdict(list)),
        }

    def test_helper_flags_overlapping_rows(self):
        self.service.allowed_rooms.set([self.room_a])
        start = self.base_start
        rows = [
            {"idx": 0, "service_id": str(self.service.pk), "dt": start, "duration_override": None},
            {"idx": 1, "service_id": str(self.service.pk), "dt": start + timedelta(minutes=15), "duration_override": None},
        ]
        bag = self._empty_bag()
        self.admin_view._validate_service_room_capacity(rows, bag)
        self.assertIn(
            "All rooms",
            " ".join(bag["items"][1]["start_time_1"]),
        )

    def test_helper_allows_non_overlapping_rows(self):
        self.service.allowed_rooms.set([self.room_a])
        start = self.base_start
        later = start + timedelta(hours=2)
        rows = [
            {"idx": 0, "service_id": str(self.service.pk), "dt": start, "duration_override": None},
            {"idx": 1, "service_id": str(self.service.pk), "dt": later, "duration_override": None},
        ]
        bag = self._empty_bag()
        self.admin_view._validate_service_room_capacity(rows, bag)
        self.assertFalse(bag["items"])

    def test_helper_skips_cancelled_rows(self):
        self.service.allowed_rooms.set([self.room_a])
        start = self.base_start
        # CHANGED: cancelled rows must be ignored when tallying usage.
        rows = [
            {"idx": 0, "service_id": str(self.service.pk), "dt": start, "duration_override": None, "status_code": "CANCELLED"},
            {"idx": 1, "service_id": str(self.service.pk), "dt": start, "duration_override": None},
        ]
        bag = self._empty_bag()
        self.admin_view._validate_service_room_capacity(rows, bag)
        self.assertFalse(bag["items"])

    def test_enforce_room_capacity_for_items_blocks_conflicts(self):
        self.service.allowed_rooms.set([self.room_a])
        appointment = self._appointment(self.base_start)
        master_one = self._make_master("admin-room-master-one")
        master_two = self._make_master("admin-room-master-two")
        item_one = AppointmentItem(
            appointment=appointment,
            service=self.service,
            master=master_one,
            start_time=self.base_start,
        )
        item_two = AppointmentItem(
            appointment=appointment,
            service=self.service,
            master=master_two,
            start_time=self.base_start,
        )
        item_one.full_clean()
        item_two.full_clean()

        prebuilt = [(0, item_one, ""), (1, item_two, "")]
        row_errs = {}
        self.admin_view._enforce_room_capacity_for_items(prebuilt, row_errs)
        self.assertIn("items-1-start_time_1", row_errs)

    def test_enforce_room_capacity_skips_cancelled_items(self):
        self.service.allowed_rooms.set([self.room_a])
        appointment = self._appointment(self.base_start)
        master_one = self._make_master("admin-room-master-cancelled")
        master_two = self._make_master("admin-room-master-active")
        # CHANGED: cancelled AppointmentItem instances should not reduce available capacity.
        cancelled_item = AppointmentItem(
            appointment=appointment,
            service=self.service,
            master=master_one,
            start_time=self.base_start,
        )
        active_item = AppointmentItem(
            appointment=appointment,
            service=self.service,
            master=master_two,
            start_time=self.base_start,
        )
        cancelled_item.full_clean()
        cancelled_item.save()
        active_item.full_clean()
        active_item.save()
        cancelled_item.status = self.cancelled_status
        cancelled_item.save(update_fields=["status"])
        cancelled_item.current_status_code = "CANCELLED"

        prebuilt = [(0, cancelled_item, ""), (1, active_item, "")]
        row_errs = {}
        self.admin_view._enforce_room_capacity_for_items(prebuilt, row_errs)
        self.assertFalse(row_errs)

    def test_enforce_room_capacity_honors_staged_cancellations(self):
        self.service.allowed_rooms.set([self.room_a])
        appointment = self._appointment(self.base_start)
        master_one = self._make_master("admin-room-master-stage-one")
        master_two = self._make_master("admin-room-master-stage-two")
        # CHANGED: staged cancellations passed from the form should be skipped.
        item_one = AppointmentItem(
            appointment=appointment,
            service=self.service,
            master=master_one,
            start_time=self.base_start,
        )
        item_two = AppointmentItem(
            appointment=appointment,
            service=self.service,
            master=master_two,
            start_time=self.base_start,
        )
        item_one.full_clean()
        item_two.full_clean()

        prebuilt = [(0, item_one, ""), (1, item_two, "")]
        row_errs = {}
        self.admin_view._enforce_room_capacity_for_items(
            prebuilt,
            row_errs,
            cancelled_prefixes={"items-0"},
        )
        self.assertFalse(row_errs)
