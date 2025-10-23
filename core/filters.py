from __future__ import annotations

from django.contrib.admin import SimpleListFilter
from .models import *

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.apps import apps

class ClientStatusFilter(SimpleListFilter):
    title = "Client Status"
    parameter_name = "client_status"

    LOOKUP_TO_LABEL = {
        "new": "New Client",
        "regular": "Regular Client",
        "vip": "VIP",
        "super_vip": "Super VIP",
    }

    def lookups(self, request, model_admin):
        return [(k, v) for k, v in self.LOOKUP_TO_LABEL.items()]

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        target_label = self.LOOKUP_TO_LABEL.get(value)
        if not target_label:
            return queryset.none()

        # Собираем id пользователей (auth_user.id), чьи профили попадают под нужный статус
        ids = [
            up.user_id
            for up in UserProfile.objects.select_related("user").only("user_id")
            if up.client_status == target_label
        ]
        return queryset.filter(id__in=ids)


class MasterRoleFilter(SimpleListFilter):
    title = "Is Master"
    parameter_name = "is_master"

    def lookups(self, request, model_admin):
        return (("yes", "Yes"),)

    def queryset(self, request, queryset):
        if self.value() == "yes":
            master_role = Role.objects.filter(name="Master").first()
            if master_role:
                master_ids = UserRole.objects.filter(role=master_role).values_list("user_id", flat=True)
                return queryset.filter(id__in=master_ids)
        return queryset


class StaffSetByFilter(SimpleListFilter):
    title = _("Set by")
    parameter_name = "set_by"

    def lookups(self, request, model_admin):
        staff_profiles = (
            UserProfile.objects
            .filter(user__is_staff=True)
            .select_related("user")
            .order_by("user__first_name", "user__last_name", "user__username")
            .distinct()
        )
        options = []
        for profile in staff_profiles:
            full_name = (profile.get_full_name() or "").strip()
            label = full_name or profile.user.get_username()
            options.append((str(profile.pk), label))
        return options

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        return queryset.filter(set_by_id=value)


