from bisect import bisect_left
from collections import defaultdict
from typing import Dict, Any, List
from urllib.parse import urlencode

from django.contrib.admin import DateFieldListFilter

from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.core.exceptions import FieldError
from django.db import transaction, IntegrityError
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.contrib import admin, messages
from django.db.models import Sum, Count, Q, F, ExpressionWrapper, IntegerField
from itertools import cycle

from django.utils.formats import number_format
from django.utils.timezone import localtime, datetime, make_aware, localdate, get_current_timezone, make_naive
from django.utils.html import escape
from core.utils.admin_perms import is_master, master_obj
from django.shortcuts import redirect
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from datetime import date, timedelta
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse, Http404
from django.contrib.auth.models import Permission
from django.db.models.functions import Coalesce, Concat, Greatest
from django.db.models import DecimalField, Value
from django.contrib.contenttypes.models import ContentType
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json
from django.utils.dateparse import parse_date
import csv
from django.utils.translation import gettext_lazy as _
from django.urls import path, reverse, NoReverseMatch, re_path
from django.http import HttpResponse
from django.shortcuts import render
from .filters import *
from .models import *
from .forms import *
from .validators import *
from core.services.user_import import (
    import_users_from_file,
    UserImportError,
    UserImportSchemaError,
)

# -----------------------------
# Custom filter for filtering users by Role
# -----------------------------

# Переопределение index view
from datetime import timedelta
from django.contrib import admin
from django.db.models import Count, Sum, Q, F
from django.template.response import TemplateResponse
from django.utils import timezone
from django.utils.timezone import localdate

from core.models import (
    Appointment, AppointmentItem, Payment,
    AppointmentStatus, Role, MasterProfile, Service
)


def custom_index(request):
    today = localdate()
    now = timezone.now()
    week_ago = today - timedelta(days=6)
    week_days = [today - timedelta(days=6 - i) for i in range(7)]
    first_day = today.replace(day=1)

    # Базовые QS
    appts_7d = Appointment.objects.filter(start_time__date__range=[week_ago, today])
    payments_7d = Payment.objects.filter(appointment__start_time__date__range=[week_ago, today])

    # Роль/профиль мастера
    userprof = getattr(request.user, "userprofile", None)

    master_profile = getattr(userprof, "master_profile", None) if userprof else None

    # График продаж/записей за 7 дней
    chart_data, total_sales = [], 0.0
    for i in range(7):
        day = today - timedelta(days=6 - i)
        sales = payments_7d.filter(appointment__start_time__date=day) \
                    .aggregate(total=Sum("amount"))["total"] or 0
        appts = appts_7d.filter(start_time__date=day).distinct().count()
        total_sales += float(sales)

        chart_data.append({"day": day.strftime("%a %d"), "sales": float(sales), "appointments": appts})

    # Статусы и счётчики на ближайшие 7 дней
    confirmed = AppointmentStatus.objects.filter(name="Confirmed").first()
    cancelled = AppointmentStatus.objects.filter(name="Cancelled").first()

    upcoming = Appointment.objects.filter(
        start_time__date__range=(today, today + timedelta(days=7))
    )
    confirmed_count = upcoming.filter(appointmentstatushistory__status=confirmed) \
        .distinct().count() if confirmed else 0
    cancelled_count = upcoming.filter(appointmentstatushistory__status=cancelled) \
        .distinct().count() if cancelled else 0

    # Top services (текущий месяц) — считаем позиции у Service через обратную связь "appointmentitem"
    top_services = (
        Service.objects.annotate(
            count=Count(
                "appointmentitem",
                filter=Q(appointmentitem__appointment__start_time__date__gte=first_day),
            )
        )
        .order_by("-count")[:10]
    )
    first_day = today.replace(day=1)

    # Берём уникальные пары (master, appointment), где есть хотя бы один Item этого мастера
    pairs = (
        AppointmentItem.objects
        .filter(appointment__start_time__date__gte=first_day)
        .values("master_id", "appointment_id")
        .distinct()
    )

    # Сколько мастеров участвует в каждой встрече (для деления платежа)
    masters_count_sq = (
        Appointment.objects
        .filter(pk=OuterRef("appointment_id"))
        .annotate(mc=Count("items__master", distinct=True))
        .values("mc")[:1]
    )

    # Сумма платежей по каждой встрече (на случай если платежей несколько)
    paid_total_sq = (
        Payment.objects
        .filter(appointment_id=OuterRef("appointment_id"))
        .values("appointment_id")
        .annotate(total=Sum("amount"))
        .values("total")[:1]
    )

    pairs = pairs.annotate(
        masters_count=Subquery(masters_count_sq, output_field=IntegerField()),
        paid_total=Subquery(paid_total_sq, output_field=DecimalField(max_digits=12, decimal_places=2)),
    ).annotate(
        # вклад мастера в эту встречу: total_payment / masters_count
        contrib=ExpressionWrapper(
            Coalesce(F("paid_total"), Value(0))
            / Greatest(Coalesce(F("masters_count"), Value(1)), Value(1)),
            output_field=DecimalField(max_digits=12, decimal_places=2),
            )
    )

    # Суммируем вклады по всем встречам для каждого мастера
    agg = (
        pairs.values("master_id")
        .annotate(total=Sum("contrib"))
        .order_by("-total")[:10]
    )

    # Берём сами профили мастеров и прикрепляем им поле .total
    master_totals = {row["master_id"]: (row["total"] or 0) for row in agg}
    top_masters_qs = MasterProfile.objects.filter(pk__in=master_totals.keys()).select_related("user")
    top_masters = list(top_masters_qs)
    for m in top_masters:
        m.total = master_totals.get(m.pk, 0)

    # Отсортировать финально по total (на случай несохранённого порядка)
    top_masters = sorted(top_masters, key=lambda m: m.total or 0, reverse=True)[:10]

    # Недавние встречи (20) с префетчем позиций
    recent_appointments = (
        Appointment.objects.select_related("client__user")
        .prefetch_related(
            Prefetch(
                "items",
                queryset=AppointmentItem.objects.select_related("service", "master__user")
                .order_by("start_time"),
                )
        )
        .order_by("-start_time")[:20]
    )

    # Сегодняшние предстоящие встречи (Appointment + items); мастеру — только его
    today_appointments = (
        AppointmentItem.objects.filter(start_time__date=today, start_time__gte=now)
        .select_related("appointment__client__user")
        .order_by("start_time")
    )
    if is_master(request.user) and master_profile:
        today_appointments = today_appointments.filter(master=master_profile).distinct()

    # Ежедневная разбивка Confirmed/Cancelled (на 7 дней вперёд)
    daily_counts = []
    for day in week_days:
        c = Appointment.objects.filter(start_time__date=day,
                                       appointmentstatushistory__status=confirmed) \
            .distinct().count() if confirmed else 0
        x = Appointment.objects.filter(start_time__date=day,
                                       appointmentstatushistory__status=cancelled) \
            .distinct().count() if cancelled else 0
        daily_counts.append({"day": day.strftime("%a %d"), "confirmed": c, "cancelled": x})

    context = admin.site.each_context(request)
    context.update({
        "is_master": is_master(request.user),
        "daily_appointments": daily_counts,
        "chart_data": chart_data,
        "total_sales": total_sales,
        "upcoming_total": upcoming.count(),
        "confirmed_count": confirmed_count,
        "cancelled_count": cancelled_count,
        "top_services": top_services,      # Service с .name и .count
        "top_masters": top_masters,        # MasterProfile с .total
        "today": today,
        "recent_appointments": recent_appointments,
        "today_appointments": today_appointments,
    })
    return TemplateResponse(request, "admin/index.html", context)

# Переопределить главную страницу
admin.site.index = custom_index
class ExportCsvMixin:
    export_fields = None  # список полей; можно переопределить в admin

    def get_urls(self):
        opts = self.model._meta
        return [
            path(
                "export-csv/",
                self.admin_site.admin_view(self.export_all_csv),
                name=f"{opts.app_label}_{opts.model_name}_export_csv"
            )
        ] + super().get_urls()

    def export_all_csv(self, request):
        queryset = self.get_queryset(request)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename={self.model._meta.model_name}.csv'

        fields = self.export_fields or [field.name for field in self.model._meta.fields]
        writer = csv.writer(response)
        writer.writerow(fields)

        for obj in queryset:
            if hasattr(self, 'get_export_row'):
                row = self.get_export_row(obj)
            else:
                row = [getattr(obj, field) for field in fields]
            writer.writerow(row)

        return response

    def changelist_view(self, request, extra_context=None):
        # Попробуем reverse без краша
        extra_context = extra_context or {}
        try:
            opts = self.model._meta
            export_url = reverse(f'admin:{opts.app_label}_{opts.model_name}_export_csv')
            export_url += f"?{request.GET.urlencode()}"
            extra_context['export_url'] = export_url
        except NoReverseMatch:
            extra_context['export_url'] = None

        return super().changelist_view(request, extra_context=extra_context)
# -----------------------------
# Customized User Admin
# -----------------------------
class CustomUserAdmin(ExportCsvMixin ,BaseUserAdmin):
    """
    Custom admin interface for Django's User model, enhanced with roles and profile fields.
    """
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    export_fields = ['username', 'email', 'first_name', 'last_name', 'phone', 'birth_date', 'postal_code', 'is_staff', 'is_superuser', 'is_active', 'source', 'consent']

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'username', 'usable_password', 'password1', 'password2',
                'email', 'first_name', 'last_name',
                'phone', 'birth_date', 'postal_code',
                'personal_discount_percent', 'how_heard', 'email_marketing_consent',
                'notes',
                'is_active', 'is_staff', 'is_superuser', 'groups',
            ),
        }),
        ('Health', {
            'classes': ('collapse',),
            'fields': (
                'has_allergies', 'allergies_text', 'gender',
                'chronic_conditions', 'medications', 'pregnant',
                'skin_sensitivity', 'recent_procedures',
                'contraindications', 'health_notes',
            ),
        }),
    )

    def get_export_row(self, obj):
        phone = obj.userprofile.phone if hasattr(obj, 'userprofile') else ''
        birth_date = obj.userprofile.birth_date if hasattr(obj, 'userprofile') else ''
        postal_code = obj.userprofile.postal_code if hasattr(obj, 'userprofile') else ''
        source = obj.userprofile.source if hasattr(obj, 'userprofile') else ''
        consent = obj.userprofile.email_marketing_consent if hasattr(obj, 'userprofile') else ''

        return [
            obj.username,
            obj.email,
            obj.first_name,
            obj.last_name,
            phone,
            birth_date,
            postal_code,
            obj.is_staff,
            obj.is_superuser,
            obj.is_active,
            source,
            consent
        ]
    # Fields shown when adding a new user


    # Fields shown in user list
    list_display = ('username', 'email', 'first_name', 'last_name', 'staff_status', 'phone', 'birth_date', 'source', 'client_status_col')
    list_filter = ('is_superuser', 'userprofile__how_heard', ClientStatusFilter)
    search_fields = ('username', 'email', 'first_name', 'last_name', 'userprofile__phone')

    # Field layout when editing a user
    fieldsets = (
        (None, {'fields': ('username', 'email', 'password', 'personal_discount_percent')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'phone', 'birth_date', 'postal_code', 'how_heard', 'email_marketing_consent')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Files', {'fields': ('files',)}),
        ('Notes', {'fields': ('notes',)}),
        ('Health', {
            'classes': ('collapse', 'wide'),
            'fields': (
                'has_allergies', 'allergies_text', 'gender',
                'chronic_conditions', 'medications',
                'pregnant', 'skin_sensitivity',
                'recent_procedures', 'contraindications',
                'health_notes',
            ),
        }),
    )

    def get_queryset(self, request):
        # чтобы не ловить N+1
        return super().get_queryset(request).select_related('userprofile')

    @admin.display(description="Status")
    def client_status_col(self, obj):
        up = getattr(obj, 'userprofile', None)
        return getattr(up, 'client_status', '-') if up else ('-')

    @admin.display(description="Source")
    def source(self, obj):
        up = getattr(obj, 'userprofile', None)
        return getattr(up, 'source', '-') if up else '-'

    def get_fieldsets(self, request, obj=None):
        # Allow Django to use default fieldsets logic
        return super().get_fieldsets(request, obj)

    def get_form(self, request, obj=None, **kwargs):
        # Return different form on add vs change
        return self.add_form if obj is None else self.form

    def save_model(self, request, obj, form, change):
        # Save user and assign roles
        super().save_model(request, obj, form, change)

    # Custom display methods for user profile fields
    def phone(self, instance):
        return instance.userprofile.phone if hasattr(instance, 'userprofile') else '-'

    def birth_date(self, instance):
        return instance.userprofile.birth_date if hasattr(instance, 'userprofile') else '-'

    def _maybe_redirect_back(self, request, response):
        """
        Если пришли из Appointment (по нашему параметру _from_appointment),
        вернёмся на календарь визитов.
        """
        if "_from_appointment" in request.GET or "_from_appointment" in request.POST:

            return redirect(reverse("admin:core_appointment_changelist"))
        return response

    def response_add(self, request, obj, post_url_continue=None):
        resp = super().response_add(request, obj, post_url_continue)
        return self._maybe_redirect_back(request, resp)

    def response_change(self, request, obj):
        resp = super().response_change(request, obj)
        return self._maybe_redirect_back(request, resp)

    def response_delete(self, request, obj_display, obj_id):
        resp = super().response_delete(request, obj_display, obj_id)
        return self._maybe_redirect_back(request, resp)

    @admin.display(description="")
    def send_notify_button(self, obj):
        return mark_safe(
            f'<button type="button" class="send-notify-btn" '
            f'data-user-id="{obj.id}" '
            f'data-user-name="{obj.get_full_name() or obj.username}">Send Notification</button>'
        )
    def get_urls(self):
        urls = super().get_urls()
        opts = self.model._meta
        custom_urls = [
            path(
                'import-users/',
                self.admin_site.admin_view(self.import_users_view),
                name=f'{opts.app_label}_{opts.model_name}_import',
            ),
            path('send_notification/', self.admin_site.admin_view(self.send_notification_view), name='send_notification'),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        try:
            opts = self.model._meta
            extra_context.setdefault(
                'import_url',
                reverse(f'admin:{opts.app_label}_{opts.model_name}_import'),
            )
            extra_context.setdefault('import_label', 'Import users')
        except NoReverseMatch:
            pass
        return super().changelist_view(request, extra_context=extra_context)

    def import_users_view(self, request):
        opts = self.model._meta
        form = UserImportUploadForm()
        if request.method == "POST":
            form = UserImportUploadForm(request.POST, request.FILES)
            if form.is_valid():
                uploaded = form.cleaned_data["import_file"]
                try:
                    result = import_users_from_file(uploaded)
                except UserImportSchemaError as exc:
                    form.add_error("import_file", str(exc))
                except UserImportError as exc:
                    form.add_error(None, str(exc))
                else:
                    if result.created:
                        messages.success(request, f"Imported {result.created} user(s).")
                    if result.errors:
                        snippet = result.errors[:10]
                        list_html = format_html_join(
                            '',
                            '<li>Row {0} ({1}): {2}</li>',
                            (
                                (
                                    message.row_number,
                                    message.username or '-',
                                    message.message,
                                )
                                for message in snippet
                            ),
                        )
                        remaining = len(result.errors) - len(snippet)
                        tail = ""
                        if remaining > 0:
                            tail = format_html('<p>... and {} more row(s) with issues.</p>', remaining)
                        messages.error(
                            request,
                            format_html('Some rows could not be imported:<ul>{}</ul>{}', list_html, tail),
                        )

                    changelist_url = reverse(f'admin:{opts.app_label}_{opts.model_name}_changelist')
                    return redirect(changelist_url)

        context = {
            **self.admin_site.each_context(request),
            "opts": opts,
            "form": form,
            "title": "Import users",
        }
        return TemplateResponse(request, "admin/user_import.html", context)

    @method_decorator(csrf_exempt)
    def send_notification_view(self, request):
        if request.method == "POST":
            data = json.loads(request.body)
            user_id = data.get("user_id")
            message = data.get("message")

            user = UserProfile.objects.filter(id=user_id).first()
            if user:
                Notification.objects.create(
                    user=user,
                    message=message,
                    channel="email"  # или sms
                )
                return JsonResponse({"status": "ok"})

        return JsonResponse({"status": "error"}, status=400)
    @admin.display(boolean=True, description="Staff Status")
    def staff_status(self, instance):
        return instance.is_staff
    staff_status.boolean = True


# Unregister the default User admin and re-register with our custom one
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


@admin.register(MasterAvailability)
class MasterAvailabilityAdmin(ExportCsvMixin, admin.ModelAdmin):
    form = MasterAvailabilityForm
    list_display = ("master", "start_time", "end_time", "reason")
    list_filter = ("master",)
    search_fields = ("master__first_name", "master__last_name", "reason")
    export_fields = ["master", "start_time", "end_time", "reason"]

    def _redirect_to_appointments(self, request):
        url = reverse("admin:core_appointment_changelist")
        # переносим дату (и любые будущие параметры из календаря)
        passthrough = {}
        for key in ("date",):
            val = request.GET.get(key) or request.POST.get(key)
            if val:
                passthrough[key] = val
        if passthrough:
            url = f"{url}?{urlencode(passthrough)}"
        return redirect(url)

    # ---- после добавления ----
    def response_add(self, request, obj, post_url_continue=None):
        # всегда назад в календарь записей
        return self._redirect_to_appointments(request)

    # ---- после изменения ----
    def response_change(self, request, obj):
        # даже если нажали "Сохранить и продолжить" — уводим в календарь
        return self._redirect_to_appointments(request)

    # ---- после удаления ----
    def response_delete(self, request, obj_display, obj_id):
        return self._redirect_to_appointments(request)

    def has_add_permission(self, request):
        if request.user.is_superuser or request.user.is_staff:
            return True
        return hasattr(request.user, "master_profile")

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser or request.user.is_staff:
            return True
        if hasattr(request.user, "master_profile"):
            # список — разрешаем открыть; конкретный объект — только свой
            return True if obj is None else (obj.master_id == request.user.master_profile.id)
        return False

    # --- удаление: только свои (админ/стфф — любые)
    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser or request.user.is_staff:
            return True
        if hasattr(request.user, "master_profile"):
            return True if obj is None else (obj.master_id == request.user.master_profile.id)
        return False

    # --- только свои time off ---
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if hasattr(request.user, "master_profile") and not request.user.is_superuser:
            return qs.filter(master=request.user.master_profile)
        return qs
    def get_form(self, request, obj=None, **kwargs):
        BaseForm = super().get_form(request, obj, **kwargs)

        class WrappedForm(BaseForm):
            def __init__(self, *args, **kw):
                super().__init__(*args, **kw)
                # Только для мастеров (не суперюзеров/стффа)
                if hasattr(request.user, "master_profile") and not request.user.is_superuser:
                    if "master" in self.fields:
                        # визуально фиксируем поле
                        self.fields["master"].disabled = True
        return WrappedForm

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)

        date_str = request.GET.get("date")
        time_str = request.GET.get("time")
        const_master = request.GET.get("master")

        if date_str and time_str:
            try:
                combined = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
                initial["start_time"] = make_aware(combined)

            except ValueError:
                pass
        if const_master:
            initial["master"] = const_master
        if hasattr(request.user, "master_profile") and not request.user.is_superuser:
            initial["master"] = request.user.master_profile.id

        return initial


# -----------------------------
# Appointment Admin
# -----------------------------


def _can_override_discount_rule(user) -> bool:
    """Право на одновременную скидку услуги и промокод в одной позиции."""
    return bool(
        getattr(user, "is_superuser", False)
        or user.has_perm("core.bypass_service_discount_rule")  # NOTE: при желании задай такой perm
    )


def _can_edit_unit_price(user) -> bool:
    """Право редактировать индивидуальную цену позиции (unit_price)."""
    return bool(
        getattr(user, "is_superuser", False)
        or user.has_perm("core.can_edit_unit_price")  # NOTE: при желании задай такой perm
    )


# ──────────────────────────────────────────────────────────────────────────────
# Inline: AppointmentItem
# ──────────────────────────────────────────────────────────────────────────────

class AppointmentItemInline(admin.TabularInline):
    model = AppointmentItem
    form = AppointmentItemInlineForm
    fk_name = "appointment"
    extra = 0
    # autocomplete_fields = ["service", "master", "promocode"]  # если используете автокомплит

    def get_formset(self, request, obj=None, **kwargs):
        """
        obj — это родитель (Appointment). Передадим его в каждую форму через kwargs.
        А ещё скорректируем queryset для промокода, чтобы уже выбранный (даже неактивный) отображался.
        """
        parent = obj
        FormSet = super().get_formset(request, obj, **kwargs)

        class PrefillFormSet(FormSet):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                # Если у вас в форме есть поле 'promocode' и вы фильтруете только активные,
                # добиваемся, чтобы выбранный ранее промокод тоже был в queryset:
                for form in self.forms:
                    if hasattr(form, "fix_promocode_queryset"):
                        form.fix_promocode_queryset()

            def _construct_form(self, i, **kw):
                # Передаём родителя в конструктор формы
                kw.setdefault("parent_obj", parent)
                return super()._construct_form(i, **kw)

        return PrefillFormSet

    def has_delete_permission(self, request, obj=None):

        return True


# ──────────────────────────────────────────────────────────────────────────────
# CSV helpers
# ──────────────────────────────────────────────────────────────────────────────

def _money(x):
    return f"{x:.2f}" if x is not None else ""


# ──────────────────────────────────────────────────────────────────────────────
# AppointmentAdmin
# ──────────────────────────────────────────────────────────────────────────────


@admin.register(Appointment)
class AppointmentAdmin(ExportCsvMixin, admin.ModelAdmin):
    """
    Полнофункциональная админка:
      • обычный список + календарный вид (?view=calendar)
      • AJAX JSON эндпоинт для событий календаря
      • CSV-экшены (по приёмам и по позициям)
      • inline позиций с валидаторами/правами
      • режим мастера: видит только свои записи, read-only, без действий
    """
    form = AppointmentAdminForm
    inlines = [AppointmentItemInline]
    add_form = AppointmentAddForm
    # NOTE: если хочешь отдельный шаблон для календаря — задай его здесь
    change_list_template = "admin/appointments_calendar.html"  # твой базовый шаблон списка
    change_form_template = "admin/custom_edit_appointment.html"
    date_hierarchy = "start_time"  # поправь, если поле называется иначе

    list_select_related = ("client",)


    ordering = ("-start_time",)
    autocomplete=["promocode",]
    readonly_fields = ("final_price", "discount_source", "personal_discount_percent", "computed_total_readonly", "items_preview",)

    fieldsets = (
        (None, {
            "fields": (
                "client",
                "start_time",
                "end_time",           # если есть
                "status",             # если есть
                "payment_status",     # если есть
                "personal_discount",  # если есть
                "computed_total_readonly",
                "items_preview",
            )
        }),
    )

    # ── РЕЖИМ МАСТЕРА: права и доступ ────────────────────────────────────────

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # if is_master(request.user):
        #     # Если мастер хранится в AppointmentItem (мульти-услуги)
        #     return qs.filter(items__master=master_obj(request.user)).distinct()
            # Если мастер хранится прямо в Appointment (одиночная услуга):
        # return qs.filter(master=master_obj(request.user))
        return qs


    def get_actions(self, request):
        actions = super().get_actions(request)
        if is_master(request.user):
            # мастерам скрываем CSV-экшены и любые массовые действия
            return {}
        return actions

    # ── QS и агрегаты ────────────────────────────────────────────────────────


    def get_changeform_initial_data(self, request):
        """
        Для страницы создания (add) — дать начальные значения.
        Для редактирования (change) Django сам подставит instance-данные.
        """
        from django.utils import timezone
        data = super().get_changeform_initial_data(request)

        # пример: округлим старт к ближайшим 15 минутам вперёд
        now = timezone.now()
        minute = (now.minute // 15 + 1) * 15
        if minute == 60:
            from datetime import timedelta
            now = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
        else:
            now = now.replace(minute=minute, second=0, microsecond=0)
        data.setdefault("start_time", now)

        # если у пользователя есть привязанный мастер — подставим его в initial
        # (мастер не сможет выбрать другого, это дополнительно контролируется на фронте и в POST)
        mp = MasterProfile.objects.filter(user=UserProfile.objects.filter(user=request.user).first()).first()
        if mp:
            data.setdefault("master", mp)

        return data

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):

        ctx = dict(context)
        adminform = ctx.get("adminform")
        if adminform:
            ctx["form"] = adminform.form

        # отдаём инлайн-формсет позиций в шаблон
        # ── НАЙТИ inline formset ДЛЯ AppointmentItem НАДЁЖНО ─────────────────
        # === 1) Собираем formset для items принудительно ===
        items_fs = None
        for inline in ctx.get("inline_admin_formsets", []):

            if getattr(inline.opts, "model", None) is AppointmentItem:

                items_fs = inline.formset

                break


        if items_fs is not None:
            ctx["items_formset"] = items_fs
        # ===== данные для кастомных селектов =====
        # ограничим пул мастеров, если текущий пользователь — мастер
        mp = MasterProfile.objects.filter(user=UserProfile.objects.filter(user=request.user).first()).first()

        # мастера (id, название)
        # if is_master(request.user):
        #     masters_qs = MasterProfile.objects.select_related("user").filter(pk=mp.pk)
        # else:
        masters_qs = MasterProfile.objects.select_related("user").all()

        masters_qs = masters_qs.order_by("user__user__first_name", "user__user__last_name")
        masters = [{"id": str(m.id), "name": str(m)} for m in masters_qs]

        today = timezone.now().date()
        svc_discounts = {}
        for sd in ServiceDiscount.objects.filter(start_date__lte=today, end_date__gte=today).select_related("service"):
            svc_discounts[str(sd.service_id)] = int(sd.discount_percent)

        # карта мастер → [услуги]
        ms_map = defaultdict(list)
        for sm in ServiceMaster.objects.select_related("service", "master").order_by("service__name"):
            sid = str(sm.service_id)
            ms_map[str(sm.master_id)].append({
                "id": str(sm.service_id),
                "name": sm.service.name,
                "base_price": str(sm.service.base_price),
                "svc_disc": svc_discounts.get(sid, 0),  # %
            })

        # промокоды
        promos_by_service = defaultdict(list)
        promos_global = []
        qs = PromoCode.objects.filter(active=True, start_date__lte=today, end_date__gte=today).prefetch_related("applicable_services")
        for pc in qs:
            payload = {"id": str(pc.pk), "text": pc.code, "discount": int(pc.discount_percent)}
            services = list(pc.applicable_services.all())
            if services:
                for s in services:
                    promos_by_service[str(s.pk)].append(payload)
            else:
                promos_global.append(payload)

        ctx.update({
            "masters_data": masters,
            "ms_map_data": dict(ms_map),
            "svc_discounts_data": svc_discounts,
            "promos_by_service_data": dict(promos_by_service),
            "promos_global_data": promos_global,
            "APPT_FIELDS_1": ("client", "start_time", "payment_status", "current_status"),

            # === важные флаги для шаблонов/JS ===
            "is_master": is_master(request.user),
            "current_master_id": mp.id if mp else None,
        })
        return super().render_change_form(request, ctx, add=add, change=change, form_url=form_url, obj=obj)

    def save_model(self, request, obj, form, change):
        # Админка валидирует формы, но мы дополнительно страхуемся:
        print(f"obj:{obj}")
        obj.full_clean()  # вызывает Appointment.clean()
        super().save_model(request, obj, form, change)
        new_status = form.cleaned_data.get("current_status")
        if not new_status:
            return

        last = (AppointmentStatusHistory.objects
                .filter(appointment=obj)
                .order_by("-set_at")             # или -created_at
                .values_list("status_id", flat=True)
                .first())
        if last != new_status.id:
            AppointmentStatusHistory.objects.create(
                appointment=obj,
                status=new_status,
                set_by=self._actor(request.user),
                set_at=timezone.now(),
            )

    def _actor(self, user):
        # Подгони под свой профиль:

        p = getattr(user, "userprofile", None)
        if p is not None:
            return p
        return user

    def save_formset(self, request, form, formset, change):
        # Забираем инстансы без сохранения
        instances = formset.save(commit=False)
        print(f"formset: {formset}")
        # Удаления — отдельно
        for deleted in formset.deleted_objects:
            deleted.delete()

        # Прогоняем full_clean() на каждом дочернем объекте
        for inst in instances:
            print(f"inst: {inst}")
            inst.full_clean()  # вызывает AppointmentItem.clean()
            inst.save()

        formset.save_m2m()
    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs["form"] = self.add_form
        else:
            kwargs["form"] = self.form
        return super().get_form(request, obj, **kwargs)


    def add_view(self, request, form_url='', extra_context=None):
        return self.custom_create_view(request)

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            # только клиент при создании
            return (("Client", {"fields": ("client",)}),)
        # на редактировании — ваша стандартная форма
        return (
            (None, {"fields": ("client", "start_time", "payment_status")}),
            ("Totals", {"fields": ("final_price", "discount_source", "personal_discount_percent"),
                        "classes": ("collapse",)}),
        )

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "create/custom/",
                self.admin_site.admin_view(self.custom_create_view),
                name="core_appointment_custom_create",
            ),

        ]
        return custom + urls


    def _default_payment_status_id(self):
        obj, _ = PaymentStatus.objects.get_or_create(name="Not Paid")
        return obj.id

    def _context_lists(self):
        clients = (UserProfile.objects.select_related("user")
                   .annotate(label=Concat("user__first_name", Value(" "), "user__last_name"))
                   .values("id", "label").order_by("label"))
        masters = (MasterProfile.objects.select_related("user")
                   .annotate(label=Concat("user__user__first_name", Value(" "), "user__user__last_name"))
                   .values("id", "label").order_by("label"))
        services_by_master = {}
        qs = (ServiceMaster.objects.select_related("service", "master")
              .values("master_id", "service__id", "service__name", "service__base_price", "service__duration_min"))
        for r in qs:
            services_by_master.setdefault(str(r["master_id"]), []).append({
                "id": str(r["service__id"]),
                "name": r["service__name"],
                "base_price": str(r["service__base_price"]),
                "duration_min": r["service__duration_min"],
            })
        return list(clients), list(masters), services_by_master

    def _parse_start_dt(date_str: str | None, time_str: str | None):
        if not date_str or not time_str:
            return None
    # Популярные форматы
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                naive = datetime.strptime(f"{date_str} {time_str}", fmt)
                return timezone.make_aware(naive, timezone.get_current_timezone())
            except ValueError:
                pass
        # Fallback для ISO, если прилетит time с 'Z'
        try:
            t = time_str.replace("Z", "+00:00") if time_str.endswith("Z") else time_str
            dt = datetime.fromisoformat(f"{date_str}T{t}")
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            return dt
        except Exception:
            return None


    def custom_create_view(self, request):
        # ---------------- helpers ----------------
        def _parse_dt(date_str: str | None, time_str: str | None):
            if not date_str or not time_str:
                return None
            # популярные форматы
            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
                try:
                    naive = datetime.strptime(f"{date_str} {time_str}", fmt)
                    return make_aware(naive, get_current_timezone())
                except ValueError:
                    pass
            # ISO fallback (если time приходит c 'Z' и т.п.)
            try:
                t = time_str.replace("Z", "+00:00") if time_str.endswith("Z") else time_str
                dt = datetime.fromisoformat(f"{date_str}T{t}")
                if dt.tzinfo is None:
                    dt = make_aware(dt, get_current_timezone())
                return dt
            except Exception:
                return None

        def _empty_error_bag():
            return {
                "__all__": [],                 # глобальные ошибки
                "fields": defaultdict(list),   # ошибки по полям формы (вне айтемов)
                "items": defaultdict(lambda: defaultdict(list)),  # ошибки по строкам айтемов
            }

        def _serialize_validation_error(exc, bag):
            """
            Преобразует ValidationError (в т.ч. с message_dict) в наш bag.
            """
            if hasattr(exc, "message_dict"):
                for key, msgs in exc.message_dict.items():
                    msgs = msgs if isinstance(msgs, (list, tuple)) else [msgs]
                    if key.startswith("items-"):
                        # варианты: items-2-start_time или items-2
                        parts = key.split("-")
                        try:
                            idx = int(parts[1])
                        except Exception:
                            idx = None
                        if idx is not None:
                            if len(parts) >= 3:
                                field = "-".join(parts[2:])
                                bag["items"][idx][field].extend(msgs)
                            else:
                                bag["items"][idx]["__all__"].extend(msgs)
                        else:
                            bag["__all__"].extend(msgs)
                    elif key in ("__all__", "non_field_errors"):
                        bag["__all__"].extend(msgs)
                    else:
                        bag["fields"][key].extend(msgs)
            else:
                msgs = exc.messages if hasattr(exc, "messages") else [str(exc)]
                bag["__all__"].extend(msgs)

        def _finalize_bag(bag):
            bag["fields"] = dict(bag["fields"])
            bag["items"] = {i: dict(fields) for i, fields in bag["items"].items()}
            return bag

        def _context_lists():
            """Ваш существующий метод, оставляю как есть; если у вас уже есть — используйте его."""
            return self._context_lists()
        # ---------------- GET: первичная отрисовка ----------------
        mp = MasterProfile.objects.filter(user=UserProfile.objects.filter(user=request.user).first()).first()
        if request.method == "GET" and request.GET.get("master") != 'undefined':
            clients, masters, services_by_master = _context_lists()

            q_date   = request.GET.get("date")
            q_time   = request.GET.get("time")
            q_master = request.GET.get("master")

            if is_master(request.user):
                q_master = str(mp.pk)
                masters = [m for m in masters if str(m["id"]) == str(mp.pk)]

            initial_first_item = {}

            if q_master and MasterProfile.objects.filter(pk=q_master).exists():
                initial_first_item["master"] = str(q_master)

            dt = _parse_dt(q_date, q_time)
            if dt:
                initial_first_item["start_time_date"] = dt.strftime("%Y-%m-%d")
                initial_first_item["start_time_time"] = dt.strftime("%H:%M:%S" if dt.second else "%H:%M")

            ctx = {
                **self.admin_site.each_context(request),
                "clients": clients,
                "masters": masters,
                "services_by_master": services_by_master,
                "initial_first_item": initial_first_item,
                "prefill_query": {"date": q_date, "time": q_time, "master": str(q_master) if q_master else None},

                "is_master": is_master(request.user),
                "current_master_id": mp.id if mp else None,
            }
            return TemplateResponse(request, "admin/custom_create_appointment.html", ctx)


        # ---------------- POST: создаём запись ----------------
        clients, masters, services_by_master = _context_lists()

        if is_master(request.user):
            masters = [m for m in masters if str(m["id"]) == str(mp.pk)]
        # соберём промокоды по сервисам (как у вас)
        promos_by_service: dict[str, list[dict]] = {}
        try:
            fk_qs = PromoCode.objects.filter(~Q(service=None)).select_related("service")
        except Exception:
            fk_qs = PromoCode.objects.none()

        for pc in fk_qs:
            sid = str(pc.service_id)
            promos_by_service.setdefault(sid, []).append({
                "id": str(pc.pk),
                "text": getattr(pc, "code", str(pc.pk)),
                "discount": getattr(pc, "discount_percent", None),
            })

        try:
            m2m_qs = PromoCode.objects.prefetch_related("applicable_services")
        except Exception:
            m2m_qs = PromoCode.objects.none()

        for pc in m2m_qs:
            services = getattr(pc, "applicable_services", None)
            if not services:
                continue
            for svc in services.all():
                sid = str(svc.pk)
                promos_by_service.setdefault(sid, []).append({
                    "id": str(pc.pk),
                    "text": getattr(pc, "code", str(pc.pk)),
                    "discount": getattr(pc, "discount_percent", None),
                })

        # dedup + sort
        for sid, items in promos_by_service.items():
            seen, uniq = set(), []
            for it in items:
                if it["id"] in seen:
                    continue
                seen.add(it["id"])
                uniq.append(it)
            promos_by_service[sid] = sorted(uniq, key=lambda x: (x["text"] or "").lower())

        # state + первичная валидация
        bag = _empty_error_bag()
        client_id = (request.POST.get("client") or "").strip()
        try:
            total_forms = int(request.POST.get("items-TOTAL_FORMS", 0))
        except Exception:
            total_forms = 0

        posted_items = []  # чтобы вернуть в шаблон ровно то, что вводили
        for i in range(total_forms):
            pref = f"items-{i}-"
            posted_items.append({
                "master":      (request.POST.get(pref + "master") or "").strip(),
                "service":     (request.POST.get(pref + "service") or "").strip(),
                "start_time_0": (request.POST.get(pref + "start_time_0") or "").strip(),  # date
                "start_time_1": (request.POST.get(pref + "start_time_1") or "").strip(),  # time
                "unit_price":  (request.POST.get(pref + "unit_price") or "").strip(),
                "promocode":   (request.POST.get(pref + "promocode") or "").strip(),
            })

        # обязательные поля верхнего уровня
        if not client_id:
            bag["fields"]["client"].append("Client is required.")
        if total_forms < 1:
            bag["__all__"].append("Add at least one service.")

        # построчная валидация ещё до создания объектов
        valid_rows = []
        for idx, row in enumerate(posted_items):
            # пропускаем пустые
            if not any(row.values()):
                continue

            master_id  = row["master"]
            service_id = row["service"]
            date_str   = row["start_time_0"]
            time_str   = row["start_time_1"]

            if is_master(request.user):
                if master_id and str(master_id) != str(mp.pk):
                    # фиксируем в UI, но и ошибку подсветим, чтобы было наглядно, почему перезатираем
                    bag["items"][idx]["master"].append("You can assign items only to yourself.")
                master_id = str(mp.pk)

            if not master_id:
                bag["items"][idx]["master"].append("Select master.")
            if not service_id:
                bag["items"][idx]["service"].append("Select service.")
            if not date_str:
                bag["items"][idx]["start_time_0"].append("Select date.")
            if not time_str:
                bag["items"][idx]["start_time_1"].append("Select time.")

            dt = _parse_dt(date_str, time_str)
            if date_str and time_str and not dt:
                bag["items"][idx]["start_time_1"].append("Invalid date/time.")

            valid_rows.append({
                "idx": idx,
                "master_id": master_id or None,
                "service_id": service_id or None,
                "dt": dt,
                "unit_price": (row["unit_price"] or None),
                "promocode_id": (row["promocode"] or None),
            })

        # если уже есть ошибки — просто показать страницу с ними
        has_errors = bool(bag["__all__"] or bag["fields"] or bag["items"])
        if has_errors:
            ctx = {
                **self.admin_site.each_context(request),
                "clients": clients,
                "masters": masters,
                "services_by_master": services_by_master,
                "promos_by_service_json": json.dumps(promos_by_service),
                "form_errors": bag["__all__"],
                "field_errors": dict(bag["fields"]),
                "item_errors": {i: dict(v) for i, v in bag["items"].items()},
                "posted_items": posted_items,
                "posted_client": client_id,


                "is_master": is_master(request.user),
                "current_master_id": mp.id if mp else None,
            }
            return TemplateResponse(request, "admin/custom_create_appointment.html", ctx)

        # всё валидно — создаём
        try:
            with transaction.atomic():
                appt = Appointment(
                    client_id=client_id,
                    payment_status_id=self._default_payment_status_id(),
                )
                appt.full_clean()
                appt.save()


                row_errs = {}  # message_dict для последующего ValidationError
                prebuilt_items = []  # сюда сложим валидные, чтобы потом сохранить



                for row in valid_rows:
                    idx = row["idx"]
                    if not (row["master_id"] and row["service_id"] and row["dt"]):
                        # (сюда попадём только если кто-то внезапно пустой — но мы отфильтровали выше)
                        key = f"items-{idx}"
                        row_errs.setdefault(key, []).append("Incomplete row.")
                        continue

                    if is_master(request.user) and str(row["master_id"]) != str(mp.pk):
                        key = f"items-{idx}-master"
                        row_errs.setdefault(key, []).append("You can assign items only to yourself.")
                        continue
                    item = AppointmentItem(
                        appointment=appt,
                        master_id=row["master_id"],
                        service_id=row["service_id"],
                        start_time=row["dt"],
                        unit_price=row["unit_price"] or None,
                    )
                    try:
                        item.full_clean()
                        prebuilt_items.append((idx, item, row.get("promocode_id") or ""))
                        item.save()
                    except ValidationError as e:
                        if hasattr(e, "message_dict"):
                            for field, msgs in e.message_dict.items():
                                msgs = msgs if isinstance(msgs, (list, tuple)) else [msgs]
                                if field in ("__all__", "non_field_errors"):
                                    key = f"items-{idx}"
                                    row_errs.setdefault(key, []).extend(msgs)
                                else:
                                    key = f"items-{idx}-{field}"
                                    row_errs.setdefault(key, []).extend(msgs)
                        else:
                            msgs = e.messages if hasattr(e, "messages") else [str(e)]
                            key = f"items-{idx}"
                            row_errs.setdefault(key, []).extend(msgs)

                    # Если хотя бы у одной строки есть ошибки — откатываем и показываем их в форме
                if row_errs:
                    raise ValidationError(row_errs)
                first_start = None
                for idx, item, promocode_id in prebuilt_items:
                    item.save()
                    if first_start is None or item.start_time < first_start:
                        first_start = item.start_time

                    promo_id = (promocode_id or "").strip()
                    if promo_id:
                        promo_obj = PromoCode.objects.filter(pk=promo_id).first()
                        if promo_obj:
                            AppointmentItemPromoCode.objects.update_or_create(
                                item=item, defaults={"promocode": promo_obj}
                            )
                    else:
                        AppointmentItemPromoCode.objects.filter(item=item).delete()

                if first_start:
                    appt.start_time = first_start

                if hasattr(appt, "recompute_totals"):
                    appt.recompute_totals(save=True)
                else:
                    appt.save(update_fields=["start_time"])

                status = AppointmentStatus.objects.filter(name="Booked").first()
                if status:
                    # аккуратно получаем профиль, если он есть
                    set_by = getattr(getattr(request.user, "userprofile", None), "pk", None)
                    AppointmentStatusHistory.objects.create(
                        appointment=appt,
                        status=status,
                        set_by=request.user.userprofile if set_by else None,
                    )

            messages.success(request, "Appointment created.")
            return redirect("admin:core_appointment_change", appt.pk)

        except ValidationError as ve:
            # Переносим ошибки из моделей в наш мешок и показываем в той же форме
            _serialize_validation_error(ve, bag)
            bag = _finalize_bag(bag)
            ctx = {
                **self.admin_site.each_context(request),
                "clients": clients,
                "masters": masters,
                "services_by_master": services_by_master,
                "promos_by_service_json": json.dumps(promos_by_service),
                "form_errors": bag["__all__"],
                "field_errors": bag["fields"],
                "item_errors": bag["items"],
                "posted_items": posted_items,
                "posted_client": client_id,
                "is_master": is_master(request.user),
                "current_master_id": mp.id if mp else None,
            }
            return TemplateResponse(request, "admin/custom_create_appointment.html", ctx)

        except IntegrityError as ie:
            # Ошибка БД — показываем как глобальную и не падаем 500
            bag["__all__"].append(f"Database error: {ie}")
            ctx = {
                **self.admin_site.each_context(request),
                "clients": clients,
                "masters": masters,
                "services_by_master": services_by_master,
                "promos_by_service_json": json.dumps(promos_by_service),
                "form_errors": bag["__all__"],
                "field_errors": dict(bag["fields"]),
                "item_errors": {i: dict(v) for i, v in bag["items"].items()},
                "posted_items": posted_items,
                "posted_client": client_id,
                "is_master": is_master(request.user),
                "current_master_id": mp.id if mp else None,
            }
            return TemplateResponse(request, "admin/custom_create_appointment.html", ctx)

        except Exception:
            # На проде — лог, а пользователю безопасно
            bag["__all__"].append("Unexpected error while creating appointment.")
            ctx = {
                **self.admin_site.each_context(request),
                "clients": clients,
                "masters": masters,
                "services_by_master": services_by_master,
                "promos_by_service_json": json.dumps(promos_by_service),
                "form_errors": bag["__all__"],
                "field_errors": dict(bag["fields"]),
                "item_errors": {i: dict(v) for i, v in bag["items"].items()},
                "posted_items": posted_items,
                "posted_client": client_id,
                "is_master": is_master(request.user),
                "current_master_id": mp.id if mp else None,
            }
            return TemplateResponse(request, "admin/custom_create_appointment.html", ctx)

    @admin.display(description=_("Позиций"), ordering="_items_count")
    def items_count_display(self, obj):
        return getattr(obj, "_items_count", 0)

    @admin.display(description=_("Итого, $"), ordering="_total")
    def total_price_display(self, obj):
        return getattr(obj, "_total", Decimal("0"))

    @admin.display(description=_("Статус"))
    def status_display(self, obj):
        return getattr(obj, "status", None) or "—"

    @admin.display(description=_("Оплата"))
    def payment_status_display(self, obj):
        return getattr(obj, "payment_status", None) or "—"

    @admin.display(description=_("Состав"))
    def items_preview(self, obj):
        items_mgr = getattr(obj, "appointmentitem_set", None) or getattr(obj, "items", None)
        if not items_mgr:
            return "—"
        parts = []
        for it in items_mgr.all()[:6]:
            s_name = getattr(it.service, "name", str(it.service))
            m_name = getattr(it.master, "short_name", None) or getattr(it.master, "user", None) or "—"
            start = getattr(it, "start_time", None)
            fp = getattr(it, "final_price", None)
            frag = f"{s_name} | {m_name}"
            if start:
                frag += f" @ {start:%Y-%m-%d %H:%M}"
            if fp is not None:
                frag += f" — ${fp}"
            parts.append(frag)
        if items_mgr.count() > 6:
            parts.append("…")
        return " | ".join(parts)

    @admin.display(description=_("Итого (расчёт)"), ordering="_total")
    def computed_total_readonly(self, obj):
        return self.total_price_display(obj)

    # ── Сохранение и жёсткие проверки ────────────────────────────────────────

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        appt = form.instance
        mp = MasterProfile.objects.filter(user=UserProfile.objects.filter(user=request.user).first()).first()
        if is_master(request.user):
            for formset in formsets:
                if not isinstance(formset, BaseInlineFormSet):
                    continue
                model = getattr(getattr(formset, "model", None), "__name__", "")
                # интересует только инлайн с AppointmentItem
                if model != "AppointmentItem":
                    continue

        appt.recompute_totals(save=True)
        # Бизнес-правила (как и раньше — строгость сохранили):
        validate_appointment_has_items_on_save(appt)
        validate_items_prices_nonnegative(appt)
        # Если у тебя запрещены дубли услуг в одном приёме — оставь проверку:
        # (иначе — закомментируй следующую строку)
        # validate_no_duplicate_services_in_items(appt)
        validate_no_time_overlap_for_same_master(appt)


    # ── CSV действия (через твой миксин) ─────────────────────────────────────

    actions = ["export_appointments_csv", "export_appointment_items_csv"]

    def _csv_export(self, request, filename, headers, rows):
        """
        Универсальный адаптер под разные реализации твоего миксина.
        1) export_as_csv(request, filename, headers, rows)
        2) stream_csv(filename, headers, rows)
        3) fallback — HttpResponse (если миксин ничего не определяет)
        """
        if hasattr(self, "export_as_csv") and callable(getattr(self, "export_as_csv")):
            return self.export_as_csv(request, filename, headers, rows)
        if hasattr(self, "stream_csv") and callable(getattr(self, "stream_csv")):
            return self.stream_csv(filename, headers, rows)

        import csv
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        writer = csv.writer(resp)
        writer.writerow(headers)
        for r in rows:
            writer.writerow(r)
        return resp

    def _qs_for_export(self, request, queryset=None):
        qs = (queryset or self.get_queryset(request)).select_related(
            "client",
        ).prefetch_related(
            "appointmentitem_set__service",
            "appointmentitem_set__master",
            "appointmentitem_set__promocode",
            "appointmentitem_set__service_discount",
        )
        return qs

    def export_appointments_csv(self, request, queryset):
        qs = self._qs_for_export(request, queryset)
        headers = [
            "Appointment ID",
            "Start",
            "Client",
            "Status",
            "Payment Status",
            "Personal Discount",
            "Items Count",
            "Total (sum of items)",
            "Items (preview)",
        ]
        rows = []
        for appt in qs:
            items = getattr(appt, "appointmentitem_set").all()
            total = sum([(it.final_price or 0) for it in items])
            preview = " | ".join(
                f"{getattr(it.service, 'name', it.service)} ×{getattr(it, 'quantity', 1)}"
                for it in items[:6]
            )
            if items.count() > 6:
                preview += " …"
            rows.append([
                str(appt.pk),
                getattr(appt, "start_time", None),
                getattr(appt.client, "full_name", getattr(getattr(appt.client, "user", None), "username", "")),
                getattr(appt, "status", ""),
                getattr(appt, "payment_status", ""),
                getattr(appt, "personal_discount", ""),
                items.count(),
                _money(total),
                preview,
            ])
        return self._csv_export(request, "appointments.csv", headers, rows)
    export_appointments_csv.short_description = "Export Appointments (1 row per appointment)"

    def export_appointment_items_csv(self, request, queryset):
        qs = self._qs_for_export(request, queryset)
        headers = [
            "Appointment ID",
            "Item ID",
            "Item Start",
            "Service",
            "Master",
            "Quantity",
            "Unit Price",
            "Service Discount",
            "Promocode",
            "Final Price",
            "Client",
            "Appointment Status",
            "Payment Status",
            "Personal Discount (Appointment)",
        ]
        rows = []
        for appt in qs:
            items = getattr(appt, "appointmentitem_set").all()
            for it in items:
                rows.append([
                    str(appt.pk),
                    str(getattr(it, "pk", "")),
                    getattr(it, "start_time", None),
                    getattr(it.service, "name", str(it.service)),
                    getattr(it.master, "short_name", getattr(getattr(it.master, "user", None), "username", "")),
                    getattr(it, "quantity", 1),
                    _money(getattr(it, "unit_price", None)),
                    getattr(getattr(it, "service_discount", None), "name", getattr(it, "service_discount", "")),
                    getattr(getattr(it, "promocode", None), "code", getattr(it, "promocode", "")),
                    _money(getattr(it, "final_price", None)),
                    getattr(appt.client, "full_name", getattr(getattr(appt.client, "user", None), "username", "")),
                    getattr(appt, "status", ""),
                    getattr(appt, "payment_status", ""),
                    getattr(appt, "personal_discount", ""),
                ])
        return self._csv_export(request, "appointment_items.csv", headers, rows)
    export_appointment_items_csv.short_description = "Export Appointment Items (1 row per item)"

    # ── AJAX КАЛЕНДАРЬ (список → календарь + JSON) ──────────────────────────


    def changelist_view(self, request, extra_context=None):

        selected_date = request.GET.get('date')

        if selected_date:
            selected_date = datetime.strptime(selected_date, '%Y-%m-%d').date()

        else:
            selected_date = timezone.localdate()

        services = Service.objects.all()
        appointment_statuses = AppointmentStatus.objects.all()
        payment_statuses = PaymentStatus.objects.all()

        appointments = AppointmentItem.objects.select_related('appointment__client', 'service', 'master').prefetch_related('appointment__items__service')


        masters = MasterProfile.objects.filter(
            id__in=appointments.values_list('master_id', flat=True)
        ).distinct()
        start_of_day = make_aware(datetime.combine(selected_date, datetime.min.time()))
        end_of_day = make_aware(datetime.combine(selected_date, datetime.max.time()))

        availabilities = MasterAvailability.objects.filter(
            start_time__lte=end_of_day,
            end_time__gte=start_of_day
        )
        if request.GET.get("service"):
            appointments = appointments.filter(service_id=request.GET["service"])
        if request.GET.get("status"):
            appointments = appointments.filter(appointment__appointmentstatushistory__status_id=request.GET["status"])
        if request.GET.get("payment_status"):
            appointments = appointments.filter(appointment__payment_status_id__in=request.GET.getlist("payment_status"))

        # Слоты по 15 минут
        start_hour = 8
        end_hour = 21
        slot_times = []
        time_pointer = datetime(2000, 1, 1, start_hour, 0)
        end_time = datetime(2000, 1, 1, end_hour, 0)


        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            action = request.GET.get("action")

            calendar_table = createTable(selected_date, time_pointer, end_time, slot_times, appointments, masters, availabilities)

            if action == "filter":  # Фильтрация по форме

                html = render_to_string('admin/appointments_calendar_partial.html', {
                    "calendar_table": calendar_table,
                    'masters': masters,
                })
                return JsonResponse({"html": html})

            elif action == "calendar":  # Подгрузка календаря (твоя текущая логика)

                html = render_to_string('admin/appointments_calendar_partial.html', {
                    'calendar_table': calendar_table,
                    'masters': masters,
                }, request=request)

                return JsonResponse({'html': html})

        calendar_table = createTable(selected_date, time_pointer, end_time, slot_times, appointments, masters, availabilities)

        response = super().changelist_view(request, extra_context=extra_context)

        if hasattr(response, "context_data"):
            context = response.context_data
            context.update({

                "calendar_table": calendar_table,
                "masters": masters,
                "selected_date": selected_date,
                "prev_date": (selected_date - timedelta(days=1)).strftime("%Y-%m-%d"),
                "next_date": (selected_date + timedelta(days=1)).strftime("%Y-%m-%d"),
                "today": timezone.localdate().strftime("%Y-%m-%d"),
                "services": services,
                "appointment_statuses": appointment_statuses,
                "payment_statuses": payment_statuses,
            })

        return response


# -----------------------------
# Appointment Status History Admin
# -----------------------------
@admin.register(AppointmentStatusHistory)
class AppointmentStatusHistoryAdmin(ExportCsvMixin,admin.ModelAdmin):
    """
    Admin interface for tracking status changes of appointments.
    """
    exclude = ('set_by',)
    list_display = ('appointment', 'status', 'set_by', 'set_at')
    list_filter = ('appointment','set_by')
    export_fields = ['appointment', 'status', 'set_by', 'set_at']
    def has_delete_permission(self, request, obj=None):
        # Суперадмин может всегда
        if request.user.is_superuser:
            return True
        # Мастер может удалять
        if hasattr(request.user, "master_profile"):
            return True
        return False
    def save_model(self, request, obj, form, change):
        if not obj.set_by_id:
            profile = getattr(request.user, "userprofile", None)
            if profile is None:
                profile, _ = UserProfile.objects.get_or_create(user=request.user)
            obj.set_by = profile
        super().save_model(request, obj, form, change)


# -----------------------------
# Payment Admin
# -----------------------------
@admin.register(Payment)
class PaymentAdmin(ExportCsvMixin ,admin.ModelAdmin):
    """
    Admin interface for payments.
    """
    list_display = (
        'appointment',
        'amount',
        'currency',
        'status',
        'amount_received',
        'method',
        'livemode',
        'created_at',
    )
    list_filter = ('method', 'status', 'livemode')
    search_fields = (
        'appointment__client__user__first_name', 'appointment__client__user__last_name',
        'appointment__client__user__email',
        'appointment__master__user__first_name', 'appointment__master__user__last_name',
        'appointment__service__name',
        'stripe_payment_intent_id', 'stripe_charge_id',
    )
    readonly_fields = (
        'created_at', 'updated_at', 'stripe_payment_intent_id', 'stripe_charge_id',
        'stripe_payment_method_id', 'receipt_url', 'raw_response', 'metadata',
        'amount_received', 'amount_refunded', 'captured_at', 'livemode',
    )
    export_fields = [
        'appointment', 'amount', 'currency', 'status', 'amount_received',
        'amount_refunded', 'method', 'livemode', 'stripe_payment_intent_id',
        'stripe_charge_id', 'created_at',
    ]


# -----------------------------
# Appointment Prepayment Admin
# -----------------------------
@admin.register(AppointmentPrepayment)
class AppointmentPrepaymentAdmin(ExportCsvMixin,admin.ModelAdmin):
    """
    Admin interface for prepayment options tied to appointments.
    """
    list_display = ('appointment', 'option')
    export_fields = ['appointment', 'option']

# -----------------------------
# Hidden Proxy Admin for CustomUserDisplay
# -----------------------------
@admin.register(CustomUserDisplay)
class CustomUserDisplayAdmin(admin.ModelAdmin):
    def _redirect_to_appointments(self, request):
        url = reverse("admin:core_appointment_changelist")
        # переносим дату (и любые будущие параметры из календаря)
        passthrough = {}
        for key in ("date",):
            val = request.GET.get(key) or request.POST.get(key)
            if val:
                passthrough[key] = val
        if passthrough:
            url = f"{url}?{urlencode(passthrough)}"
        return redirect(url)

    # ---- после добавления ----
    def response_add(self, request, obj, post_url_continue=None):
        # всегда назад в календарь записей
        return self._redirect_to_appointments(request)

    # ---- после изменения ----
    def response_change(self, request, obj):
        # даже если нажали "Сохранить и продолжить" — уводим в календарь
        return self._redirect_to_appointments(request)

    # ---- после удаления ----
    def response_delete(self, request, obj_display, obj_id):
        return self._redirect_to_appointments(request)


# -----------------------------
# Service Master Admin
# -----------------------------
@admin.register(ServiceMaster)
class ServiceMasterAdmin(ExportCsvMixin, admin.ModelAdmin):
    """
    Admin interface to assign masters to services.
    """
    list_display = ('master', 'service')
    search_fields = ('master__user__first_name', 'master__user__last_name', 'service__name')
    export_fields = ['master', 'service']

# -----------------------------
# Service Admin
# -----------------------------
@admin.register(Service)
class ServiceAdmin(ExportCsvMixin, admin.ModelAdmin):
    """
    Admin interface for services.
    """
    list_display = ('name', 'base_price', 'category', 'duration_min')
    search_fields = ('name',)
    list_filter = ('category',)
    export_fields = ['name', 'description','base_price', 'category','prepayment_option', 'duration_min', 'extra_time_min']
# -----------------------------
# Notification Admin
# -----------------------------
@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """
    Admin interface for notifications (email/SMS).
    """
    list_display = ('user', 'appointment', 'channel', 'short_message')
    list_filter = (('sent_at', DateFieldListFilter), 'channel')
    search_fields = ('user__user__first_name', 'user__user__last_name', 'appointment__service__name')
    ordering = ['-sent_at']

    @admin.display(description="message")
    def short_message(self, obj):
        """
        Truncates long messages to first 10 words.
        """
        words = obj.message.split()
        return ' '.join(words[:10]) + ('...' if len(words) > 10 else '')


@admin.register(ReminderSchedule)
class ReminderScheduleAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "offset_amount", "offset_unit", "email_template", "email_subject", "slug")
    list_filter  = ("is_active", "offset_unit")
    search_fields = ("name", "slug", "email_subject", "email_template")
    fields = (
        "name", "slug", "is_active",
        "offset_amount", "offset_unit",
        "email_subject", "email_template",
    )

# -----------------------------
# Client File Admin
# -----------------------------
@admin.register(ClientFile)
class ClientFileAdmin(admin.ModelAdmin):
    """
    Admin interface for managing user-uploaded files.
    """
    list_display = ('user', "uploaded_by" ,'file_type', 'file')
    fields = ('user', 'file',"uploaded_by", 'file_type')
    readonly_fields = ('file_type',)  # 👈 делаем только для чтения
    exclude = ('file_type',)  # 👈 скрываем из формы создания
    list_filter = (('uploaded_at', DateFieldListFilter), 'file_type')
    search_fields = ('user__user__first_name', 'user__user__last_name')
    ordering = ['-uploaded_at']



# -----------------------------
# Client Review Admin
# -----------------------------
@admin.register(ClientReview)
class ClientReviewAdmin(ExportCsvMixin ,admin.ModelAdmin):
    list_display = ("appointment", "get_client", "get_master", "rating", "created_at")
    search_fields = ("appointment__client__user__first_name", "appointment__client__user__last_name", "comment")
    list_filter = ("rating", "created_at")
    export_fields = ["appointment", "get_client", "get_master", "rating", "created_at"]
    @admin.display(description="Client")
    def get_client(self, obj):
        return obj.appointment.client.get_full_name()

    @admin.display(description="Master")
    def get_master(self, obj):
        return obj.appointment.master.user.get_full_name()


#-----------------------------
# Discounts Admin
#-----------------------------
@admin.register(ServiceDiscount)
class ServiceDiscountAdmin(ExportCsvMixin ,admin.ModelAdmin):
    list_display = ('service', 'discount_percent', 'start_date', 'end_date', 'is_active')
    list_filter = ('start_date', 'end_date', 'service')
    search_fields = ('service__name',)
    export_fields = ['service', 'discount_percent', 'start_date', 'end_date', 'is_active']
    @admin.display(boolean=True)
    def is_active(self, obj):
        return obj.is_active()

#-----------------------------
# Promocode Admin
#-----------------------------
@admin.register(PromoCode)
class PromoCodeAdmin(ExportCsvMixin ,admin.ModelAdmin):
    list_display = ('code', 'discount_percent', 'start_date', 'end_date',)
    list_filter = ('start_date', 'end_date')

    export_fields = ['code', 'applicable_services', 'discount_percent', 'start_date', 'end_date']

    @admin.display(boolean=True)
    def is_active(self, obj):
        return obj.is_active()


# -----------------------------
# Register remaining models directly
# -----------------------------
admin.site.register(Role)
admin.site.register(UserRole)
admin.site.register(AppointmentStatus)
admin.site.register(PaymentMethod)
admin.site.register(ClientSource)
admin.site.register(MasterRoom)
admin.site.register(ServiceCategory)
admin.site.register(PrepaymentOption)
admin.site.register(PaymentStatus)
admin.site.register(CancellationReason)

@admin.register(AppointmentItemPromoCode)
class AppointmentItemPromoCodeAdmin(admin.ModelAdmin):
    list_display = ["item", "promocode", "promocode__discount_percent", "promocode__start_date", "promocode__end_date"]



@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    form = UserProfileChangeForm
    # Явно перечислим поля на форме
    @admin.display(description="First name")
    def user_first_name(self, obj):
        return getattr(getattr(obj, "user", None), "first_name", "")

    @admin.display(description="Last name")
    def user_last_name(self, obj):
        return getattr(getattr(obj, "user", None), "last_name", "")

    @admin.display(description="Email")
    def user_email(self, obj):
        return getattr(getattr(obj, "user", None), "email", "")

    fieldsets = (
        (None, {
            "fields": (
                "user_first_name",
                "user_last_name"
            )
        }),
        ("Personal Info", {
            "fields": (
                "phone", "user_email","birth_date", "postal_code",
                "how_heard",
            )
        }),
        ("Notes", {"fields": ("notes",)}),

        # ТЕ САМЫЕ ПОЛЯ — но они теперь ПРИСУТСТВУЮТ в форме (как виртуальные),
        # поэтому Django их корректно отрендерит в админке UserProfile.
        ("Health", {
            "classes": ("collapse", "wide"),
            "fields": (
                "has_allergies", "allergies_text", "gender",
                "chronic_conditions", "medications",
                "pregnant", "skin_sensitivity",
                "recent_procedures", "contraindications",
                "health_notes",
            ),
        }),

    )

    readonly_fields = ("user_first_name", "user_last_name", "user_email")


    @admin.display(description="Status")
    def client_status_col(self, obj):
        return obj.client_status

    def response_change(self, request, obj):
        if "_from_appointment" in request.GET:
            return redirect("admin:core_appointment_changelist")
        return super().response_change(request, obj)

    def response_delete(self, request, obj_display, obj_id):
        if "_from_appointment" in request.GET:
            return redirect("admin:core_appointment_changelist")
        return super().response_delete(request, obj_display, obj_id)

    def response_post_save_change(self, request, obj):
        if "_from_appointment" in request.GET:
            return redirect("admin:core_appointment_changelist")
        return super().response_post_save_change(request, obj)

    def get_readonly_fields(self, request, obj=None):
        # Для мастера — все поля read-only, кроме 'notes'
        if hasattr(request.user, "master_profile") and not request.user.is_superuser:
            # Берём список всех полей формы и исключаем 'notes'
            all_fields = list(self.fields) if self.fields else [f.name for f in self.model._meta.fields]
            return [f for f in all_fields if f != "notes"]
        return super().get_readonly_fields(request, obj)


    # Мастер может открывать и менять (только notes)
    def has_change_permission(self, request, obj=None):
        if hasattr(request.user, "master_profile") and not request.user.is_superuser:
            return True
        return super().has_change_permission(request, obj)

    # Мастеру — нельзя создавать профили
    def has_add_permission(self, request):
        if hasattr(request.user, "master_profile") and not request.user.is_superuser:
            return False
        return super().has_add_permission(request)

    # Мастеру — нельзя удалять профили
    def has_delete_permission(self, request, obj=None):
        if hasattr(request.user, "master_profile") and not request.user.is_superuser:
            return False
        return super().has_delete_permission(request, obj)

class MasterWorkDayInline(admin.TabularInline):
    model = MasterWorkDay
    extra = 7  # сразу 7 строк для всех дней

@admin.register(MasterProfile)
class MasterProfileAdmin(ExportCsvMixin,admin.ModelAdmin):
    inlines = [MasterWorkDayInline]
    add_form = MasterCreateFullForm
    readonly_fields = ['password_display']
    export_fields = ["first_name","last_name","email","username" ,"phone","birth_date","postal_code", "profession", 'bio', "room", "is_staff", "is_superuser", 'is_active']
    search_fields = ("user__user__username", "user__user__first_name", "user__user__last_name")
    def get_export_row(self, obj):
        phone = obj.user.userprofile.phone if hasattr(obj, 'user') else ''
        birth_date = obj.user.userprofile.birth_date if hasattr(obj, 'user') else ''
        postal_code = obj.user.userprofile.postal_code if hasattr(obj, 'user') else ''


        return [
            obj.user.first_name,
            obj.user.last_name,
            obj.user.email,
            obj.user.username,
            phone,
            birth_date,
            postal_code,
            obj.profession,
            obj.bio,
            obj.work_start,
            obj.work_end,
            obj.room,
            obj.user.is_staff,
            obj.user.is_superuser,
            obj.user.is_active,
        ]
    form = MasterCreateFullForm  # на редактирование тоже можно оставить ту же


    list_display = ("get_name", "room", "profession")

    def get_fieldsets(self, request, obj=None):
        form = self.form(instance=obj if obj else None)
        fields = list(form.fields.keys())

        if obj:
            # редактирование
            fields = [f for f in fields if f not in ['password1', 'password2', 'password']]  # ← обязательно убрать 'password'
            if 'email' in fields and 'password_display' not in fields:
                fields.insert(fields.index('email') + 1, 'password_display')
            elif 'password_display' not in fields:
                fields.append('password_display')
        else:
            # создание
            fields = [f for f in fields if f != 'password_display']

        return [(None, {'fields': fields})]

    def password_display(self, obj):
        from django.utils.html import format_html
        reset_url = f"/admin/auth/user/{obj.user.id}/password/"
        return format_html(
            '<div style="word-break: break-all;">'
            '<strong>algorithm:</strong> pbkdf2_sha256<br>'
            '<strong>hash:</strong> {}<br><br>'
            '<a href="{}" class="button" style="color: #fff; background: #007bff; padding: 4px 8px; text-decoration: none; border-radius: 4px;">Reset password</a>'
            '</div>',
            obj.user.password,
            reset_url
        )
    password_display.short_description = "Password"

    def has_change_permission(self, request, obj=None):
        if hasattr(request.user, "master_profile") and not request.user.is_superuser:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if hasattr(request.user, "master_profile") and not request.user.is_superuser:
            return False
        return super().has_delete_permission(request, obj)

    def get_name(self, obj):
        return obj.user.get_full_name() or obj.user.username

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        # 1. Забираем все текущие разрешения
        user = obj.user.user
        user.user_permissions.clear()

        # 2. Добавляем только view_appointment
        needed = [
            # Appointment
            "view_appointment", "add_appointment", "change_appointment", "delete_appointment",
            # MasterAvailability (time off)
            "view_masteravailability", "add_masteravailability", "change_masteravailability", "delete_masteravailability",

             "view_userprofile", "change_userprofile", "add_appointmentitem", "change_appointmentitem", "delete_appointmentitem"
        ]
        perms = Permission.objects.filter(codename__in=needed)
        user.user_permissions.add(*perms)

        ct_proxy = ContentType.objects.get_for_model(CustomUserDisplay)
        try:
            p_view_proxy = Permission.objects.get(content_type=ct_proxy, codename="view_customuserdisplay")
            user.user_permissions.add(p_view_proxy)
        except Permission.DoesNotExist:
            pass  # миграции ещё не применены — не падаем

        # (не обязательно, но можно) право на просмотр профилей клиентов
        ct_profile = ContentType.objects.get_for_model(UserProfile)
        try:
            p_view_profile = Permission.objects.get(content_type=ct_profile, codename="view_userprofile")
            user.user_permissions.add(p_view_profile)
        except Permission.DoesNotExist:
            pass

        user.save()


TZ = get_current_timezone()


# ──────────────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────────────

def _parse_period(request: HttpRequest) -> tuple[date, date]:
    """?start=YYYY-MM-DD&end=YYYY-MM-DD, по умолчанию последние 30 дней (включительно)."""
    today = date.today()
    start_s = request.GET.get("start") or ""
    end_s = request.GET.get("end") or ""
    try:
        start = date.fromisoformat(start_s) if start_s else today - timedelta(days=30)
    except Exception:
        start = today - timedelta(days=30)
    try:
        end = date.fromisoformat(end_s) if end_s else today
    except Exception:
        end = today
    if end < start:
        start, end = end, start
    return start, end


def _cancel_no_show_names() -> list[str]:
    """Фактические названия статусов в БД (fallback на строковые)."""
    cancelled = (AppointmentStatus.objects
                 .filter(name__iexact="Cancelled")
                 .values_list("name", flat=True).first()) or "Cancelled"
    no_show = (AppointmentStatus.objects
               .filter(name__iexact="No_Show")
               .values_list("name", flat=True).first()) or "No_Show"
    return [cancelled, no_show]

def _client_source_aggregation(qs):
    # пробуем client__source, если его нет — client__how_heard
    try:
        rows = (
            qs.values("client__source")
            .annotate(
                revenue=Coalesce(Sum("final_price"), Value(Decimal("0"))),
                appts=Count("id"),
                clients=Count("client_id", distinct=True),
            )
            .order_by("-revenue")
        )
        # нормализуем ключ + подпись
        return [{"label": (r["client__source"] or "unknown"), **{k: r[k] for k in ("revenue","appts","clients")}} for r in rows]
    except FieldError:
        rows = (
            qs.values("client__how_heard")
            .annotate(
                revenue=Coalesce(Sum("final_price"), Value(Decimal("0"))),
                appts=Count("id"),
                clients=Count("client_id", distinct=True),
            )
            .order_by("-revenue")
        )
        return [{"label": (r["client__how_heard"] or "unknown"), **{k: r[k] for k in ("revenue","appts","clients")}} for r in rows]

# ──────────────────────────────────────────────────────────────────────────────
# view
# ──────────────────────────────────────────────────────────────────────────────

@staff_member_required
@staff_member_required
def stats_view(request: HttpRequest) -> HttpResponse:
    # ── Период
    start, end = _parse_period(request)  # helper уже есть в файле

    # ── Отбрасываем отменённые/похожие статусы
    last_status_name = (
        AppointmentStatusHistory.objects
        .filter(appointment_id=OuterRef("pk"))
        .order_by("-set_at")
        .values("status__name")[:1]
    )
    cancelled_like = _cancel_no_show_names()  # helper уже есть

    # Валидные аппы по дате начала визита (для счётчиков штук)
    base_appt_q = (
        Appointment.objects
        .select_related("client__user")
        .annotate(last_status=Subquery(last_status_name))
        .exclude(last_status__in=cancelled_like)
        .filter(start_time__date__gte=start, start_time__date__lte=end)
    )

    # Реальные платежи в периоде (по дате платежа)
    payments_q = (
        Payment.objects
        .filter(
            appointment__in=base_appt_q,
            created_at__date__gte=start,
            created_at__date__lte=end,
        )
    )

    # ── KPI
    kpi_total_revenue = payments_q.aggregate(
        x=Coalesce(Sum("amount"), Value(Decimal("0.00")))
    )["x"]
    kpi_total_appointments = base_appt_q.count()
    kpi_with_discount = base_appt_q.exclude(discount_source="").count()

    # ── Топы (spent — по платежам периода)
    pay_sub = (
        payments_q
        .filter(appointment__client_id=OuterRef("client_id"))
        .values("appointment__client_id")
        .annotate(s=Coalesce(Sum("amount"), Value(Decimal("0.00"))))
        .values("s")[:1]
    )

    top_bookers = (
        base_appt_q.values(
            "client_id",
            "client__user__first_name",
            "client__user__last_name",
            "client__user__email",
        )
        .annotate(
            appt_count=Count("id"),
            spent=Coalesce(Subquery(pay_sub), Value(Decimal("0.00"))),
        )
        .order_by("-appt_count", "-spent")[:10]
    )

    top_spenders = (
        base_appt_q.values(
            "client_id",
            "client__user__first_name",
            "client__user__last_name",
            "client__user__email",
        )
        .annotate(
            spent=Coalesce(Subquery(pay_sub), Value(Decimal("0.00"))),
            appt_count=Count("id"),
        )
        .order_by("-spent", "-appt_count")[:10]
    )

    # ── Разбивка по discount_source (по платежам)
    ds_totals = (
        payments_q
        .values(discount_source=F("appointment__discount_source"))
        .annotate(
            cnt=Count("appointment", distinct=True),
            revenue=Coalesce(Sum("amount"), Value(Decimal("0.00"))),
        )
        .order_by("-revenue")
    )

    # ── Дневные суммы по источникам (stacked bar) — по платежам
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    daily = {d.isoformat(): {"general": 0.0, "personal": 0.0, "promocode": 0.0, "none": 0.0} for d in days}

    def _bucket(src: str) -> str:
        s = (src or "").strip().lower()
        if "promo" in s:    return "promocode"
        if "personal" in s: return "personal"
        if "general" in s:  return "general"
        if not s:           return "none"
        if "+" in s:  # комбинированные значения
            parts = s.split("+")
            if any("promo" in p for p in parts):    return "promocode"
            if any("personal" in p for p in parts): return "personal"
            if any("general" in p for p in parts):  return "general"
        return "none"

    per_day = (
        payments_q
        .annotate(day=F("created_at__date"))
        .values("day", "appointment__discount_source")
        .annotate(total=Coalesce(Sum("amount"), Value(Decimal("0.00"))))
    )
    for row in per_day:
        d = row["day"].isoformat() if hasattr(row["day"], "isoformat") else str(row["day"])
        b = _bucket(row.get("appointment__discount_source"))
        if d in daily:
            daily[d][b] += float(row["total"])

    chart = {
        "labels": list(daily.keys()),
        "general":  [daily[d]["general"]   for d in daily],
        "personal": [daily[d]["personal"]  for d in daily],
        "promocode":[daily[d]["promocode"] for d in daily],
        "none":     [daily[d]["none"]      for d in daily],
    }

    # ── Разбивка по ServiceDiscount (uses/saved по айтемам; revenue — как было от цен, по платежам можно сделать отдельно)
    # Использования: позиции в валидных аппоинтментах с активной скидкой услуги на дату визита
    discount_filters = (
            Q(service__appointmentitem__appointment__in=base_appt_q) &
            Q(service__appointmentitem__appointment__start_time__date__gte=F("start_date")) &
            Q(service__appointmentitem__appointment__start_time__date__lte=F("end_date")) &
            Q(service__appointmentitem__discount_source="service")
    )
    discount_breakdown = (
        ServiceDiscount.objects
        .select_related("service")
        .annotate(
            uses=Count("service__appointmentitem", filter=discount_filters),
            revenue=Coalesce(  # по позициям (как раньше)
                Sum("service__appointmentitem__final_price", filter=discount_filters),
                Value(Decimal("0"))
            ),
            saved=Coalesce(
                Sum(
                    (F("service__appointmentitem__unit_price") - F("service__appointmentitem__final_price")),
                    filter=discount_filters
                ),
                Value(Decimal("0"))
            ),
        )
        .filter(uses__gt=0)
        .order_by("-uses", "-revenue")
    )

    # ── Разбивка по промокодам: uses — по позициям; revenue — платежи визита,
    #     распределённые пропорционально сумме final_price позиций с этим кодом в визите.
    # Платежи по визиту
    pay_by_appt = dict(
        payments_q.values("appointment_id")
        .annotate(total=Coalesce(Sum("amount"), Value(Decimal("0"))))
        .values_list("appointment_id", "total")
    )

    # Сумма final по промо-позициям в визите и веса по конкретным кодам
    promo_rows = (
        AppointmentItemPromoCode.objects
        .select_related("item__appointment", "promocode")
        .filter(item__appointment__in=base_appt_q)
        .values("promocode__code", "item__appointment_id")
        .annotate(weight=Coalesce(Sum("item__final_price"), Value(Decimal("0"))),
                  uses=Count("id"))
    )

    weights_per_appt = defaultdict(Decimal)  # сумма весов по визиту
    rows_per_code_appt = defaultdict(list)   # [(code, appt_id, weight, uses)]
    for r in promo_rows:
        code = r["promocode__code"]
        aid  = r["item__appointment_id"]
        w    = r["weight"] or Decimal("0")
        u    = r["uses"] or 0
        weights_per_appt[aid] += w
        rows_per_code_appt[(code, aid)].append((w, u))

    promo_totals = defaultdict(lambda: {"uses": 0, "revenue": Decimal("0")})
    for (code, aid), lst in rows_per_code_appt.items():
        paid = pay_by_appt.get(aid, Decimal("0"))
        total_w = weights_per_appt.get(aid, Decimal("0")) or Decimal("0")
        # если нет весов — делим поровну между кодами визита
        denom = total_w if total_w > 0 else Decimal(len({c for (c, a) in rows_per_code_appt if a == aid}) or 1)
        share = paid * (sum(w for w, _ in lst) / denom) if total_w > 0 else paid / denom
        promo_totals[code]["uses"] += sum(u for _, u in lst)
        promo_totals[code]["revenue"] += share

    promo_breakdown = [
        {"code": code, "uses": data["uses"], "revenue": data["revenue"]}
        for code, data in promo_totals.items()
    ]
    promo_breakdown.sort(key=lambda x: (-x["uses"], -x["revenue"]))

    # ── Клиентские источники (stacked/таблица/бар) — всё по платежам
    src_attr, how_attr = "source", "how_heard"
    try:
        src_field = UserProfile._meta.get_field(src_attr)
    except Exception:
        src_attr = "how_heard"
        src_field = UserProfile._meta.get_field(src_attr)
    src_choices = list(getattr(src_field, "choices", [])) or []
    try:
        how_field = UserProfile._meta.get_field(how_attr)
        how_choices = list(getattr(how_field, "choices", [])) or []
    except Exception:
        how_choices = []
    if ("unknown", "Unknown") not in src_choices:
        src_choices.append(("unknown", "Unknown"))
    if how_choices and ("unknown", "Unknown") not in how_choices:
        how_choices.append(("unknown", "Unknown"))

    def _norm(v): return ("" if v is None else str(v)).strip()
    def _is_online(v): return _norm(v).lower() == "online"

    expanded_categories = []
    for s_val, s_label in src_choices:
        if _is_online(s_val) and how_choices:
            for h_val, h_label in how_choices:
                expanded_categories.append((f"online::{h_val}", f"{s_label} — {h_label}"))
        else:
            expanded_categories.append((s_val, s_label))

    labels = [d.isoformat() for d in days]
    label_index = {s: i for i, s in enumerate(labels)}
    series = {key: [0.0] * len(labels) for key, _ in expanded_categories}

    src_path = f"appointment__client__{src_attr}"
    how_path = f"appointment__client__{how_attr}"

    rows = (
        payments_q
        .annotate(day=F("created_at__date"))
        .values("day", src_path, how_path)
        .annotate(total=Coalesce(Sum("amount"), Value(Decimal("0"))))
    )

    def _key_for_row(src_val, how_val) -> str:
        s = _norm(src_val) or "unknown"
        if _is_online(s) and how_choices:
            h = _norm(how_val) or "unknown"
            return f"online::{h}"
        return s or "unknown"

    for r in rows:
        d = r["day"].isoformat() if hasattr(r["day"], "isoformat") else str(r["day"])
        j = label_index.get(d)
        if j is None:
            continue
        key = _key_for_row(r.get(src_path), r.get(how_path))
        if key not in series:
            # если всплыла новая how_heard — добавим
            label = key
            if key.startswith("online::"):
                h_val = key.split("::", 1)[1]
                h_label = next((lbl for val, lbl in how_choices if val == h_val), h_val.title().replace("_", " "))
                s_label = next((lbl for val, lbl in src_choices if _is_online(val)), "Online")
                label = f"{s_label} — {h_label}"
            expanded_categories.append((key, label))
            series[key] = [0.0] * len(labels)
        series[key][j] += float(r["total"])

    # Таблица totals по категориям (revenue по платежам, appts/clients — по платежам этого периода)
    totals = {key: {"revenue": 0.0, "appts": set(), "clients": set()} for key, _ in expanded_categories}
    rows_total = (
        payments_q
        .values(src_path, how_path, "appointment_id", "appointment__client_id")
        .annotate(revenue=Coalesce(Sum("amount"), Value(Decimal("0"))))
    )
    for r in rows_total:
        key = _key_for_row(r.get(src_path), r.get(how_path))
        t = totals.setdefault(key, {"revenue": 0.0, "appts": set(), "clients": set()})
        t["revenue"] += float(r["revenue"])
        if r.get("appointment_id"):
            t["appts"].add(r["appointment_id"])
        if r.get("appointment__client_id"):
            t["clients"].add(r["appointment__client_id"])

    client_source_table = [
        {
            "key": key,
            "label": label,
            "revenue": round(totals[key]["revenue"], 2),
            "appts": len(totals[key]["appts"]),
            "clients": len(totals[key]["clients"]),
        }
        for key, label in expanded_categories
    ]

    client_source_stacked = {
        "labels": labels,
        "datasets": [{"key": key, "label": label, "data": series[key]} for key, label in expanded_categories],
    }

    # Бар «total revenue by source» — по платежам
    src_bar_rows = (
        payments_q
        .values(src_path)
        .annotate(revenue=Coalesce(Sum("amount"), Value(Decimal("0"))))
        .order_by("-revenue")
    )
    client_source_stats = [{"label": (_norm(r.get(src_path)) or "unknown"), "revenue": r["revenue"]} for r in src_bar_rows]
    src_labels = [r["label"] for r in client_source_stats]
    src_revenue = [float(r["revenue"]) for r in client_source_stats]

    # ── Контекст для шаблона
    context = {
        "title": "Statistics",
        "start": start,
        "end": end,
        "kpi": {
            "revenue": kpi_total_revenue,
            "appointments": kpi_total_appointments,
            "with_discount": kpi_with_discount,
        },
        "top_bookers": list(top_bookers),
        "top_spenders": list(top_spenders),
        "ds_totals": list(ds_totals),
        "discount_breakdown": list(discount_breakdown),
        "promo_breakdown": list(promo_breakdown),
        "chart": chart,

        "client_source_stats": client_source_stats,
        "client_source_chart": {"labels": src_labels, "revenue": src_revenue},

        "client_source_stacked": client_source_stacked,
        "client_source_table": client_source_table,
    }
    return render(request, "admin/statistics.html", context)

def _inject_admin_urls(original_get_urls):
    def get_urls():
        my = [
            path("stats/", admin.site.admin_view(stats_view), name="stats"),
        ]
        return my + original_get_urls()
    return get_urls

admin.site.get_urls = _inject_admin_urls(admin.site.get_urls)

def get_price_html(service):
    discount = service.get_active_discount()
    if discount:
        discounted = service.get_discounted_price()
        return format_html(
            '<span style="text-decoration: line-through; color: grey;">${}</span><br><strong>${}</strong>',
            service.base_price,
            discounted
        )
    return format_html("<strong>${}</strong>", service.base_price)



def createTable(selected_date, time_pointer, end_time, slot_times, items, masters, availabilities):
    """
    items: QuerySet[AppointmentItem] с select_related('appointment__client','service','master')
    masters: список мастеров для колонок
    """
    COLOR_PALETTE = ["#E4D08A", "#EDC2A2", "#CEAEC6", "#A3C1C9", "#C3CEA3", "#E7B3C3"]
    master_ids = [m.id for m in masters]
    MASTER_COLORS = dict(zip(master_ids, cycle(COLOR_PALETTE)))

    # ───── badges для позиции ───────────────────────────────────────────────────
    def _corner_badges_for_item(item):
        # скидка: если установлен промокод/персональная скидка на уровне позиции
        promo_html = ""
        base = item.unit_price if getattr(item, "unit_price", None) is not None else item.service.base_price
        final = getattr(item, "final_price", None)
        has_promo_rel = getattr(item, "promocode_link", None) is not None
        if has_promo_rel or (final is not None and str(final) != str(base)):
            promo_html = "<span class='badge badge--promo' title='Applied discount'>%</span>"

        # здоровье (по клиенту Appointment)
        def _health_flag_info(appt):
            prof = getattr(appt, "client", None)
            if not prof:
                return False, "", ""
            hc = getattr(prof, "health", None) or getattr(prof, "health_conditions", None) or {}
            def _to_str(v):
                if isinstance(v, (list, tuple)): return ", ".join(map(str, v))
                return (v or "").strip()
            has_all = bool(hc.get("has_allergies")) or bool(_to_str(hc.get("allergies_text")))
            has_med = bool(_to_str(hc.get("medications")))
            has_ctr = bool(_to_str(hc.get("contraindications")))
            has_ch = bool(_to_str(hc.get("chronic_conditions")))
            if not (has_all or has_med or has_ctr or has_ch):
                return False, "", ""
            try:
                url = reverse("health-view-master", args=[prof.id])
            except NoReverseMatch:
                url = ""
            return True, url, "Есть важные данные в анкете здоровья — нажмите, чтобы посмотреть"

        health_html = ""
        show_flag, flag_url, flag_title = _health_flag_info(item.appointment)

        if show_flag:
            ico = "⚕️"
            health_html = (
                f'<a class="badge badge--health" href="{flag_url}" title="{flag_title}">{ico}</a>'
                if flag_url else f'<span class="badge badge--health" title="{flag_title}">{ico}</span>'
            )
        if not promo_html and not health_html:
            return ""
        return f"<div class='corner-badges'>{promo_html}{health_html}</div>"

    # ───── вспомогательные ──────────────────────────────────────────────────────
    def _item_meta(item, master_obj):
        s_local = localtime(item.start_time)
        # duration берём из Item (в нём уже может быть extra_time учтён)【:contentReference[oaicite:3]{index=3}】
        total_min = int(getattr(item, "duration_min", 0) or 0)
        e_local = s_local + timedelta(minutes=total_min)

        # Статус — по родительскому Appointment (последний из истории)
        last_status = item.appointment.appointmentstatushistory_set.order_by("-set_at").first()
        status_name = last_status.status.name if last_status else "Unknown"
        items_count = len(list(item.appointment.items.all()))
        # Цены: базовая для позиции (unit_price или base_price услуги),
        # финальная — из item.final_price (если None, показываем базовую)
        base_price = item.appointment.total_without_discounts(ignore_overrides=False)
        final_price = item.appointment.final_price


        client = item.appointment.client
        client_label = client.get_full_name() or client.user.username

        return {
            "s_local": s_local,
            "e_local": e_local,
            "status": status_name,
            "master_label": escape(str(master_obj)),
            "client_label": escape(client_label),
            "service_label": escape(item.service.name),
            "time_label": f"{s_local.strftime('%I:%M%p').lstrip('0')} - {e_local.strftime('%I:%M%p').lstrip('0')}",
            "duration_label": f"{total_min}min",
            "base_price": f"${base_price}",
            "items_count": items_count,
            "final_price": f"${final_price}",
            "phone": escape(getattr(client, "phone", "") or ""),
        }

    def _cell_html_item(item, meta, show_cancelled=False):
        cancelled_suffix = " (Cancelled)" if show_cancelled else ""
        opacity = ".7" if show_cancelled else "1"
        corner = _corner_badges_for_item(item)
        footer = f"<div class='cell-mini-footer'>{meta['items_count']} services</div>" if meta.get('items_count', 1) > 1 else ""
        return f"""
        {corner}
        <div style="opacity:{opacity}; ">
          <div style="font-size:1.8vh;">
            {meta['s_local'].strftime('%I:%M').lstrip('0')} – {meta['e_local'].strftime('%I:%M').lstrip('0')}
            <strong>{meta['client_label']}</strong>
          </div>
          <div style="font-size:1.8vh;">
            {meta['service_label']}{cancelled_suffix}
          </div>
          {footer}
        </div>
        """

    def _make_item_cell(kind, item, rowspan, colspan, master_obj, bg, show_cancelled=False):
        meta = _item_meta(item, master_obj)
        return {
            "rowspan": rowspan,
            "colspan": colspan,
            "kind": kind,
            "appt_id": item.appointment_id,  # важно для ссылки клика по шаблону【:contentReference[oaicite:4]{index=4}】
            "html": _cell_html_item(meta=meta, item=item, show_cancelled=show_cancelled),
            "background": bg,
            "appointment": item,  # шаблон проверяет наличие cell.appointment для ветки рендера【:contentReference[oaicite:5]{index=5}】
            "client": meta["client_label"],
            "phone": meta["phone"],
            "service": meta["service_label"],
            "status": meta["status"],
            "master": meta["master_label"],
            "time_label": meta["time_label"],
            "duration": meta["duration_label"],
            "base_price": meta["base_price"],
            "final_price": meta["final_price"],
            "items_count": meta["items_count"],
        }

    def _make_unavail_cell(kind, rowsp, colspan, avail_id, reason, from_s, to_s, until_s):
        return {
            "rowspan": rowsp,
            "colspan": colspan,
            "kind": kind,
            "availability_id": avail_id,
            "html": f"""
                <div style="opacity:.85">
                  {escape(reason)}<br>
                  <small>{escape(from_s)}–{escape(to_s)}</small>
                </div>
            """,
            "unavailable": True,
            "reason": reason,
            "start": from_s,
            "end": to_s,
            "until": until_s,
        }

    # ───── сетка времени ────────────────────────────────────────────────────────
    while time_pointer <= end_time:
        slot_times.append(time_pointer.strftime("%H:%M"))
        time_pointer += timedelta(minutes=15)

    two_col_map = {}
    cancel_lanes = {}
    skip_two = {}
    skip_lane = {}
    for m in masters:
        mid = m.id
        two_col_map[mid] = {}
        cancel_lanes[mid] = {0: {}, 1: {}}
        skip_two[mid] = {}
        skip_lane[mid] = {0: {}, 1: {}}

    # статус Cancelled
    cancelled_status = AppointmentStatus.objects.filter(name="Cancelled").first()
    cancelled_id = getattr(cancelled_status, "id", None)

    # ───── позиции (AppointmentItem) ────────────────────────────────────────────
    for item in items:
        start_local = localtime(item.start_time)
        if start_local.date() != selected_date:
            continue

        mid = item.master_id
        slot_key = start_local.strftime("%H:%M")
        total_min = int(getattr(item, "duration_min", 0) or 0)
        rowspan = max(1, (-(-total_min // 15)))  # ceil

        last_status = item.appointment.appointmentstatushistory_set.order_by("-set_at").first()
        is_cancelled = bool(last_status and last_status.status_id == cancelled_id)

        if not is_cancelled:
            two_col_map[mid][slot_key] = {
                "kind": "appt_active",
                "rowspan": rowspan,
                "colspan": 2,
                "item": item,
            }
            for i in range(rowspan):
                t = (start_local + timedelta(minutes=15 * i)).strftime("%H:%M")
                skip_two[mid][t] = True
        else:
            lane0_busy = skip_lane[mid][0].get(slot_key) or (slot_key in cancel_lanes[mid][0])
            lane = 0 if not lane0_busy else 1
            cancel_lanes[mid][lane][slot_key] = {
                "kind": "appt_cancelled",
                "rowspan": rowspan,
                "colspan": 1,
                "item": item,
            }
            for i in range(rowspan):
                t = (start_local + timedelta(minutes=15 * i)).strftime("%H:%M")
                skip_lane[mid][lane][t] = True

    # ───── тайм-офф (перерывы/отпуска) ─────────────────────────────────────────
    for period in availabilities:
        mid = int(getattr(period.master, "id", period.master))
        start = localtime(period.start_time)
        end = localtime(period.end_time)
        if start.date() > selected_date or end.date() < selected_date:
            continue

        day_start = datetime.combine(selected_date, time(8, 0)).replace(tzinfo=start.tzinfo)
        day_end = datetime.combine(selected_date, time(21, 15)).replace(tzinfo=start.tzinfo)
        block_start = max(start, day_start)
        block_end = min(end, day_end)
        if block_start >= block_end:
            continue

        minutes = int((block_end - block_start).total_seconds() // 60)
        rowsp = max(1, (-(-minutes // 15)))  # ceil
        slot_key = block_start.strftime("%H:%M")

        if slot_key not in two_col_map.get(mid, set()):
            if mid not in two_col_map:
                two_col_map[mid] = {}
            two_col_map[mid][slot_key] = {
                "kind": "unavailable",
                "rowspan": rowsp,
                "colspan": 2,
                "reason": period.get_reason_display(),
                "from": block_start.strftime("%I:%M%p").lstrip("0"),
                "to": block_end.strftime("%I:%M%p").lstrip("0"),
                "until": period.end_time.strftime("%d %b %Y"),
                "availability_id": period.id,
            }
            for i in range(rowsp):
                t = (block_start + timedelta(minutes=15 * i)).strftime("%H:%M")
                if mid not in skip_two:
                    skip_two[mid] = {}
                skip_two[mid][t] = True

    # ───── финальная сборка строк ──────────────────────────────────────────────
    calendar_table = []

    for time_str in slot_times:
        row = {"time": time_str, "cells": []}

        for master in masters:
            mid = master.id

            # 1) старт двухколоночной?
            if time_str in two_col_map[mid]:
                cell = two_col_map[mid][time_str]

                # Проверяем конфликт с отменённой слева
                try:
                    start_idx = slot_times.index(time_str)
                except ValueError:
                    start_idx = 0
                span_times = slot_times[start_idx:start_idx + cell["rowspan"]]
                overlaps_cancel_left = any(skip_lane[mid][0].get(t) for t in span_times)

                if not overlaps_cancel_left:
                    if cell["kind"] == "appt_active":
                        row["cells"].append(
                            _make_item_cell(
                                kind="appt_active",
                                item=cell["item"],
                                rowspan=cell["rowspan"],
                                colspan=2,
                                master_obj=master,
                                bg=MASTER_COLORS.get(mid),
                                show_cancelled=False,
                            )
                        )
                    else:
                        row["cells"].append(
                            _make_unavail_cell(
                                kind="unavailable",
                                rowsp=cell["rowspan"],
                                colspan=2,
                                avail_id=cell["availability_id"],
                                reason=cell["reason"],
                                from_s=cell["from"],
                                to_s=cell["to"],
                                until_s=cell["until"],
                            )
                        )
                    continue

                # Перенос вправо (lane-right)
                for t in span_times:
                    skip_lane[mid][1][t] = True

                c0 = cancel_lanes[mid][0].get(time_str)
                if c0:
                    row["cells"].append(
                        _make_item_cell(
                            kind="appt_cancelled",
                            item=c0["item"],
                            rowspan=c0["rowspan"],
                            colspan=1,
                            master_obj=master,
                            bg=MASTER_COLORS.get(mid),
                            show_cancelled=True,
                        )
                    )
                elif not skip_lane[mid][0].get(time_str):
                    row["cells"].append({
                        "rowspan": 1, "colspan": 1, "kind": "free_half",
                        "master_id": mid, "html": "", "lane": "left"
                    })

                # правая половина переносимого блока
                row["cells"].append(
                    _make_item_cell(
                        kind="appt_active_right" if cell["kind"] == "appt_active" else "unavailable_right",
                        item=cell.get("item"),
                        rowspan=cell["rowspan"],
                        colspan=1,
                        master_obj=master,
                        bg=MASTER_COLORS.get(mid),
                        show_cancelled=False,
                    ) if cell["kind"] == "appt_active" else
                    _make_unavail_cell(
                        kind="unavailable_right",
                        rowsp=cell["rowspan"],
                        colspan=1,
                        avail_id=cell["availability_id"],
                        reason=cell["reason"],
                        from_s=cell["from"],
                        to_s=cell["to"],
                        until_s=cell["until"],
                    )
                )
                continue

            # 2) lane-режим (отменённые/перенесённые)
            lane0_start = time_str in cancel_lanes[mid][0]
            lane0_skip = bool(skip_lane[mid][0].get(time_str))
            lane1_skip = bool(skip_lane[mid][1].get(time_str))
            lane_mode = lane0_start or lane0_skip or lane1_skip

            if lane_mode:
                # левая половинка
                c0 = cancel_lanes[mid][0].get(time_str)
                if c0:
                    row["cells"].append(
                        _make_item_cell(
                            kind="appt_cancelled",
                            item=c0["item"],
                            rowspan=c0["rowspan"],
                            colspan=1,
                            master_obj=master,
                            bg=MASTER_COLORS.get(mid),
                            show_cancelled=True,
                        )
                    )
                elif not lane0_skip:
                    row["cells"].append({
                        "rowspan": 1, "colspan": 1, "kind": "free_half",
                        "master_id": mid, "html": "", "lane": "left"
                    })

                # правая половинка
                if not lane1_skip:
                    row["cells"].append({
                        "rowspan": 1, "colspan": 1, "kind": "free_half",
                        "master_id": mid, "html": "", "lane": "right"
                    })
                continue

            # 3) продолжающиеся двухколоночные
            if skip_two[mid].get(time_str):
                continue

            # 4) дефолтная свободная двухколоночная
            row["cells"].append({
                "rowspan": 1,
                "colspan": 2,
                "kind": "free",
                "master_id": mid,
                "html": "",
            })

        calendar_table.append(row)

    return calendar_table


def _health_flag_info(appt):
    """
    True/False + (url|""), title — нужно ли показывать флаг здоровья.
    Поддерживает и profile.health, и profile.health_conditions.
    """
    prof = getattr(appt, "client", None)
    if not prof:
        return False, "", ""

    hc = getattr(prof, "health", None) or getattr(prof, "health_conditions", None) or {}

    def _to_str(v):
        if isinstance(v, (list, tuple)):
            return ", ".join(map(str, v))
        return (v or "").strip()

    has_all = bool(hc.get("has_allergies")) or bool(_to_str(hc.get("allergies")))
    has_med = bool(_to_str(hc.get("medications")))
    has_ctr = bool(_to_str(hc.get("contraindications")))

    if not (has_all or has_med or has_ctr):
        return False, "", ""

    try:
        url = reverse("health-view-master", args=[prof.id])
    except NoReverseMatch:
        url = ""

    return True, url, "Есть важные данные в анкете здоровья — нажмите, чтобы посмотреть"

def _corner_badges_html(appt, appt_promocode):
    """
    Возвращает HTML «уголка» со значками (скидка + здоровье).
    Вызываем внутри карточки визита, у родителя должен быть position:relative.
    """
    # скидка
    promo_html = ""
    if appt_promocode or appt.final_price != appt.service.base_price:
        promo_html = "<span class='badge badge--promo' title='Applied discount'>%</span>"

    # здоровье
    show_flag, flag_url, flag_title = _health_flag_info(appt)
    health_html = ""
    if show_flag:
        ico = "⚕️"  # можно заменить на 🩺
        if flag_url:
            health_html = f'<a class="badge badge--health" href="{flag_url}" title="{flag_title}">{ico}</a>'
        else:
            health_html = f'<span class="badge badge--health" title="{flag_title}">{ico}</span>'

    if not promo_html and not health_html:
        return ""

    return f"<div class='corner-badges'>{promo_html}{health_html}</div>"

# core/admin.py
from django.db import connection

def custom_index(request):
    from django.template.response import TemplateResponse

    tables = set(connection.introspection.table_names())
    userprof = None
    if "core_userprofile" in tables:
        try:
            userprof = getattr(request.user, "userprofile", None)
        except Exception:
            userprof = None

    ctx = {"userprof": userprof}
    return TemplateResponse(request, "admin/index.html", ctx)
