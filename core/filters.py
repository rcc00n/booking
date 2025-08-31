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

class AppointmentServiceFilter(admin.SimpleListFilter):
    title = _("услуга (через позиции)")
    parameter_name = "service"

    def lookups(self, request, model_admin):
        qs = Service.objects.all()
        if hasattr(Service, "is_active"):
            qs = qs.filter(is_active=True)
        return [(str(s.pk), getattr(s, "name", f"Service {s.pk}")) for s in qs.order_by("name")[:500]]

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        return queryset.filter(appointmentitem__service_id=value).distinct()


class AppointmentItemMasterFilter(admin.SimpleListFilter):
    title = _("мастер (через позиции)")
    parameter_name = "item_master"

    def lookups(self, request, model_admin):
        qs = UserProfile.objects.all()
        # если есть роль Мастер — можно отфильтровать только их
        if hasattr(UserProfile, "is_master"):
            qs = qs.filter(is_master=True)
        return [(str(u.pk), getattr(u, "short_name", getattr(u, "user", str(u)))) for u in qs.order_by("id")[:500]]

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        return queryset.filter(appointmentitem__master_id=value).distinct()


class AppointmentHasPromocodeFilter(admin.SimpleListFilter):
    title = _("есть промокоды в позициях")
    parameter_name = "has_promocode"

    def lookups(self, request, model_admin):
        return [("yes", _("Да")), ("no", _("Нет"))]

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        if value == "yes":
            return queryset.filter(appointmentitem__promocode__isnull=False).distinct()
        else:
            return queryset.exclude(appointmentitem__promocode__isnull=False).distinct()

