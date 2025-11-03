from __future__ import annotations

from datetime import timedelta

from decimal import Decimal

from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class AppointmentItemStatusMigrationTests(TransactionTestCase):
    migrate_from = ("core", "0038_alter_clientsource_source")
    migrate_to = ("core", "0042_appointmentitem_validation_enabled")
    databases = {"default"}

    def setUp(self):
        self.executor = MigrationExecutor(connection)
        self.executor.loader.build_graph()

    def _flush_deferred_constraints(self):
        if connection.in_atomic_block:
            transaction.set_autocommit(True, using=connection.alias)
        connection.commit()
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        connection.commit()
        connection.close()
        connection.ensure_connection()

    def _migrate_to_head(self):
        self._flush_deferred_constraints()
        self.executor.loader.build_graph()
        final_targets = self.executor.loader.graph.leaf_nodes()
        self.executor.migrate(final_targets)

    def test_forward_migration_populates_item_statuses(self):
        old_target = [self.migrate_from]
        new_target = [self.migrate_to]

        try:
            self._flush_deferred_constraints()
            self.executor.migrate(old_target)
            old_apps = self.executor.loader.project_state(old_target).apps

            User = old_apps.get_model("auth", "User")
            UserProfile = old_apps.get_model("core", "UserProfile")
            MasterProfile = old_apps.get_model("core", "MasterProfile")
            MasterRoom = old_apps.get_model("core", "MasterRoom")
            Service = old_apps.get_model("core", "Service")
            ServiceMaster = old_apps.get_model("core", "ServiceMaster")
            Appointment = old_apps.get_model("core", "Appointment")
            AppointmentItem = old_apps.get_model("core", "AppointmentItem")
            AppointmentStatus = old_apps.get_model("core", "AppointmentStatus")
            AppointmentStatusHistory = old_apps.get_model("core", "AppointmentStatusHistory")
            PaymentStatus = old_apps.get_model("core", "PaymentStatus")

            now = timezone.now().replace(microsecond=0)

            client_user = User.objects.create_user(username="client-mig", password="test123")
            client_profile = UserProfile.objects.create(user=client_user)

            master_user = User.objects.create_user(username="master-mig", password="test123")
            master_profile_user = UserProfile.objects.create(user=master_user)
            master_profile = MasterProfile.objects.create(user=master_profile_user)

            admin_user = User.objects.create_user(username="admin-mig", password="test123")
            admin_profile = UserProfile.objects.create(user=admin_user)

            payment_status = PaymentStatus.objects.create(name="Not Paid")

            service = Service.objects.create(
                name="Therapy Session",
                base_price=Decimal("100.00"),
                duration_min=60,
                extra_time_min=0,
            )
            room = MasterRoom.objects.create(room="Room A")
            service.allowed_rooms.add(room)
            ServiceMaster.objects.create(service=service, master=master_profile)

            appointment = Appointment.objects.create(
                client=client_profile,
                payment_status=payment_status,
                start_time=now,
            )

            item_ids = []
            for offset in range(3):
                item = AppointmentItem.objects.create(
                    appointment=appointment,
                    service=service,
                    master=master_profile,
                    start_time=now + timedelta(hours=offset),
                    unit_price=service.base_price,
                )
                item_ids.append(str(item.pk))

            cancelled_status = AppointmentStatus.objects.create(name="Cancelled")
            AppointmentStatusHistory.objects.create(
                appointment=appointment,
                status=cancelled_status,
                set_by=admin_profile,
            )

            appointment_id = str(appointment.pk)

            self._flush_deferred_constraints()
            self.executor.migrate(new_target)
            self._flush_deferred_constraints()

        finally:
            self._migrate_to_head()
            from core.models import (
                Appointment,
                AppointmentItem,
                AppointmentItemStatusHistory,
            )

            runtime_items = list(
                AppointmentItem.objects.filter(appointment_id=appointment_id).values_list("status__code", flat=True)
            )
            self.assertEqual(len(runtime_items), 3)
            self.assertEqual(set(runtime_items), {"CANCELLED"})

            history_entries = AppointmentItemStatusHistory.objects.filter(
                item__appointment_id=appointment_id
            )
            self.assertEqual(history_entries.count(), 3)
            self.assertEqual(
                {str(entry.item_id) for entry in history_entries},
                set(item_ids),
            )

            runtime_appt = Appointment.objects.get(pk=appointment_id)
            self.assertEqual(runtime_appt.aggregated_status_code, "CANCELLED")
            self.assertEqual(runtime_appt.aggregated_status, "Cancelled")

    def test_backward_migration_drops_item_status_models(self):
        old_target = [self.migrate_from]
        new_target = [self.migrate_to]

        try:
            self._flush_deferred_constraints()
            self.executor.migrate(new_target)

            from core.models import (
                Appointment,
                AppointmentItem,
                AppointmentItemStatus,
                AppointmentItemStatusHistory,
                AppointmentStatusHistory,
                AppointmentStatus,
                MasterProfile,
                PaymentStatus,
                Service,
                ServiceMaster,
                UserProfile,
            )
            from django.contrib.auth import get_user_model
            from core.models import MasterRoom

            User = get_user_model()
            now = timezone.now().replace(microsecond=0)

            client = User.objects.create_user(username="client-back", password="test123")
            client_profile = UserProfile.objects.create(user=client)

            master_user = User.objects.create_user(username="master-back", password="test123")
            master_profile = MasterProfile.objects.create(user=UserProfile.objects.create(user=master_user))

            admin_user = User.objects.create_user(username="admin-back", password="test123")
            admin_profile = UserProfile.objects.create(user=admin_user)

            payment_status = PaymentStatus.objects.create(name="Not Paid")
            service = Service.objects.create(
                name="Consultation",
                base_price=Decimal("75.00"),
                duration_min=45,
                extra_time_min=0,
            )
            room = MasterRoom.objects.create(room="Room B")
            service.allowed_rooms.add(room)
            ServiceMaster.objects.create(service=service, master=master_profile)

            appointment = Appointment.objects.create(
                client=client_profile,
                payment_status=payment_status,
                start_time=now,
            )
            status_confirmed = AppointmentItemStatus.objects.get(code="CONFIRMED")
            items = []
            for offset in range(2):
                item = AppointmentItem.objects.create(
                    appointment=appointment,
                    service=service,
                    master=master_profile,
                    start_time=now + timedelta(hours=offset),
                    unit_price=service.base_price,
                    status=status_confirmed,
                )
                AppointmentItemStatusHistory.objects.create(
                    item=item,
                    status=status_confirmed,
                    set_by=admin_user,
                )
                items.append(str(item.pk))

            legacy_status = AppointmentStatus.objects.create(name="Confirmed")
            AppointmentStatusHistory.objects.create(
                appointment=appointment,
                status=legacy_status,
                set_by=admin_profile,
            )

            self._flush_deferred_constraints()
            self.executor.migrate(old_target)
            old_apps = self.executor.loader.project_state(old_target).apps
            OldItem = old_apps.get_model("core", "AppointmentItem")

            fresh_item = OldItem.objects.get(pk=items[0])
            field_names = {field.name for field in OldItem._meta.get_fields()}
            self.assertNotIn("status", field_names)

            table_names = connection.introspection.table_names()
            self.assertNotIn("core_appointmentitemstatus", table_names)
            self.assertNotIn("core_appointmentitemstatushistory", table_names)

        finally:
            self._migrate_to_head()



