"""
Utilities for managing client intake form assignments.
"""
from __future__ import annotations

from typing import Iterable, Sequence

from django.db import transaction

from core.models import (
    ClientIntakeAssignment,
    ClientIntakeForm,
    UserProfile,
)


def _filter_assignable_forms(forms: Iterable[ClientIntakeForm]) -> list[ClientIntakeForm]:
    """
    Ensure we only attempt to assign active forms.
    """
    unique = []
    seen: set[str] = set()
    for form in forms:
        if not form or not form.is_active:
            continue
        fid = str(form.pk)
        if fid in seen:
            continue
        seen.add(fid)
        unique.append(form)
    return unique


def ensure_assignments(
    *,
    profile: UserProfile,
    forms: Sequence[ClientIntakeForm],
    assigned_by=None,
) -> int:
    """
    Assign the provided forms to the client profile if not already assigned.

    Returns number of assignments created.
    """
    if profile is None:
        return 0

    assignable = _filter_assignable_forms(forms)
    if not assignable:
        return 0

    existing = set(
        ClientIntakeAssignment.objects.filter(client=profile, form__in=assignable).values_list("form_id", flat=True)
    )
    payload = []
    for form in assignable:
        if form.pk in existing:
            continue
        payload.append(
            ClientIntakeAssignment(
                form=form,
                client=profile,
                assigned_by=assigned_by,
            )
        )

    if not payload:
        return 0

    created = ClientIntakeAssignment.objects.bulk_create(payload, ignore_conflicts=True)
    return len(created)


def ensure_universal_assignments_for_profile(profile: UserProfile) -> int:
    """
    Guarantee that the profile has assignments for all active universal forms.
    """
    universal_forms = ClientIntakeForm.objects.filter(is_active=True, is_universal=True)
    return ensure_assignments(profile=profile, forms=universal_forms)


def ensure_universal_assignments_for_form(intake_form: ClientIntakeForm) -> int:
    """
    Guarantee that all client profiles receive an assignment for the specified universal form.

    Returns number of assignments created.
    """
    if intake_form is None or not intake_form.is_universal or not intake_form.is_active:
        return 0

    # Use a transaction to maintain consistency when bulk-creating.
    created_total = 0
    with transaction.atomic():
        existing_ids = set(
            ClientIntakeAssignment.objects.filter(form=intake_form).values_list("client_id", flat=True)
        )
        queryset = UserProfile.objects.exclude(pk__in=existing_ids)

        batch = []
        for profile in queryset.iterator(chunk_size=500):
            batch.append(
                ClientIntakeAssignment(
                    form=intake_form,
                    client=profile,
                )
            )
            if len(batch) >= 500:
                created_total += len(
                    ClientIntakeAssignment.objects.bulk_create(batch, ignore_conflicts=True)
                )
                batch.clear()

        if batch:
            created_total += len(
                ClientIntakeAssignment.objects.bulk_create(batch, ignore_conflicts=True)
            )

    return created_total
