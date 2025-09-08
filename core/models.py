from decimal import Decimal, InvalidOperation

from django.apps import apps
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models, transaction
from django.contrib.auth.models import User
import uuid
from django.core.exceptions import ValidationError
from datetime import timedelta, time
import os

from django.db.models import OuterRef, Subquery, Sum, Prefetch
from django.utils import timezone
from django.utils.timezone import localtime
from core.validators import clean_phone, clean_ab_postal_code
from django.conf import settings


from storages.backends.s3boto3 import S3Boto3Storage
# --- 1. ROLES ---

class Role(models.Model):
    """
    Represents a role that can be assigned to a user (e.g., Master, Client, Admin).
    """
    name = models.CharField(max_length=20, unique=True)

    def __str__(self):
        return self.name


class CustomUserDisplay(User):
    """
    Proxy model for Django's User to allow customization in admin views and display logic.
    """
    class Meta:
        proxy = True


    def __str__(self):
        full_name = self.get_full_name()
        return full_name if full_name else self.username
    @property
    def notes(self) -> str:
        # безопасно вернёт '' если профиля/поля нет
        return getattr(getattr(self, 'userprofile', None), 'notes', '')


class HowHeard(models.TextChoices):
    GOOGLE = "google", "Google search"
    INSTAGRAM = "instagram", "Instagram"
    TIKTOK = "tiktok", "TikTok"
    FRIEND = "friend", "Friends/Family"
    OTHER = "other", "Other"

class UserProfile(models.Model):
    SOURCE_CHOICES = [
        ("online", "Online"),
        ("offline", "Offline"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    phone = models.CharField(max_length=32, unique=True)
    birth_date = models.DateField(null=True, blank=True)

    # === NEW ===
    email_marketing_consent = models.BooleanField(default=False)   # согласие на рассылки
    email_marketing_consented_at = models.DateTimeField(null=True, blank=True)
    how_heard = models.CharField(max_length=32, choices=HowHeard.choices, blank=True)
    notes = models.TextField(blank=True, null=True)
    personal_discount_percent = models.PositiveSmallIntegerField(default=0,
                                                                 help_text="personal client's discount, % (0–100)",
                                                                 validators=[MinValueValidator(0), MaxValueValidator(100)])
    health_conditions = models.JSONField(default=dict, blank=True)
    postal_code = models.CharField(
        max_length=6,
        blank=True,
        help_text="Alberta postal code, 6 chars (e.g. T2X1A1)"
    )
    source = models.CharField(
        max_length=10,
        choices=SOURCE_CHOICES,
        default="online",   # по умолчанию считаем, что онлайн
        editable=False,
    )
    def save(self, *args, **kwargs):
        # Нормализуем индекс (uppercase, без пробелов). Пустое — ок.
        if self.postal_code:
            self.postal_code = clean_ab_postal_code(self.postal_code)
        super().save(*args, **kwargs)

    def health_summary(self) -> str:
        """Короткое суммирующее описание для UI."""
        hc = self.health_conditions or {}
        parts = []
        if hc.get("allergies"): parts.append(f"Allergies: {', '.join(hc['allergies'])}")
        if hc.get("medications"): parts.append(f"Medications: {', '.join(hc['medications'])}")
        if hc.get("chronic_conditions"): parts.append(f"Chronic Conditions: {', '.join(hc['chronic_conditions'])}")
        if hc.get("contraindications"): parts.append(f"Contraindications: {', '.join(hc['contraindications'])}")
        if hc.get("notes"): parts.append(f"Notes: {hc['notes']}")
        return " | ".join(parts) or "—"

    def set_marketing_consent(self, value: bool):
        """Удобный метод: при выставлении True заполнит timestamp, при снятии — очистит."""
        if value and not self.email_marketing_consent:
            self.email_marketing_consent = True
            self.email_marketing_consented_at = timezone.now()
        elif not value and self.email_marketing_consent:
            self.email_marketing_consent = False
            self.email_marketing_consented_at = None

    def get_full_name(self):
        return f"{self.user.get_full_name()}"
    def __str__(self):
        return f"{self.get_full_name()} "

        # ── агрегаты по платежам
    def total_spent_usd(self) -> Decimal:
        """
        Сумма оплаченных визитов (по модели Payment).
        Если у тебя аудит «завершения» идёт по статусу Appointment/PaymentStatus — можно ужесточить фильтры ниже.
        """
        return (
                Payment.objects
                .filter(appointment__client=self)
                # Если хочешь ограничить только оплатами со статусом Paid:
                # .filter(appointment__payment_status__name__iexact="Paid")
                .aggregate(total=Sum("amount"))["total"]
                or Decimal("0")
        )

    @property
    def client_status(self) -> str:
        """
        Ранги:
        1) New Client — если дата регистрации < 30 дней назад
        2) Regular Client — иначе
        3) VIP — если total_spent > 1000
        4) Super VIP — если total_spent > 3000
        Логика приоритетов: финансовые ранги старше календарных.
        """
        spent = self.total_spent_usd()
        if spent >= Decimal("3000"):
            return "Super VIP"
        if spent >= Decimal("1000"):
            return "VIP"

        joined = getattr(self.user, "date_joined", None)
        if joined:
            # date_joined — у auth.User; сравниваем с now()
            return "New Client" if (timezone.now() - joined).days < 30 else "Regular Client"
        return "Regular Client"


class UserRole(models.Model):
    """
    Links a user to a specific role with a timestamp of when the role was assigned.
    """
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'role')

    def __str__(self):
        return f"{self.user} → {self.role.name}"

class ClientSource(models.Model):
    source = models.CharField()

    def __str__(self):
        return f"{self.source}%"


# --- 2. SERVICES ---

class ServiceCategory(models.Model):
    """
    Represents a service offered in the system (e.g., haircut, massage).
    """
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class PrepaymentOption(models.Model):
    """
    Defines available prepayment percentage options.
    """
    percent = models.IntegerField()

    def __str__(self):
        return f"{self.percent}%"

class Service(models.Model):
    """
    Represents a service offered in the system (e.g., haircut, massage).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    category = models.ForeignKey(ServiceCategory, on_delete=models.CASCADE, blank=True, null=True)
    # prepayment_option = models.ForeignKey(PrepaymentOption, on_delete=models.CASCADE, blank=True, null=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_min = models.IntegerField()
    extra_time_min = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return self.name


    def get_active_discount(self):
        today = timezone.now().date()
        return self.discounts.filter(start_date__lte=today, end_date__gte=today).first()

    def get_discounted_price(self):
        """
        Call instead of price to get discounted price or base_price if discount is not set
        :return:
        """
        discount = self.get_active_discount()
        if discount:
            discount_multiplier = Decimal(1) - (Decimal(discount.discount_percent) / Decimal(100))
            return (self.base_price * discount_multiplier).quantize(Decimal('0.01'))
        return self.base_price

class MasterRoom(models.Model):
    """
    Rooms where Master will operate
    """
    room = models.CharField(max_length=20)

    def __str__(self):
        return self.room

class MasterProfile(models.Model):
    """
    Дополнительная информация о мастере: профессия, график работы, цвет и т.д.
    """
    user = models.OneToOneField(UserProfile, on_delete=models.CASCADE, related_name="master_profile")
    profession = models.CharField(max_length=100, blank=True)
    bio = models.TextField(blank=True)
    room = models.ForeignKey(MasterRoom, on_delete=models.CASCADE, blank=True, null=True)

    def __str__(self):
        return f"{self.user.get_full_name()}"
    @property
    def initials(self):
        parts = self.user.get_full_name().strip().split()
        if len(parts) >= 2:
            return parts[0][0] + parts[1][0]
        return self.user.get_full_name()[:2]

class MasterWorkDay(models.Model):
    WEEKDAYS = [
        (0, "Monday"),
        (1, "Tuesday"),
        (2, "Wednesday"),
        (3, "Thursday"),
        (4, "Friday"),
        (5, "Saturday"),
        (6, "Sunday"),
    ]

    master = models.ForeignKey(MasterProfile, on_delete=models.CASCADE, related_name="workdays")
    weekday = models.IntegerField(choices=WEEKDAYS)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        unique_together = ("master", "weekday")
        ordering = ["weekday"]

    def __str__(self):
        return f"{self.get_weekday_display()} {self.start_time}–{self.end_time}"

class ServiceMaster(models.Model):
    """
    Connects a specific service with a master who can perform it.
    """
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    master = models.ForeignKey(MasterProfile, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('service', 'master')   # ← важно
        indexes = [
            models.Index(fields=['master', 'service']),
        ]

    def __str__(self):
        return f"{self.master} → {self.service.name}"

# --- 3. APPOINTMENTS ---

class AppointmentStatus(models.Model):
    """
    Statuses an appointment can have (e.g., Confirmed, Cancelled).
    """
    name = models.CharField(max_length=20)

    def __str__(self):
        return self.name


class PaymentStatus(models.Model):
    """
    Describes the status of a payment (e.g., Paid, Pending).
    """
    name = models.CharField(max_length=20)

    def __str__(self):
        return self.name


class Appointment(models.Model):
    """
    Represents a scheduled appointment between a client and a master for a service.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='appointments_as_client')
    start_time = models.DateTimeField(null=True, blank=True)
    payment_status = models.ForeignKey(PaymentStatus, on_delete=models.CASCADE, default=PaymentStatus.objects.get(name="Not Paid").id)
    final_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, editable=False)
    discount_source = models.CharField(max_length=30, blank=True, default="", editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # Снимок персональной скидки клиента на момент создания
    personal_discount_percent = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        editable=False,
        help_text="Personal discount snapshot at booking time"
    )


    def items_qs(self):
        return self.items.select_related("service", "master__user").all()

    def time_span(self):
        items = list(self.items_qs())
        if not items:
            return None
        starts = [it.start_time for it in items if it.start_time]
        ends = [it.end_time for it in items if it.end_time]
        return (min(starts), max(ends)) if starts and ends else None

    def recompute_totals(self, save=True, *, persist_items=True):
        """
        1) Складываем позиции c учётом позиционных скидок (service/promocode), без персональной.
        2) Применяем персональную скидку ко всей сумме визита.
        3) discount_source визита: агрегируем позиционные источники; 'personal' добавляем 1 раз,
           только если персональная скидка визита > 0.
        """
        from decimal import Decimal
        changed = []
        subtotal = Decimal("0.00")
        item_sources = set()
        item_sources.add("")
        for it in self.items_qs():
            before = (it.final_price, it.discount_source, it.unit_price)
            it._compute_item_pricing()
            if it.final_price is None:
                it.final_price = it.unit_price
            after = (it.final_price, it.discount_source, it.unit_price)
            if after != before:
                changed.append(it)
            subtotal += it.final_price
            # собираем ТОЛЬКО позиционные источники
            if it.discount_source:
                item_sources.add(it.discount_source)
        # агрегированный источник

        self.sync_start_time_from_items(save=True)
        self.final_price = subtotal
        self.discount_source = max(item_sources)
        with transaction.atomic():
            if persist_items and changed:
                type(self).items.rel.related_model.objects.bulk_update(
                    changed, ["final_price", "discount_source", "unit_price"]
        )
        if save:
            super().save(update_fields=["final_price", "discount_source", "start_time"])

    def sync_start_time_from_items(self, *, save: bool = True) -> None:
        """
        Копирует в self.start_time самое раннее start_time среди связанных items.
        Если items нет — ставит None (или можете оставить текущее значение).
        """
        first = self.items.order_by("start_time").first()
        new_start = first.start_time if first else None
        # сохраняем только при изменении, чтобы не трогать updated_at и не триггерить лишние сигналы
        if self.start_time != new_start:
            self.start_time = new_start
            if save:
                self.save(update_fields=["start_time"])

    def total_without_discounts(self, *, ignore_overrides: bool = True) -> Decimal:
        """
        Сумма по визиту БЕЗ скидок.
        ignore_overrides=True  → всегда service.base_price
        ignore_overrides=False → берём unit_price (если задана), иначе service.base_price
        """
        total = Decimal("0.00")
        for it in self.items.select_related("service").all():
            if ignore_overrides:
                total += it.service.base_price
            else:
                # «база позиции»: ручная цена, если стоит; иначе прайс услуги
                total += (it.unit_price if it.unit_price is not None else it.service.base_price)
        return total.quantize(Decimal("0.01"))

    def __str__(self):

        formatted = localtime(self.start_time).strftime("%Y-%m-%d %H:%M")
        return f"{self.client} at {formatted}"

    def _items_qs(self):
        """
        Универсально получаем связанные айтемы (любой related_name).
        """
        if hasattr(self, "items"):
            return self.items.all()
        return self.appointmentitem_set.all()

    def clean(self):

        # 1) Старт времени на уровне Appointment
        if self.start_time and self.start_time.time() > time(23, 59):
            raise ValidationError({"start_time": "Время начала не может быть позже 23:59."})

        # Если нет стартового времени или айтемов – дальше не валидируем
        if not self.start_time:
            return

        items = list(self._items_qs().select_related("service", "master", "appointment"))
        if not items:
            return

        errors = {}

        cancelled_status = AppointmentStatus.objects.filter(name="Cancelled").first()

        # Внутренняя функция проверки одного айтема,
        # почти та же логика, что в AppointmentItem.clean
        def validate_item(it: "AppointmentItem"):
            # старт от Appointment
            start_dt = getattr(it, "start_time", None) or self.start_time
            if not it.master or not it.service or not start_dt:
                return  # пропускаем неполные строки

            extra_min = it.service.extra_time_min or 0
            total_min = (it.service.duration_min or 0) + extra_min
            this_end = start_dt + timedelta(minutes=total_min)

            # Поиск пересечений с чужими AppointmentItem этого же мастера
            overlapping_qs = AppointmentItem.objects.filter(
                master=it.master,
                appointment__start_time__lt=this_end,
                appointment__start_time__gte=start_dt - timedelta(hours=3),
            )

            # исключаем все айтемы текущего Appointment
            if self.pk:
                overlapping_qs = overlapping_qs.exclude(appointment=self)

            if cancelled_status:
                overlapping_qs = overlapping_qs.exclude(
                    appointment__appointmentstatushistory__status=cancelled_status
                )

            for other in overlapping_qs.select_related("service", "appointment"):
                other_start = other.appointment.start_time if other.appointment else None
                if not other_start:
                    continue
                other_extra = (other.service.extra_time_min or 0) if other.service else 0
                other_total = (other.service.duration_min or 0) + other_extra
                other_end = other_start + timedelta(minutes=other_total)

                if start_dt < other_end and this_end > other_start:
                    # Копим ошибку на поле start_time
                    errors.setdefault("start_time", []).append(
                        f"Overlap for master {getattr(it.master, 'display_name', it.master)} "
                        f"with another appointment."
                    )
                    break

            # Проверка окна работы мастера
            master_profile = getattr(it.master, "master_profile", None)
            if master_profile:
                local_start_dt = localtime(start_dt)
                local_end_dt = local_start_dt + timedelta(minutes=total_min)

                weekday = local_start_dt.weekday()
                workday = master_profile.workdays.filter(weekday=weekday).first()
                if not workday:
                    errors.setdefault("start_time", []).append(
                        f"У мастера {getattr(it.master, 'display_name', it.master)} нет рабочих часов на "
                        f"{local_start_dt.strftime('%A')}."
                    )
                    return

                work_start_dt = local_start_dt.replace(
                    hour=workday.start_time.hour, minute=workday.start_time.minute,
                    second=0, microsecond=0,
                )
                work_end_dt = local_start_dt.replace(
                    hour=workday.end_time.hour, minute=workday.end_time.minute,
                    second=0, microsecond=0,
                )

                if work_end_dt <= work_start_dt:
                    work_end_dt += timedelta(days=1)
                    if local_end_dt <= work_start_dt:
                        local_end_dt += timedelta(days=1)
                    if local_start_dt <= work_start_dt:
                        local_start_dt += timedelta(days=1)

                if local_start_dt < work_start_dt:
                    errors.setdefault("start_time", []).append(
                        f"Start time ({local_start_dt.strftime('%H:%M')}) earlier than master's shift start "
                        f"({work_start_dt.strftime('%H:%M')}) "
                        f"для мастера {getattr(it.master, 'display_name', it.master)}."
                    )

                if local_end_dt > work_end_dt:
                    errors.setdefault("start_time", []).append(
                        f"The appointment ends at ({local_end_dt.strftime('%H:%M')}) later than master's end of shift "
                        f"({work_end_dt.strftime('%H:%M')}) "
                        f"для мастера {getattr(it.master, 'display_name', it.master)}."
                    )

        # Прогоняем все айтемы текущего Appointment
        for it in items:
            validate_item(it)

        if errors:
            # Django сам склеит списки ошибок в читаемый вид
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        creating = self._state.adding
        if creating and self.client_id and self.personal_discount_percent == 0:
            # «Замораживаем» персональную скидку клиента в момент создания
            p = int(getattr(self.client, "personal_discount_percent", 0) or 0)
            self.personal_discount_percent = max(0, min(100, p))

        super().save(*args, **kwargs)

class CancellationReason(models.Model):
    """
    Справочник причин отмены записи
    """
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class AppointmentItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="items")
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    master = models.ForeignKey(MasterProfile, on_delete=models.CASCADE, related_name="appointment_items")

    # Время начала именно этой услуги
    start_time = models.DateTimeField()

    # Базовая цена позиции на момент записи (может быть вручную переопределена в админке)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0'))], null=True, blank=True)
    unit_price_overridden = models.BooleanField(default=False, help_text="Manually set in admin")

    # Итог позиции после позиционных скидок (service/promocode). Персональная НЕ учитывается!
    final_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, editable=False)
    discount_source = models.CharField(max_length=30, blank=True, default="", editable=False)  # '', 'service', 'promocode'

    class Meta:
        indexes = [models.Index(fields=["master", "start_time"])]
    def __str__(self):
        return f"{self.appointment.client} for {self.service} at {self.start_time}"
    @property
    def duration_min(self) -> int:
        extra = self.service.extra_time_min or 0
        return (self.service.duration_min or 0) + extra

    @property
    def end_time(self):
        return self.start_time + timedelta(minutes=self.duration_min)

    @staticmethod
    def _to_decimal(val):
        if val in (None, ""):
            return None
        if isinstance(val, Decimal):
            return val
        try:
            return Decimal(str(val))
        except (InvalidOperation, TypeError, ValueError):
            return None

    def _effective_unit_price(self) -> Decimal:
        """
        Возвращает базовую цену позиции как Decimal.
        Если руками не задано (или задано '0' / ''), берём Service.base_price.
        Никогда не возвращает строку.
        """
        price = self._to_decimal(self.unit_price)
        if price is None or price == Decimal("0"):
            # берём цену услуги; это уже Decimal, но прогоним через конвертер для надёжности
            price = self._to_decimal(getattr(self.service, "base_price", None))
            # не считаем это ручной правкой
            if price is not None:
                self.unit_price = price
        return price or Decimal("0.00")

    def _compute_item_pricing(self):
        """
        Считает цену позиции с учётом:
          • скидки услуги или промокода (берём максимум)
          • персональной скидки клиента (поверх остальных)
        """
        promocode_link = getattr(self, "promocode_link", None)
        promocode = getattr(promocode_link, "promocode", None)

        base = self._effective_unit_price()  # Decimal

        service_disc = 0
        disc = self.service.get_active_discount()
        if disc:
            service_disc = int(disc.discount_percent)
        promo_disc = 0
        if promocode and promocode.is_valid_for(self.service):
            promo_disc = int(promocode.discount_percent)
        # сначала применяем скидку услуги/промокода
        price = base * (Decimal(100) - Decimal(promo_disc)) / Decimal(100)
        price = price * (Decimal(100) - Decimal(service_disc)) / Decimal(100)
        # потом — персональную скидку клиента
        personal_pct = 0
        if self.appointment and self.appointment.client:
            personal_pct = int(self.appointment.client.personal_discount_percent or 0)

        if personal_pct:
            price = price * (Decimal(100) - Decimal(personal_pct)) / Decimal(100)
        # финальная цена
        self.final_price = price.quantize(Decimal("0.01"))
        # источник скидки
        if service_disc == 0 and personal_pct == 0 and promo_disc == 0:
            self.discount_source = ""
        elif promo_disc > 0 and personal_pct > 0 and service_disc:
            self.discount_source = "promocode+personal+service"
        elif service_disc > 0 and personal_pct > 0:
            self.discount_source = "service+personal"
        elif promo_disc > 0 and personal_pct > 0:
            self.discount_source = "promocode+personal"
        elif service_disc > 0:
            self.discount_source = "service"
        elif promo_disc > 0:
            self.discount_source = "promocode"
        else:
            self.discount_source = "personal"


    # Удобный хелпер: берём реальный старт из self.start_time (или из appointment.start_time, если нет)
    def _resolve_start_dt(self):
        if getattr(self, "start_time", None):
            return self.start_time
        appt = getattr(self, "appointment", None)
        return getattr(appt, "start_time", None)

    def clean(self):
        # === 0) Базовые вычисления: старт/длительность/конец ===
        start_dt = self._resolve_start_dt()

        # Хард-стоп по времени суток
        if start_dt and start_dt.time() > time(23, 59):
            raise ValidationError({"start_time": "Время начала не может быть позже 23:59."})

        # До ключевых атрибутов — выходим тихо
        if not self.master or not self.service or not start_dt:
            return

        extra_min = self.service.extra_time_min or 0
        total_min = (self.service.duration_min or 0) + extra_min
        this_end = start_dt + timedelta(minutes=total_min)

        # === 1) Пересечения для этого мастера по предметному времени (AppointmentItem.start_time) ===
        # Исключаем отменённые аппы (если статус «Cancelled» существует)
        cancelled_status = apps.get_model(self._meta.app_label, "AppointmentStatus").objects.filter(name="Cancelled").first()

        overlapping_qs = type(self).objects.filter(
            master=self.master,
            start_time__lt=this_end,
            start_time__gt=start_dt - timedelta(hours=24),  # «окно» поиска (с запасом на смены через полночь)
        )
        if self.pk:
            overlapping_qs = overlapping_qs.exclude(pk=self.pk)
        if cancelled_status:
            overlapping_qs = overlapping_qs.exclude(
                appointment__appointmentstatushistory__status=cancelled_status
            )

        # Фактическое пересечение по интервалам item'ов
        for other in overlapping_qs.select_related("service", "appointment"):
            if not other.start_time:
                continue
            other_extra = (other.service.extra_time_min or 0) if other.service else 0
            other_total = (other.service.duration_min or 0) + other_extra
            other_end = other.start_time + timedelta(minutes=other_total)

            if start_dt < other_end and this_end > other.start_time:
                raise ValidationError({
                    "start_time": "Этот слот пересекается с другим приёмом у того же мастера."
                })

        # === 2) Проверка рабочего окна мастера (MasterProfile.workdays[weekday]: start_time..end_time) ===
        # master может быть либо MasterProfile, либо User с related master_profile
        master_profile = getattr(self.master, "master_profile", None) or self.master
        workdays_qs = getattr(master_profile, "workdays", None)

        if workdays_qs is not None:
            local_start_dt = localtime(start_dt)
            local_end_dt = local_start_dt + timedelta(minutes=total_min)

            weekday = local_start_dt.weekday()  # 0 = Пн
            workday = workdays_qs.filter(weekday=weekday).first()
            if not workday:
                raise ValidationError({"start_time": f"У мастера нет рабочих часов на {local_start_dt.strftime('%A')}."})

            work_start_dt = local_start_dt.replace(
                hour=workday.start_time.hour, minute=workday.start_time.minute, second=0, microsecond=0
            )
            work_end_dt = local_start_dt.replace(
                hour=workday.end_time.hour, minute=workday.end_time.minute, second=0, microsecond=0
            )

            # Смена через полночь
            if work_end_dt <= work_start_dt:
                work_end_dt += timedelta(days=1)
                # Подтянем и интервал визита, если он «до» смены
                if local_end_dt <= work_start_dt:
                    local_end_dt += timedelta(days=1)
                if local_start_dt <= work_start_dt:
                    local_start_dt += timedelta(days=1)

            if local_start_dt < work_start_dt:
                raise ValidationError({
                    "start_time": (
                        f"Старт ({local_start_dt.strftime('%H:%M')}) раньше начала смены мастера "
                        f"({work_start_dt.strftime('%H:%M')})."
                    )
                })
            if local_end_dt > work_end_dt:
                raise ValidationError({
                    "start_time": (
                        f"Окончание ({local_end_dt.strftime('%H:%M')}) позже конца смены мастера "
                        f"({work_end_dt.strftime('%H:%M')})."
                    )
                })

        # === 3) Кабинет: два мастера не могут работать в одном кабинете одновременно ===
        # Ищем «room» на master_profile или прямо на item/appointment (под разные схемы)
        room = getattr(master_profile, "room", None)
        if room is None:
            room = getattr(self, "room", None)
        if room is None:
            room = getattr(getattr(self, "appointment", None), "room", None)

        if room is not None:
            room_overlap_qs = type(self).objects.filter(
                # любой мастер, но тот же кабинет
                start_time__lt=this_end,
                start_time__gt=start_dt - timedelta(hours=24),
            )
            # фильтрация по «room» — где бы он ни лежал
            # 1) room на item:
            try:
                room_overlap_qs = room_overlap_qs.filter(room=room)
                room_on_item = True
            except Exception:
                room_on_item = False

            # 2) room на master_profile:
            if not room_on_item:
                try:
                    room_overlap_qs = room_overlap_qs.filter(master__master_profile__room=room)
                except Exception:
                    # 3) room прямо на master:
                    try:
                        room_overlap_qs = room_overlap_qs.filter(master__room=room)
                    except Exception:
                        # 4) room на appointment:
                        try:
                            room_overlap_qs = room_overlap_qs.filter(appointment__room=room)
                        except Exception:
                            room_overlap_qs = None  # поле не найдено — пропустим проверку

            if room_overlap_qs is not None:
                if self.pk:
                    room_overlap_qs = room_overlap_qs.exclude(pk=self.pk)
                if cancelled_status:
                    room_overlap_qs = room_overlap_qs.exclude(
                        appointment__appointmentstatushistory__status=cancelled_status
                    )

                for other in room_overlap_qs.select_related("service", "appointment", "master"):
                    if not other.start_time:
                        continue
                    other_extra = (other.service.extra_time_min or 0) if other.service else 0
                    other_total = (other.service.duration_min or 0) + other_extra
                    other_end = other.start_time + timedelta(minutes=other_total)
                    if start_dt < other_end and this_end > other.start_time:
                        raise ValidationError({
                            "start_time": "В этом кабинете уже есть запись на это время."
                        })

        # === 4) Недоступность мастера (time off / vacation / blocked) ===
        # Поддержим несколько возможных имён модели и полей, чтобы не «падать», если схема немного отличается.
        timeoff_model = None
        for model_name in ("MasterAvailability", "MasterTimeOff", "MasterBlock", "MasterAbsence"):
            try:
                timeoff_model = apps.get_model(self._meta.app_label, model_name)
                if timeoff_model is not None:
                    break
            except LookupError:
                continue

        if timeoff_model is not None:
            # Базовый фильтр пересечения интервалов
            to_qs = timeoff_model.objects.filter(
                master=self.master,  # если master в той модели другой (MasterProfile/User) — при необходимости подправьте
                start_time__lt=this_end,
                end_time__gt=start_dt,
            )

            # Если в модели есть флаг/тип «time off» — отфильтруем только недоступность
            timeoff_field_names = {f.name for f in timeoff_model._meta.get_fields()}
            # Частые варианты: is_time_off(True), is_working(False), kind in ('time_off','vacation','blocked')
            if "is_time_off" in timeoff_field_names:
                to_qs = to_qs.filter(is_time_off=True)
            elif "is_working" in timeoff_field_names:
                to_qs = to_qs.filter(is_working=False)
            elif "kind" in timeoff_field_names:
                to_qs = to_qs.filter(kind__in=["time_off", "vacation", "blocked"])

            if to_qs.exists():
                raise ValidationError({
                    "start_time": "Мастер недоступен на выбранный интервал (time off/vacation/blocked)."
                })

    def save(self, *args, **kwargs):
        # Старт по умолчанию — «конвейером»: после последней позиции, иначе — от якоря визита
        if not self.start_time:
            last = self.appointment.items.exclude(pk=self.pk).order_by('-start_time').first()
            self.start_time = (last.end_time if last else self.appointment.start_time)
        # Если руками поменяли unit_price — помечаем
        if self.unit_price is not None and 'update_fields' in kwargs:
            if 'unit_price' in (kwargs.get('update_fields') or []):
                self.unit_price_overridden = True

        # Пересчёт позиционной цены (service/promocode)
        # self._compute_item_pricing()
        super().save(*args, **kwargs)



class AppointmentStatusHistory(models.Model):
    """
    Tracks status changes for appointments, including who made the change and when.
    """
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE)
    status = models.ForeignKey(AppointmentStatus, on_delete=models.CASCADE)
    set_by = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    set_at = models.DateTimeField(auto_now_add=True)

    cancellation_reason = models.ForeignKey(
        "CancellationReason",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        help_text="Reason for cancelling if status is 'Cancelled'"
    )

# --- 4. PAYMENTS ---

class PaymentMethod(models.Model):
    """
    Represents a method of payment (e.g., Credit Card, Cash).
    """
    name = models.CharField(max_length=20)

    def __str__(self):
        return self.name


class Payment(models.Model):
    """
    Stores payment records for appointments.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.ForeignKey(PaymentMethod, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

# --- 5. PREPAYMENTS ---


class AppointmentPrepayment(models.Model):
    """
    Links a prepayment option to a specific appointment.
    """
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE)
    option = models.ForeignKey(PrepaymentOption, on_delete=models.CASCADE)

# --- 6. FILES ---

class ClientFile(models.Model):
    """
    Represents a file uploaded for a user, such as a document or image.
    """
    USER = 'user'
    ADMIN = 'admin'

    OWNER_CHOICES = [
        (USER, 'User'),
        (ADMIN, 'Admin'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    file = models.FileField(upload_to='client_files/', storage=S3Boto3Storage()) # stored in S3!
    file_type = models.CharField(max_length=50, editable=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.CharField(
        max_length=10,
        choices=OWNER_CHOICES,
        default=USER,
        help_text="Who uploaded the file: admin or user"
    )

    description = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional description (e.g., 'Form before procedure')"
    )
    def save(self, *args, **kwargs):
        if self.file and not self.file_type:
            name, extension = os.path.splitext(self.file.name)
            self.file_type = extension.lower().lstrip('.')  # без точки
        super().save(*args, **kwargs)

# --- 7. NOTIFICATIONS ---


class Notification(models.Model):
    """
    Represents a notification sent to a user regarding an appointment.
    Supports email and SMS channels.
    """
    REM_D = "reminder_days"
    REM_H  = "reminder_hours"
    OTHER   = "other"
    CREATED = "created"
    UPDATED = "updated"
    CANCELLED = "cancelled"
    STATUS  = "status"      # смена статуса (в т.ч. Cancelled)

    KIND_CHOICES = [
        (REM_D, "Reminder Days"),
        (REM_H,  "Reminder Hours"),
        (CREATED, "Appointment created"),
        (UPDATED, "Appointment updated"),
        (CANCELLED, "Appointment cancelled"),
        (STATUS,  "Appointment status changed"),
        (OTHER,   "Other"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    appointment = models.ForeignKey(Appointment, on_delete=models.SET_NULL, null=True, blank=True)
    channel = models.CharField(max_length=10, choices=[('email', 'Email'), ('sms', 'SMS')])
    kind = models.CharField(max_length=32, choices=KIND_CHOICES, default=OTHER)

    message = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)

    # Новые поля для учёта отправок
    provider = models.CharField(max_length=32, default="sendgrid", blank=True)
    provider_message_id = models.CharField(max_length=128, blank=True, default="")
    status = models.CharField(max_length=20, default="sent")  # sent | failed
    error = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            # Не допускаем дубликатов напоминаний одного вида для одной записи
            models.UniqueConstraint(
                fields=["appointment", "kind", "channel"],
                name="uniq_notification_per_kind_channel",
                condition=~models.Q(kind="updated"),
            )
        ]

    def __str__(self):
        return f"{self.get_kind_display()} → {self.user} ({self.channel})"

class ReminderSchedule(models.Model):
    """
    Global reminder rule you can manage in Admin.
    Example: 2 days before, or 3 hours before.
    """
    UNIT_HOURS = "hours"
    UNIT_DAYS  = "days"
    UNIT_CHOICES = [
        (UNIT_HOURS, "Hours"),
        (UNIT_DAYS,  "Days"),
    ]

    name = models.CharField(max_length=64, help_text="Visible name, e.g. '48h' or '3 hours before'")
    is_active = models.BooleanField(default=True)

    offset_amount = models.PositiveIntegerField(help_text="How many hours/days before start")
    offset_unit   = models.CharField(max_length=8, choices=UNIT_CHOICES, default=UNIT_HOURS)

    # E-mail presentation
    email_subject = models.CharField(max_length=200, default="Appointment reminder")
    email_template = models.CharField(
        max_length=200,
        default="email/appointment_reminder.html",
        help_text="Django template path"
    )

    # Optional: unique marker to guarantee idempotency (used in Notification.message prefix)
    slug = models.SlugField(max_length=64, unique=True, help_text="Used for deduplication, e.g. 'rem-48h'")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_active", "offset_unit", "offset_amount", "name"]

    def __str__(self):
        unit = "h" if self.offset_unit == self.UNIT_HOURS else "d"
        return f"{self.name} ({self.offset_amount}{unit})"

    def get_timedelta(self):
        from datetime import timedelta
        if self.offset_unit == self.UNIT_DAYS:
            return timedelta(days=self.offset_amount)
        return timedelta(hours=self.offset_amount)

    def remaining_label(self):
        # Human label like "2 days" or "3 hours"
        unit = "day" if self.offset_unit == self.UNIT_DAYS else "hour"
        n = self.offset_amount
        return f"{n} {unit}{'' if n == 1 else 's'}"

# --- 8. MASTERS ---


class MasterAvailability(models.Model):
    VACATION = 'vacation'
    LUNCH = 'lunch'
    BREAK = 'break'

    REASON_CHOICES = [
        (VACATION, 'Vacation'),
        (LUNCH, 'Lunch'),
        (BREAK, 'Break'),
    ]

    master = models.ForeignKey(MasterProfile, on_delete=models.CASCADE)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    reason = models.CharField(
        max_length=20,
        choices=REASON_CHOICES,
        default=VACATION,
        help_text="Reason for time off"
    )

    class Meta:
        verbose_name = "Time Off / Vacation"
        verbose_name_plural = "Time Offs / Vacations"

    def __str__(self):
        return f"{self.master} → {self.get_reason_display()} from {self.start_time} to {self.end_time}"

    def clean(self):
        super().clean()

        if not self.master or not self.start_time or not self.end_time:
            return  # нечего валидировать без ключевых полей

        cancelled = AppointmentStatus.objects.filter(name__iexact="Cancelled").first()

        # Последний статус для ВСТРЕЧИ (важно: связываем по appointment_id у item)
        last_status_sq = (
            AppointmentStatusHistory.objects
            .filter(appointment_id=OuterRef("appointment_id"))
            .order_by("-set_at")
            .values("status_id")[:1]
        )

        # Берём ITEMS данного мастера, чьи встречи попадают в окно
        base_qs = (
            AppointmentItem.objects
            .select_related("appointment")  # чтобы брать start_time без доп. запросов
            .annotate(last_status=Subquery(last_status_sq))
            .filter(
                master=self.master,
                appointment__start_time__lt=self.end_time,
                appointment__start_time__gte=self.start_time - timedelta(hours=3),
            )
        )
        if cancelled:
            base_qs = base_qs.exclude(last_status=cancelled.id)

        # Забираем для каждой найденной встречи все её items (с сервисом и мастером),
        # чтобы посчитать суммарную длительность окна встречи.
        items = base_qs.prefetch_related(
            Prefetch(
                "appointment__items",
                queryset=AppointmentItem.objects.select_related("service", "master"),
                to_attr="prefetched_items",
            )
        )

        # Соберём уникальные встречи из найденных items
        seen_appt_ids = set()
        for it in items:
            appt = it.appointment
            if appt is None or appt.id in seen_appt_ids:
                continue
            seen_appt_ids.add(appt.id)

            # Суммарная длительность встречи = сумма duration_min по всем её items
            total_min = 0
            for appt_item in getattr(appt, "prefetched_items", []) or []:
                srv = getattr(appt_item, "service", None)
                dur = getattr(srv, "duration_min", None) if srv else None
                if isinstance(dur, int) and dur > 0:
                    qty = getattr(appt_item, "quantity", 1) or 1
                    total_min += dur * qty

            # fall-back на старые данные (если почему-то нет items/длительностей)
            if total_min <= 0:
                srv = getattr(appt, "service", None)  # если поле у Appointment ещё есть
                dur = getattr(srv, "duration_min", None) if srv else None
                if isinstance(dur, int) and dur > 0:
                    total_min = dur

            appt_end = appt.start_time + timedelta(minutes=total_min or 0)

            # Пересечение интервалов: [self.start_time, self.end_time] vs [appt.start_time, appt_end]
            if self.start_time < appt_end and self.end_time > appt.start_time:
                raise ValidationError({
                    "start_time": "Vacations are overlapping with existing Appointments",
                })


class ClientReview(models.Model):
    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.CASCADE,
        related_name='review',
        help_text="One review per one appointment"
    )
    rating = models.PositiveSmallIntegerField(
        choices=[(i, f"{i} ★") for i in range(1, 6)],
        help_text="Rating 1 to 5"
    )
    comment = models.TextField(blank=True, help_text="Not obligatory text comment")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Review {self.rating}★ for {self.appointment}"

    class Meta:
        verbose_name = "Client Review"
        verbose_name_plural = "Client Reviews"


class ServiceDiscount(models.Model):
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='discounts')
    discount_percent = models.PositiveIntegerField(help_text="Percent of discount")
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        verbose_name = "Service Discount"
        verbose_name_plural = "Service Discounts"
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.discount_percent}% off on {self.service.name} ({self.start_date} – {self.end_date})"

    def is_active(self):
        today = timezone.now().date()
        return self.start_date <= today <= self.end_date


class PromoCode(models.Model):
    code = models.CharField(max_length=20, unique=True)
    discount_percent = models.PositiveIntegerField(help_text="discount in percents(0-100)")
    active = models.BooleanField(default=True)
    start_date = models.DateField()
    end_date = models.DateField()
    applicable_services = models.ManyToManyField(Service, blank=True, help_text="leave empty to apply to all services")

    def is_valid_for(self, service, today=None):
        today = today or timezone.now().date()
        return (
                self.active and
                self.start_date <= today <= self.end_date and
                (self.applicable_services.count() == 0 or self.applicable_services.filter(pk=service.pk).exists())
        )

    def __str__(self):
        return self.code

class AppointmentItemPromoCode(models.Model):
    item = models.OneToOneField(AppointmentItem, on_delete=models.CASCADE, related_name="promocode_link")
    promocode = models.ForeignKey(PromoCode, on_delete=models.CASCADE)
    # Админ может «пробить» промокод поверх скидки услуги
    force_apply = models.BooleanField(default=False, help_text="Allow promo even if service discount is active")

    @property
    def appointment(self):
        return self.item.appointment  # ✅ даст совместимость со старым кодом
    def clean(self):
        today = timezone.now().date()
        if not self.promocode.active or self.promocode.start_date > today or self.promocode.end_date < today:
            raise ValidationError({"promocode": "Промокод не активен."})
        if not self.promocode.is_valid_for(self.item.service):
            raise ValidationError({"promocode": "Промокод неприменим к выбранной услуге."})

        disc = self.item.service.get_active_discount()
        if disc and int(disc.discount_percent) > 0 and not self.force_apply:
            # клиентам нельзя; админ в админке проставляет force_apply=True
            raise ValidationError({"promocode": "Для услуги действует скидка. Клиент не может применить промокод."})

def get_effective_discount_percent(service: Service, client: UserProfile | None, promocode: PromoCode | None = None) -> int:
    """
    Возвращает максимальный процент скидки из:
    - активной скидки на услугу (ServiceDiscount)
    - персональной скидки клиента (UserProfile.personal_discount_percent)
    - промокода (если передан и валиден)
    """
    percents = [0]

    # скидка на услугу
    disc = service.get_active_discount()
    if disc:
        percents.append(int(disc.discount_percent))

    # персональная скидка клиента
    if client and client.personal_discount_percent:
        percents.append(int(client.personal_discount_percent))

    # промокод (опционально)
    if promocode:
        percents.append(int(promocode.discount_percent))

    return max(percents)


def get_price_for(service: Service, client: UserProfile | None, promocode: PromoCode | None = None) -> Decimal:
    """
    Итоговая цена для клиента с учётом лучшего источника скидки.
    """
    base = service.base_price
    best = Decimal(get_effective_discount_percent(service, client, promocode))
    price = (base * (Decimal(100) - best) / Decimal(100)).quantize(Decimal("0.01"))
    return price

def detect_discount_source(service, client, promocode):
    """Возвращает строку-источник: 'personal' | 'promocode' | 'service' | ''"""
    # проценты по источникам
    # скидка услуги
    disc = service.get_active_discount()
    s = int(getattr(disc, "discount_percent", 0) or 0)
    # персональная
    p = int(getattr(client, "personal_discount_percent", 0) or 0)
    # промокод
    pr = int(getattr(promocode, "discount_percent", 0) or 0)

    general = max(s, pr)
    if p > general:
        return "personal"
    if pr >= s and pr > 0:
        return "promocode"
    if s > 0:
        return "service"
    return ""