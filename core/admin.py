from bisect import bisect_left
from urllib.parse import urlencode

from django.contrib.admin import DateFieldListFilter

from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.contrib import admin
from django.db.models import Sum, Count, Q
from itertools import cycle
from django.utils.timezone import localtime, datetime, make_aware, localdate
from django.utils.html import escape
from django.shortcuts import redirect
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.contrib.auth.models import Permission
from django.db.models.functions import Coalesce
from django.db.models import DecimalField, Value
from django.contrib.contenttypes.models import ContentType
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json
import csv
from django.urls import path, reverse, NoReverseMatch
from django.http import HttpResponse
from .filters import *
from .models import *
from .forms import *

# -----------------------------
# Custom filter for filtering users by Role
# -----------------------------

# Переопределение index view
def custom_index(request):
    today = localdate()
    week_ago = today - timedelta(days=6)
    week = [today + timedelta(days=i) for i in range(7)]
    appointments_qs = Appointment.objects.filter(start_time__date__range=[week_ago, today])
    payments_qs = Payment.objects.filter(appointment__start_time__date__range=[week_ago, today])
    is_master = (
            hasattr(request.user, "userprofile")
            and request.user.userprofile.userrole_set.filter(
        role__name="Master",
        user__user__is_superuser=False,  # ← добавили ещё один __user
    ).exists()
    )
    chart_data = []
    total_sales = 0
    for i in range(7):
        day = today - timedelta(days=6 - i)
        sales = payments_qs.filter(appointment__start_time__date=day).aggregate(total=Sum("amount"))["total"] or 0
        appts = appointments_qs.filter(start_time__date=day).count()
        total_sales += float(sales)
        chart_data.append({
            "day": day.strftime("%a %d"),
            "sales": float(sales),
            "appointments": appts
        })

    confirmed = AppointmentStatus.objects.filter(name="Confirmed").first()
    cancelled = AppointmentStatus.objects.filter(name="Cancelled").first()
    upcoming = Appointment.objects.filter(start_time__range=(today, today+timedelta(7)))
    confirmed_count = upcoming.filter(appointmentstatushistory__status=confirmed).count()
    cancelled_count = upcoming.filter(appointmentstatushistory__status=cancelled).count()

    top_services = Service.objects.annotate(count=Count("appointment")).order_by("-count")[:3]

    master_role = Role.objects.filter(name="Master").first()

    today = timezone.now().date()
    first_day = today.replace(day=1)
    masters = MasterProfile.objects.filter(
        user__userrole__role=master_role
    ).annotate(
        total=Sum(
            "appointments_as_master__service__base_price",
            filter=Q(appointments_as_master__start_time__date__gte=first_day)
        )
    )

    top_masters = sorted(masters, key=lambda m: m.total or 0, reverse=True)[:3]


    recent_appointments = Appointment.objects.select_related("client", "master", "service").order_by("-start_time")[:20]
    today_appointments = Appointment.objects.filter(
        start_time__date=today,
        start_time__gte=timezone.now()
    )
    if is_master:
        today_appointments = today_appointments.filter(master=request.user.masterprofile)

    today_appointments = today_appointments.order_by("start_time")

    daily_counts = []

    for day in week:
        confirmed_appts = Appointment.objects.filter(
            start_time__date=day,
            appointmentstatushistory__status=confirmed
        ).count()

        cancelled_appts =  Appointment.objects.filter(
            start_time__date=day,
            appointmentstatushistory__status=cancelled
        ).count()

        daily_counts.append({
            "day": day.strftime("%a %d"),  # e.g., "Fri 25"
            "confirmed": confirmed_appts,
            "cancelled": cancelled_appts
        })
    context = admin.site.each_context(request)
    context.update({
        "is_master": is_master,
        "daily_appointments": daily_counts,
        "chart_data": chart_data,
        "total_sales": total_sales,
        "upcoming_total": upcoming.count(),
        "confirmed_count": confirmed_count,
        "cancelled_count": cancelled_count,
        "top_services": top_services,
        "top_masters": top_masters,
        "today": localdate(),
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
    export_fields = ['username', 'email', 'first_name', 'last_name', 'phone', 'birth_date', 'address', 'user_roles', 'is_staff', 'is_superuser', 'is_active', 'source']

    def get_export_row(self, obj):
        phone = obj.userprofile.phone if hasattr(obj, 'userprofile') else ''
        birth_date = obj.userprofile.birth_date if hasattr(obj, 'userprofile') else ''
        address = obj.userprofile.address if hasattr(obj, 'userprofile') else ''
        source = obj.userprofile.source if hasattr(obj, 'userprofile') else ''
        consent = obj.userprofile.email_marketing_consent if hasattr(obj, 'userprofile') else ''
        roles = ", ".join([ur.role.name for ur in obj.userprofile.userrole_set.all()])

        return [
            obj.username,
            obj.email,
            obj.first_name,
            obj.last_name,
            phone,
            birth_date,
            address,
            roles,
            obj.is_staff,
            obj.is_superuser,
            obj.is_active,
            source,
            consent
        ]
    # Fields shown when adding a new user
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'first_name', 'last_name', 'phone', 'address','birth_date',
                       'password1', 'password2', 'is_staff', 'is_active', 'is_superuser', 'email_marketing_consent', 'how_heard'),
        }),
    )

    # Fields shown in user list
    list_display = ('username', 'email', 'first_name', 'last_name', 'staff_status', 'phone', 'birth_date', 'user_roles', 'send_notify_button')
    list_filter = ('is_staff', 'is_superuser', 'is_active', RoleFilter, 'userprofile__how_heard')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'userprofile__phone')

    # Field layout when editing a user
    fieldsets = (
        (None, {'fields': ('username', 'email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'phone', 'birth_date', 'address', 'how_heard', 'email_marketing_consent')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Files', {'fields': ('files',)}),
        ('Notes', {'fields': ('notes',)})
    )

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

    @admin.display(description="")
    def send_notify_button(self, obj):
        return mark_safe(
            f'<button type="button" class="send-notify-btn" '
            f'data-user-id="{obj.id}" '
            f'data-user-name="{obj.get_full_name() or obj.username}">Send Notification</button>'
        )
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('send_notification/', self.admin_site.admin_view(self.send_notification_view), name='send_notification'),
        ]
        return custom_urls + urls

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

    @admin.display(description="Roles")
    def user_roles(self, instance):
        roles = instance.userprofile.userrole_set.select_related('role').all()
        return ", ".join([ur.role.name for ur in roles]) if roles else "-"


# Unregister the default User admin and re-register with our custom one
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)

# -----------------------------
# Mixin to filter users who have the "Master" role
# -----------------------------
# class MasterSelectorMixing:
#     """
#     Restricts 'master' foreign key fields to users who have the 'Master' role.
#     """
#     def formfield_for_foreignkey(self, db_field, request, **kwargs):
#         if db_field.name == "master":
#             master_role = Role.objects.filter(name="Master").first()
#             if master_role:
#                 master_user_ids = UserRole.objects.filter(role=master_role).values_list('user_id', flat=True)
#                 kwargs["queryset"] = CustomUserDisplay.objects.filter(id__in=master_user_ids)
#             else:
#                 kwargs["queryset"] = User.objects.none()
#         return super().formfield_for_foreignkey(db_field, request, **kwargs)



@admin.register(MasterAvailability)
class MasterAvailabilityAdmin(ExportCsvMixin, admin.ModelAdmin):
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
@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    change_list_template = "admin/appointments_calendar.html"
    form = AppointmentForm
    fields = ['client', 'master', 'service', 'start_time', 'payment_status', 'status']
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

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        class WrappedForm(form):
            def __init__(self, *args, **kwargs_inner):
                kwargs_inner["user"] = request.user
                super().__init__(*args, **kwargs_inner)

                # выставить initial статуса для редактирования
                if obj:
                    last_status = obj.appointmentstatushistory_set.order_by('-set_at').first()
                    if last_status:
                        self.fields['status'].initial = last_status.status

                # мастеру – заблокировать поле master
                if hasattr(request.user, "master_profile") and not request.user.is_superuser:
                    if "master" in self.fields:
                        self.fields["master"].disabled = True

        return WrappedForm

    # --- права ---
    def has_add_permission(self, request):
        if request.user.is_superuser or request.user.is_staff:
            return True
        if hasattr(request.user, "master_profile"):
            return True   # разрешаем мастеру создавать
        return False

    def has_change_permission(self, request, obj=None):
        # админ → всё
        if request.user.is_superuser or request.user.is_staff:
            return True
        # мастер → только свои записи
        if hasattr(request.user, "master_profile"):
            if obj is None:
                return True  # список доступен
            return obj.master_id == request.user.master_profile.id
        return False

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser or request.user.is_staff:
            return True
        if hasattr(request.user, "master_profile"):
            if obj is None:
                return True
            return obj.master_id == request.user.master_profile.id
        return False

    # --- только свои записи мастеру ---
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if hasattr(request.user, "master_profile") and not request.user.is_superuser:
            return qs.filter(master=request.user.master_profile)
        return qs

    # --- поле master фиксируем для мастера ---
    def formfield_for_foreignkey(self, db_field, request, **kwargs):

        if db_field.name == "master" and hasattr(request.user, "master_profile") and not request.user.is_superuser:
            kwargs["queryset"] = MasterProfile.objects.filter(id=request.user.masterprofile.id)
            kwargs["initial"] = request.user.masterprofile.id

        return super().formfield_for_foreignkey(db_field, request, **kwargs)




    def changelist_view(self, request, extra_context=None):

        selected_date = request.GET.get('date')

        if selected_date:
            selected_date = datetime.strptime(selected_date, '%Y-%m-%d').date()

        else:
            selected_date = timezone.localdate()

        services = Service.objects.all()
        appointment_statuses = AppointmentStatus.objects.all()
        payment_statuses = PaymentStatus.objects.all()

        appointments = Appointment.objects.select_related('client', 'service', 'master')


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
            appointments = appointments.filter(appointmentstatushistory__status_id=request.GET["status"])
        if request.GET.get("payment_status"):
            appointments = appointments.filter(payment_status_id__in=request.GET.getlist("payment_status"))

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
    def save_model(self, request, obj, form, change):
        if hasattr(request.user, "master_profile") and not request.user.is_superuser:
            obj.master = request.user.master_profile
        super().save_model(request, obj, form, change)


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
    list_display = ('appointment', 'amount', 'method')
    list_filter = ('method',)
    export_fields = ['appointment', 'amount', 'method']
    search_fields = (
        'appointment__client__user__first_name', 'appointment__client__user__last_name',
        'appointment__master__user__first_name', 'appointment__master__user__last_name',
        'appointment__service__name',
    )


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


#-----------------------------
# Appointments Promocode Admin
#-----------------------------
@admin.register(AppointmentPromoCode)
class PromoCodeAdmin(ExportCsvMixin ,admin.ModelAdmin):
    list_display = ('appointment', 'promocode')

    export_fields = ['appointment', 'promocode']


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

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    # Явно перечислим поля на форме
    fields = (
        "user",
        "phone",
        "birth_date",
        "address",
        "how_heard",
        "email_marketing_consent",
        "notes",     # единственное редактируемое поле для мастера
    )

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




@admin.register(MasterProfile)
class MasterProfileAdmin(ExportCsvMixin,admin.ModelAdmin):
    add_form = MasterCreateFullForm
    readonly_fields = ['password_display']
    export_fields = ["first_name","last_name","email","username" ,"phone","birth_date","address", "profession", 'bio',"work_start", "work_end", "room", "is_staff", "is_superuser", 'is_active']

    def get_export_row(self, obj):
        phone = obj.user.userprofile.phone if hasattr(obj, 'user') else ''
        birth_date = obj.user.userprofile.birth_date if hasattr(obj, 'user') else ''
        address = obj.user.userprofile.address if hasattr(obj, 'user') else ''


        return [
            obj.user.first_name,
            obj.user.last_name,
            obj.user.email,
            obj.user.username,
            phone,
            birth_date,
            address,
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


    list_display = ("get_name", "room", "profession", "work_start", "work_end")

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

             "view_userprofile", "change_userprofile"
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

def createTable(selected_date, time_pointer, end_time, slot_times, appointments, masters, availabilities):
    def createTable(selected_date, time_pointer, end_time, slot_times, appointments, masters, availabilities):
        """
        Строит таблицу расписания для дня:
          - две колонки на мастера (левая/правая полоса)
          - активные/отменённые записи
          - тайм‑офф (перерывы/отпуска)
        Исправления:
          • Тайм‑офф больше НЕ помечает дорожки в skip_lane → корректный colspan=2.
          • Дублирующийся код формирования ячеек вынесен в хелперы.
        """
    from itertools import cycle
    from datetime import datetime, timedelta, time
    from django.utils.timezone import localtime
    from django.utils.html import escape

    COLOR_PALETTE = ["#E4D08A", "#EDC2A2", "#CEAEC6", "#A3C1C9", "#C3CEA3", "#E7B3C3"]
    master_ids = [m.id for m in masters]
    MASTER_COLORS = dict(zip(master_ids, cycle(COLOR_PALETTE)))

    # ───── вспомогательные ──────────────────────────────────────────────────────
    def _appt_meta(appt, master_obj):
        s_local = localtime(appt.start_time)
        total_min = (appt.service.duration_min or 0) + (appt.service.extra_time_min or 0)
        e_local = s_local + timedelta(minutes=total_min)
        appt_promocode = getattr(appt, "appointmentpromocode", None)
        last_status = appt.appointmentstatushistory_set.order_by("-set_at").first()
        status_name = last_status.status.name if last_status else "Unknown"
        return {
            "s_local": s_local,
            "e_local": e_local,
            "status": status_name,
            "promo": appt_promocode,
            "master_label": escape(str(master_obj)),
            "client_label": escape(appt.client.get_full_name() or appt.client.user.username),
            "service_label": escape(appt.service.name),
            "time_label": f"{s_local.strftime('%I:%M%p').lstrip('0')} - {e_local.strftime('%I:%M%p').lstrip('0')}",
            "duration_label": f"{appt.service.duration_min}min",
            "discount_label": (f"-{appt_promocode.promocode.discount_percent}"
                               if appt_promocode else ""),
            "price_discounted": f"${appt.service.get_discounted_price()}",
            "price": f"${appt.service.base_price}",
        }

    def _cell_html_appt(meta, show_cancelled=False):
        # Один HTML для активной и отменённой (различается прозрачность/текст)
        cancelled_suffix = " (Cancelled)" if show_cancelled else ""
        opacity = ".7" if show_cancelled else "1"
        promo_html = ""
        return f"""
            <div style="opacity:{opacity}">
              <div style="font-size:1.8vh;">
                {meta['s_local'].strftime('%I:%M').lstrip('0')} – {meta['e_local'].strftime('%I:%M').lstrip('0')}
                <strong>{meta['client_label']}</strong>
              </div>
              <div style="font-size:1.8vh;">
                {meta['service_label']}{cancelled_suffix}
                {promo_html}
              </div>
            </div>
        """

    def _make_appt_cell(kind, appt, rowspan, colspan, master_obj, bg, show_cancelled=False):
        meta = _appt_meta(appt, master_obj)
        return {
            "rowspan": rowspan,
            "colspan": colspan,
            "kind": kind,
            "appt_id": appt.id,
            "html": _cell_html_appt(meta, show_cancelled=show_cancelled),
            "background": bg,
            "appointment": appt,
            "client": meta["client_label"],
            "phone": escape("+1 " + getattr(appt.client, "phone", "")),
            "service": meta["service_label"],
            "status": meta["status"],
            "master": meta["master_label"],
            "time_label": meta["time_label"],
            "duration": meta["duration_label"],
            "discount": meta["discount_label"],
            "price_discounted": meta["price_discounted"],
            "price": meta["price"],
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
    cancel_lanes = {}   # cancel_lanes[mid][lane][time] → старт отменённой в дорожке 0|1
    skip_two = {}       # skip двухколоночных (active/unavailable)
    skip_lane = {}      # skip одноколоночных по дорожкам (тянущиеся блоки)

    for m in masters:
        mid = m.id
        two_col_map[mid] = {}
        cancel_lanes[mid] = {0: {}, 1: {}}
        skip_two[mid] = {}
        skip_lane[mid] = {0: {}, 1: {}}

    # статус Cancelled
    cancelled_status = AppointmentStatus.objects.filter(name="Cancelled").first()
    cancelled_id = getattr(cancelled_status, "id", None)

    # ───── записи (appointments) ────────────────────────────────────────────────
    for appt in appointments:
        start_local = localtime(appt.start_time)
        if start_local.date() != selected_date:
            continue

        mid = appt.master_id
        slot_key = start_local.strftime("%H:%M")
        total_min = (appt.service.duration_min or 0) + (appt.service.extra_time_min or 0)
        rowspan = max(1, (-(-total_min // 15)))  # ceil

        last_status = appt.appointmentstatushistory_set.order_by("-set_at").first()
        is_cancelled = bool(last_status and last_status.status_id == cancelled_id)

        if not is_cancelled:
            two_col_map[mid][slot_key] = {
                "kind": "appt_active",
                "rowspan": rowspan,
                "colspan": 2,
                "appt": appt,
            }
            for i in range(rowspan):
                t = (start_local + timedelta(minutes=15 * i)).strftime("%H:%M")
                skip_two[mid][t] = True
        else:
            # кладём отменённую запись в левую дорожку, если свободно, иначе в правую
            lane0_busy = skip_lane[mid][0].get(slot_key) or (slot_key in cancel_lanes[mid][0])
            lane = 0 if not lane0_busy else 1
            cancel_lanes[mid][lane][slot_key] = {
                "kind": "appt_cancelled",
                "rowspan": rowspan,
                "colspan": 1,
                "appt": appt,
            }
            for i in range(rowspan):
                t = (start_local + timedelta(minutes=15 * i)).strftime("%H:%M")
                skip_lane[mid][lane][t] = True

    # ───── тайм‑офф (перерывы/отпуска) ─────────────────────────────────────────
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

        # ВАЖНО: НЕ занимаем skip_lane для тайм‑офф (раньше это заставляло colspan=1)
        if slot_key not in two_col_map[mid]:
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
                skip_two[mid][t] = True  # только блокируем двухколоночные
            # Больше НЕ трогаем skip_lane → тайм‑офф рисуется как полноценный блок на 2 колонки.

    # ───── финальная сборка строк ──────────────────────────────────────────────
    calendar_table = []

    for time_str in slot_times:
        row = {"time": time_str, "cells": []}

        for master in masters:
            mid = master.id

            # 1) старт двухколоночной?
            if time_str in two_col_map[mid]:
                cell = two_col_map[mid][time_str]

                # проверим, не тянется ли слева отменённая запись на любой из слотов диапазона
                try:
                    start_idx = slot_times.index(time_str)
                except ValueError:
                    start_idx = 0
                span_times = slot_times[start_idx:start_idx + cell["rowspan"]]
                overlaps_cancel_left = any(skip_lane[mid][0].get(t) for t in span_times)

                # если нет пересечения — рисуем как полноценный 2‑колоночный блок
                if not overlaps_cancel_left:
                    if cell["kind"] == "appt_active":
                        row["cells"].append(
                            _make_appt_cell(
                                kind="appt_active",
                                appt=cell["appt"],
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

                # иначе переносим двухколоночный блок вправо на весь диапазон
                for t in span_times:
                    skip_lane[mid][1][t] = True  # правая полоса занята этим блоком

                # слева — отменённая (если стартует сейчас) или пустая половинка
                c0 = cancel_lanes[mid][0].get(time_str)
                if c0:
                    row["cells"].append(
                        _make_appt_cell(
                            kind="appt_cancelled",
                            appt=c0["appt"],
                            rowspan=c0["rowspan"],
                            colspan=1,
                            master_obj=master,
                            bg=MASTER_COLORS.get(mid),
                            show_cancelled=True,
                        )
                    )
                elif not skip_lane[mid][0].get(time_str):
                    row["cells"].append({
                        "rowspan": 1,
                        "colspan": 1,
                        "kind": "free_half",
                        "master_id": mid,
                        "html": "",
                        "lane": "left",
                    })

                # справа — переносимый блок (как одна половинка)
                if cell["kind"] == "appt_active":
                    row["cells"].append(
                        _make_appt_cell(
                            kind="appt_active_right",
                            appt=cell["appt"],
                            rowspan=cell["rowspan"],
                            colspan=1,
                            master_obj=master,
                            bg=MASTER_COLORS.get(mid),
                            show_cancelled=False,
                        )
                    )
                else:
                    row["cells"].append(
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
                continue  # к следующему мастеру

            # 2) lane‑режим — проверяем ДО skip_two!
            lane0_start = time_str in cancel_lanes[mid][0]
            lane0_skip = bool(skip_lane[mid][0].get(time_str))   # тянется отменённая слева
            lane1_skip = bool(skip_lane[mid][1].get(time_str))   # тянется перенесённый вправо блок
            lane_mode = lane0_start or lane0_skip or lane1_skip

            if lane_mode:
                # левая половинка
                c0 = cancel_lanes[mid][0].get(time_str)
                if c0:
                    row["cells"].append(
                        _make_appt_cell(
                            kind="appt_cancelled",
                            appt=c0["appt"],
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

            # 3) обычный skip двухколоночной (продолжение блока)
            if skip_two[mid].get(time_str):
                continue

            # 4) дефолтная пустая двухколоночная
            row["cells"].append({
                "rowspan": 1,
                "colspan": 2,
                "kind": "free",
                "master_id": mid,
                "html": "",
            })

        calendar_table.append(row)

    return calendar_table