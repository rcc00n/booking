from decimal import Decimal

from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.contrib.auth.models import User
import uuid
from django.core.exceptions import ValidationError
from datetime import timedelta, time
import os

from django.db.models import OuterRef, Subquery, Sum
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
        ("online", "Online (self-registered)"),
        ("offline", "Offline (created by admin)"),
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
    master = models.ForeignKey(MasterProfile, on_delete=models.CASCADE, related_name='appointments_as_master')
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    start_time = models.DateTimeField()
    payment_status = models.ForeignKey(PaymentStatus, on_delete=models.CASCADE)
    final_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, editable=False)
    discount_source = models.CharField(max_length=20, blank=True, default="", editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):

        formatted = localtime(self.start_time).strftime("%Y-%m-%d %H:%M")
        return f"{self.client} for {self.service} at {formatted}"

    def clean(self):
        if self.start_time and self.start_time.time() > time(23, 59):
            raise ValidationError({
                "start_time": "Время начала не может быть позже 23:59."
            })

        # Остальная логика…
        if not self.master or not self.service or not self.start_time:
            return

        cancelled_status = AppointmentStatus.objects.filter(name="Cancelled").first()
        # Проверка на пересечение с другими записями
        overlapping = Appointment.objects.filter(
            master=self.master,
            start_time__lt=self.start_time + timedelta(minutes=self.service.duration_min),
            start_time__gte=self.start_time - timedelta(hours=3)
        ).exclude(id=self.id)

        overlapping = overlapping.exclude(
            appointmentstatushistory__status=cancelled_status
        )

        this_end = self.start_time + timedelta(minutes=self.service.duration_min)
        for appt in overlapping:
            other_end = appt.start_time + timedelta(minutes=appt.service.duration_min)
            if self.start_time < other_end and this_end > appt.start_time:
                raise ValidationError({
                    "start_time": "This appointment overlaps with another appointment for the same master."
                })

            # --- 🔒 Проверка пересечения по комнате ---
        master_profile = getattr(self.master, "master_profile", None)

        if master_profile and self.start_time:
            local_start_dt = localtime(self.start_time)

        # длительность услуги
            extra_min = self.service.extra_time_min or 0
            total_minutes = self.service.duration_min + extra_min
            local_end_dt = local_start_dt + timedelta(minutes=total_minutes)

            weekday = local_start_dt.weekday()  # 0=Пн, 6=Вс
            workday = master_profile.workdays.filter(weekday=weekday).first()

            if not workday:
                raise ValidationError({
                    "start_time": f"У мастера нет рабочих часов на {local_start_dt.strftime('%A')}."
                })

            # строим datetime начала/конца рабочего окна
            work_start_dt = local_start_dt.replace(
                hour=workday.start_time.hour,
                minute=workday.start_time.minute,
                second=0,
                microsecond=0,
            )
            work_end_dt = local_start_dt.replace(
                hour=workday.end_time.hour,
                minute=workday.end_time.minute,
                second=0,
                microsecond=0,
            )

            # поддержка "через полночь"
            if work_end_dt <= work_start_dt:
                work_end_dt += timedelta(days=1)
                if local_end_dt <= work_start_dt:
                    local_end_dt += timedelta(days=1)
                if local_start_dt <= work_start_dt:
                    local_start_dt += timedelta(days=1)

                # 1) старт раньше начала смены
            if local_start_dt < work_start_dt:
                raise ValidationError({
                    "start_time": f"Start time ({local_start_dt.strftime('%H:%M')}) earlier than masters shift starts git st "
                                  f"({work_start_dt.strftime('%H:%M')})."
            })

            # 2) конец позже конца смены
            if local_end_dt > work_end_dt:
                raise ValidationError({
                    "start_time": f"The appointment ends at ({local_end_dt.strftime('%H:%M')}) which is later then master's end of shift "
                                  f"({work_end_dt.strftime('%H:%M')})."
                })

class CancellationReason(models.Model):
    """
    Справочник причин отмены записи
    """
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

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
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    appointment = models.ForeignKey(Appointment, on_delete=models.SET_NULL, null=True, blank=True)
    channel = models.CharField(max_length=10, choices=[('email', 'Email'), ('sms', 'SMS')])
    message = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        """
        Triggers message sending based on the selected channel (email or SMS).
        """
        is_new = self._state.adding
        super().save(*args, **kwargs)

        if is_new:
            if self.channel == 'email':
                self.send_email()
            elif self.channel == 'sms':
                self.send_sms()

    def send_email(self):
        """
        Stub: logic to send an email message to the user.
        """
        print(f"[EMAIL] To {self.user}: {self.message}")

    def send_sms(self):
        """
        Stub: logic to send an SMS message to the user.
        """
        print(f"[SMS] To {self.user}: {self.message}")

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
            return  # Не валидируем, если что-то не заполнено
        cancelled = AppointmentStatus.objects.filter(name__iexact="Cancelled").first()

        # Найдём все записи мастера, которые пересекаются с отпуском
        if cancelled:
            last_status = (
                AppointmentStatusHistory.objects
                .filter(appointment=OuterRef("pk"))
                .order_by("-set_at")
                .values("status_id")[:1]
            )

            overlapping_appointments = (
                Appointment.objects
                .annotate(last_status=Subquery(last_status))
                .filter(
                    master=self.master,
                    start_time__lt=self.end_time,
                    start_time__gte=self.start_time - timedelta(hours=3),
                )
                .exclude(last_status=cancelled.id)  # убираем отменённые
            )
        else:
            overlapping_appointments = Appointment.objects.filter(
                master=self.master,
                start_time__lt=self.end_time,
                start_time__gte=self.start_time - timedelta(hours=3),
            )

        for appt in overlapping_appointments:
            appt_end = appt.start_time + timedelta(minutes=appt.service.duration_min)
            if self.start_time < appt_end and self.end_time > appt.start_time:
                raise ValidationError({
                    "start_time": "Vacation overlaps with existing appointments",
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

class AppointmentPromoCode(models.Model):
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name="promocodes")
    promocode = models.ForeignKey(PromoCode, on_delete=models.CASCADE)

    def clean(self):
        if self.promocode.end_date < timezone.now().date():
            raise ValidationError({
                "promocode": "This promocode is expired."
            })
        now = timezone.now()
        discounts = ServiceDiscount.objects.filter(
            service=self.appointment.service,
            start_date__lte=now,
            end_date__gte=now
        ).exists()
        if discounts:
            raise ValidationError({
                "promocode": "This Service already has a discount. Promocode can't be applied"
            })

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