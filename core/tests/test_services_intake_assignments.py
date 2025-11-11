from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.db.models.signals import post_save

from core.models import (
    ClientIntakeAssignment,
    ClientIntakeForm,
    UserProfile,
)
from core import signals as core_signals
from core.services.intake_assignments import (
    _filter_assignable_forms,
    ensure_assignments,
    ensure_universal_assignments_for_form,
    ensure_universal_assignments_for_profile,
)


class IntakeAssignmentServiceTests(TestCase):
    def setUp(self) -> None:
        self.user_model = get_user_model()
        self.profile = self._make_profile("client-assignments@example.com")
        post_save.disconnect(core_signals.ensure_profile_universal_assignments, sender=UserProfile)
        post_save.disconnect(core_signals.ensure_universal_assignments, sender=ClientIntakeForm)
        self.addCleanup(
            lambda: post_save.connect(core_signals.ensure_profile_universal_assignments, sender=UserProfile)
        )
        self.addCleanup(
            lambda: post_save.connect(core_signals.ensure_universal_assignments, sender=ClientIntakeForm)
        )

    def _make_profile(self, username: str) -> UserProfile:
        user = self.user_model.objects.create(username=username, email=username)
        return UserProfile.objects.create(user=user)

    def _make_form(self, name: str, *, is_active: bool = True, is_universal: bool = False) -> ClientIntakeForm:
        slug = name.lower().replace(" ", "-")
        suffix = ClientIntakeForm.objects.count()
        return ClientIntakeForm.objects.create(
            name=name,
            slug=f"{slug}-{suffix}",
            is_active=is_active,
            is_universal=is_universal,
            schema={"meta": {"version": 1}, "sections": []},
        )

    def test_filter_assignable_forms_keeps_unique_active(self) -> None:
        active_one = self._make_form("Active One")
        inactive = self._make_form("Inactive", is_active=False)
        active_two = self._make_form("Active Two")

        result = _filter_assignable_forms([active_one, inactive, active_one, None, active_two])

        self.assertEqual(result, [active_one, active_two])

    def test_ensure_assignments_creates_missing_records(self) -> None:
        form_one = self._make_form("Form One")
        form_two = self._make_form("Form Two")

        created = ensure_assignments(profile=self.profile, forms=[form_one, form_two, form_one])

        self.assertEqual(created, 2)
        assigned_forms = set(
            ClientIntakeAssignment.objects.filter(client=self.profile).values_list("form_id", flat=True)
        )
        self.assertEqual(assigned_forms, {form_one.pk, form_two.pk})

    def test_ensure_assignments_ignores_existing(self) -> None:
        form_one = self._make_form("Existing Form")
        ClientIntakeAssignment.objects.create(form=form_one, client=self.profile)

        created = ensure_assignments(profile=self.profile, forms=[form_one])

        self.assertEqual(created, 0)
        self.assertEqual(
            ClientIntakeAssignment.objects.filter(client=self.profile, form=form_one).count(),
            1,
        )

    def test_ensure_assignments_returns_zero_without_profile_or_forms(self) -> None:
        form = self._make_form("Another Form")
        self.assertEqual(ensure_assignments(profile=None, forms=[form]), 0)
        self.assertEqual(ensure_assignments(profile=self.profile, forms=[]), 0)

    def test_ensure_universal_assignments_for_profile_limits_to_active_universal(self) -> None:
        universal_active = self._make_form("Universal A", is_universal=True, is_active=True)
        universal_inactive = self._make_form("Universal B", is_universal=True, is_active=False)
        non_universal = self._make_form("Non Universal", is_universal=False, is_active=True)

        created = ensure_universal_assignments_for_profile(self.profile)

        self.assertEqual(created, 1)
        self.assertTrue(
            ClientIntakeAssignment.objects.filter(client=self.profile, form=universal_active).exists()
        )
        self.assertFalse(
            ClientIntakeAssignment.objects.filter(client=self.profile, form=universal_inactive).exists()
        )
        self.assertFalse(
            ClientIntakeAssignment.objects.filter(client=self.profile, form=non_universal).exists()
        )

    def test_ensure_universal_assignments_for_form_requires_universal_active(self) -> None:
        non_universal = self._make_form("Standalone Form", is_universal=False)
        inactive = self._make_form("Inactive Universal", is_universal=True, is_active=False)

        self.assertEqual(ensure_universal_assignments_for_form(non_universal), 0)
        self.assertEqual(ensure_universal_assignments_for_form(inactive), 0)

    def test_ensure_universal_assignments_for_form_bulk_batches_clients(self) -> None:
        intake_form = self._make_form("Universal Bulk", is_universal=True, is_active=True)
        existing_profile = self._make_profile("existing-bulk@example.com")
        ClientIntakeAssignment.objects.get_or_create(form=intake_form, client=existing_profile)

        new_profiles: list[UserProfile] = []
        for index in range(501):
            profile = self._make_profile(f"profile-{index}@example.com")
            new_profiles.append(profile)

        manager = ClientIntakeAssignment.objects
        original_bulk = manager.bulk_create

        existing_ids = set(
            ClientIntakeAssignment.objects.filter(form=intake_form).values_list("client_id", flat=True)
        )
        expected_created = UserProfile.objects.exclude(pk__in=existing_ids).count()
        self.assertGreaterEqual(expected_created, 500)

        batch_lengths: list[int] = []

        def _recording_bulk_create(records, *args, **kwargs):
            batch_lengths.append(len(records))
            return original_bulk(records, *args, **kwargs)

        with patch.object(manager, "bulk_create", side_effect=_recording_bulk_create):
            created = ensure_universal_assignments_for_form(intake_form)

        self.assertEqual(created, expected_created)
        self.assertGreaterEqual(len(batch_lengths), 2)
        self.assertIn(500, batch_lengths)
        remainder = expected_created - 500
        self.assertIn(remainder, batch_lengths)

        total_assignments = ClientIntakeAssignment.objects.filter(form=intake_form).count()
        self.assertEqual(total_assignments, expected_created + len(existing_ids))
