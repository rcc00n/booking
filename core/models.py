from decimal import Decimal, InvalidOperation
from functools import lru_cache

from django.apps import apps
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import connection, models, transaction
from django.db.utils import OperationalError, ProgrammingError
from django.contrib.auth.models import User
import uuid
from django.core.exceptions import ValidationError
from datetime import datetime, timedelta, time
import os
from importlib import import_module

from django.db.models import (
    OuterRef,
    Subquery,
    Sum,
    Prefetch,
    F,
    Q,
    Case,
    When,
    Value,
    IntegerField,
    Exists,
)
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.timezone import localtime
from core.validators import clean_phone, clean_ab_postal_code, validate_service_is_active
from django.conf import settings

from storages.backends.s3boto3 import S3Boto3Storage
from django.utils.text import slugify

from core.utils.tax import compute_tax
from core.utils.fees import card_processing_fee


TWOPLACES = Decimal("0.01")

def service_image_upload_to(instance, filename: str) -> str:
    """
    Deterministic upload path per service to avoid leftovers on S3/local storage.
    """
    base, ext = os.path.splitext(filename)
    normalized = slugify(base) or "image"
    ext = ext.lower() or ".jpg"
    service_id = instance.pk or uuid.uuid4()
    return f"services/{service_id}/{normalized}{ext}"
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

class UserProfileQuerySet(models.QuerySet):
    def create(self, **kwargs):
        """
        Ensure uniqueness on user by updating the existing profile when callers
        attempt to create a second one for the same auth user (signals/tests).
        """
        user = kwargs.get("user")
        if user is None:
            return super().create(**kwargs)

        existing = self.filter(user=user).first()
        if existing:
            for field, value in kwargs.items():
                if field == "user":
                    continue
                setattr(existing, field, value)
            existing.save(using=self.db)
            return existing

        return super().create(**kwargs)


class UserProfileManager(models.Manager.from_queryset(UserProfileQuerySet)):
    pass


class UserProfile(models.Model):
    SOURCE_CHOICES = [
        ("online", "Online"),
        ("offline", "Offline"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    phone = models.CharField(max_length=32, unique=True, null=True, blank=True, default=None)
    birth_date = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True)

    # === NEW ===
    email_marketing_consent = models.BooleanField(default=False)   # согласие на рассылки
    email_marketing_consented_at = models.DateTimeField(null=True, blank=True)
    how_heard = models.CharField(max_length=32, choices=HowHeard.choices, blank=True)
    notes = models.TextField(blank=True, null=True)
    personal_discount_percent = models.PositiveSmallIntegerField(default=0,
                                                                 help_text="personal client's discount, % (0–100)",
                                                                 validators=[MinValueValidator(0), MaxValueValidator(100)])
    health_conditions = models.JSONField(default=dict, blank=True)
    billing_contact = models.JSONField(default=dict, blank=True)
    billing_contact_updated_at = models.DateTimeField(null=True, blank=True)
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
    stripe_customer_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Stripe Customer ID for billing integrations.",
        db_index=True,
    )
    email_verified_at = models.DateTimeField(null=True, blank=True)

    objects = UserProfileManager()

    def save(self, *args, **kwargs):
        # Нормализуем индекс (uppercase, без пробелов). Пустое — ок.
        if self.phone == "":
            self.phone = None
        if self.postal_code:
            self.postal_code = clean_ab_postal_code(self.postal_code)
        if self.stripe_customer_id:
            self.stripe_customer_id = self.stripe_customer_id.strip()
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
    source = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.source}%"


# --- 2. SERVICES ---

FEATURED_CATEGORY_RANKS = (
    (1, "First"),
    (2, "Second"),
    (3, "Third"),
)


class ServiceCategoryQuerySet(models.QuerySet):
    def for_catalog(self):
        """
        Deterministic ordering for the public catalog and related UIs.
        """
        return self.order_by(
            Case(
                When(featured_rank=1, then=Value(0)),
                When(featured_rank=2, then=Value(1)),
                When(featured_rank=3, then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            ),
            Coalesce("featured_rank", Value(4)),
            Coalesce("catalog_order", Value(1000)),
            "name",
        )


class ServiceCategoryManager(models.Manager.from_queryset(ServiceCategoryQuerySet)):
    def get_queryset(self):
        # Keep alphabetical ordering for callsites that rely on implicit sorting.
        return super().get_queryset().order_by("name")


class ServiceCategory(models.Model):
    """
    Represents a service offered in the system (e.g., haircut, massage).
    """
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=150, unique=True, db_index=True)
    only_discounted_services = models.BooleanField(
        default=False,
        help_text=(
            "Automatically list every active service that currently has an in-date discount. "
            "When enabled the category ignores manual assignments."
        ),
    )
    featured_rank = models.PositiveSmallIntegerField(
        choices=FEATURED_CATEGORY_RANKS,
        blank=True,
        null=True,
        help_text="Optional position for highlighting this category first in the catalog.",
    )
    catalog_order = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Lower numbers appear earlier for categories without a featured rank.",
    )

    objects = ServiceCategoryManager()

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._generate_unique_slug()
        super().save(*args, **kwargs)

    def _generate_unique_slug(self) -> str:
        """
        Derive a unique slug from the category name, preserving existing slugs on updates.
        """
        base = slugify(self.name or "") or "category"
        max_length = self._meta.get_field("slug").max_length
        base = base[:max_length].strip("-") or "category"

        taken = set(
            ServiceCategory.objects.exclude(pk=self.pk).values_list("slug", flat=True)
        )

        if base not in taken:
            return base

        for index in range(2, 5000):
            suffix = f"-{index}"
            trimmed_base = base[: max_length - len(suffix)]
            candidate = f"{trimmed_base}{suffix}".strip("-")
            if candidate and candidate not in taken:
                return candidate

        # Fallback: append a UUID chunk if everything else failed (extremely unlikely).
        from uuid import uuid4

        fallback = f"{base[: max_length - 9]}-{uuid4().hex[:8]}"
        return fallback.strip("-") or uuid4().hex[:max_length]

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["featured_rank"],
                condition=Q(featured_rank__isnull=False),
                name="core_servicecategory_unique_featured_rank",
            ),
            models.UniqueConstraint(
                fields=["only_discounted_services"],
                condition=Q(only_discounted_services=True),
                name="core_servicecategory_single_discount_bucket",
            ),
        ]

class PrepaymentOption(models.Model):
    """
    Defines available prepayment percentage options.
    """
    percent = models.IntegerField()

    def __str__(self):
        return f"{self.percent}%"


class ClientIntakeForm(models.Model):
    """
    Reusable questionnaire/consent form that can be assigned to services.
    The actual Django form class used to render/validate the payload is referenced via `form_class`.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    form_class = models.CharField(
        max_length=255,
        blank=True,
        help_text="Dotted path to a Django form class that handles rendering/validation.",
    )
    is_active = models.BooleanField(default=True)
    is_universal = models.BooleanField(
        default=False,
        help_text="When enabled, every client must complete this form once.",
    )
    schema = models.JSONField(default=dict, blank=True)
    schema_version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_form_class(self):
        """
        Resolve the dotted path from `form_class` into an actual form class.
        Returns None if not configured.
        """
        if not self.form_class:
            return None
        module_path, class_name = self.form_class.rsplit(".", 1)
        module = import_module(module_path)
        return getattr(module, class_name)

    def normalized_schema(self) -> dict:
        """
        Ensure schema always has expected structure.
        """
        schema = self.schema or {}
        if not isinstance(schema, dict):
            schema = {}
        schema.setdefault("sections", [])
        schema.setdefault("meta", {})
        return schema

    def build_bound_form(self, *, data=None, files=None, initial=None, client=None, prefix=None):
        """
        Build a Django form instance based on the stored schema.
        """
        from core.utils.intake_forms import build_intake_form

        return build_intake_form(
            intake_form=self,
            data=data,
            files=files,
            initial=initial,
            client=client,
            prefix=prefix,
        )


class Service(models.Model):
    """
    Represents a service offered in the system (e.g., haircut, massage).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    image = models.ImageField(
        upload_to=service_image_upload_to,
        blank=True,
        null=True,
        help_text="Shown on the public catalog cards."
    )
    image_alt_text = models.CharField(
        max_length=120,
        blank=True,
        help_text="Accessible text for the service image; defaults to the service name."
    )
    category = models.ForeignKey(ServiceCategory, on_delete=models.CASCADE, blank=True, null=True)
    allowed_rooms = models.ManyToManyField(
        "core.MasterRoom",
        related_name="services",
        blank=True,
    )
    # prepayment_option = models.ForeignKey(PrepaymentOption, on_delete=models.CASCADE, blank=True, null=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_min = models.IntegerField()
    extra_time_min = models.IntegerField(null=True, blank=True)
    pre_appointment_forms = models.ManyToManyField(
        "core.ClientIntakeForm",
        blank=True,
        related_name="services",
        help_text="Forms the client must complete before attending this service.",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    is_taxable = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Charge 5% GST when true.",
    )

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        old_image = None
        if self.pk:
            try:
                old_image = Service.objects.only("image").get(pk=self.pk).image
            except Service.DoesNotExist:
                old_image = None

        super().save(*args, **kwargs)

        # If a new image uploaded or cleared, remove the old file from storage to avoid leftovers.
        if old_image and getattr(old_image, "name", "") and old_image.name != getattr(self.image, "name", ""):
            old_image.delete(save=False)

    @property
    def card_image_url(self) -> str | None:
        return self.image.url if self.image else None

    @property
    def card_image_alt(self) -> str:
        return self.image_alt_text or self.name


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

    def active_forms(self):
        """
        Return only active pre-appointment forms assigned to this service.
        """
        prefetched = getattr(self, "_prefetched_objects_cache", {})
        if prefetched and "pre_appointment_forms" in prefetched:
            return [form for form in prefetched["pre_appointment_forms"] if form.is_active]
        return self.pre_appointment_forms.filter(is_active=True)


class ClientIntakeAssignmentQuerySet(models.QuerySet):
    def pending(self):
        return self.filter(
            form__is_active=True,
            completed_at__isnull=True,
        )

    def for_client(self, profile: "UserProfile"):
        return self.filter(client=profile).select_related("form", "assigned_by")


class ClientIntakeAssignment(models.Model):
    """
    Tracks intake forms that a client must complete outside of a specific appointment.
    Includes automatically enforced universal forms and manual staff assignments.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    form = models.ForeignKey(
        ClientIntakeForm,
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    client = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name="intake_assignments",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="intake_assignments_created",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    due_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="intake_assignments_completed",
    )
    notes = models.TextField(blank=True)

    objects = ClientIntakeAssignmentQuerySet.as_manager()

    class Meta:
        unique_together = ("form", "client")
        indexes = [
            models.Index(fields=["client", "form"]),
            models.Index(fields=["form", "completed_at"]),
            models.Index(fields=["client", "completed_at"]),
        ]
        verbose_name = "Client intake assignment"
        verbose_name_plural = "Client intake assignments"

    def __str__(self):
        return f"{self.form} → {self.client}"

    @property
    def is_completed(self) -> bool:
        return self.completed_at is not None

    @property
    def is_pending(self) -> bool:
        return not self.is_completed

    def mark_completed(self, *, timestamp=None, actor=None):
        """
        Mark the assignment as completed if not already done or if provided timestamp is newer.
        """
        ts = timestamp or timezone.now()
        update_fields = []

        if self.completed_at is None or ts >= self.completed_at:
            self.completed_at = ts
            update_fields.append("completed_at")

        actor_id = getattr(actor, "pk", None)
        if actor_id and self.completed_by_id != actor_id:
            self.completed_by_id = actor_id
            update_fields.append("completed_by")

        if update_fields:
            self.save(update_fields=update_fields)


class ClientIntakeFormSubmission(models.Model):
    """
    Stores answers for a specific intake form, optionally linked to an appointment.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    form = models.ForeignKey(
        ClientIntakeForm,
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    client = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name="intake_submissions",
    )
    appointment = models.ForeignKey(
        "core.Appointment",
        on_delete=models.CASCADE,
        related_name="intake_submissions",
        null=True,
        blank=True,
    )
    assignment = models.ForeignKey(
        "core.ClientIntakeAssignment",
        on_delete=models.SET_NULL,
        related_name="submissions",
        null=True,
        blank=True,
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="intake_submissions",
        null=True,
        blank=True,
    )
    data = models.JSONField(default=dict, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    form_schema_snapshot = models.JSONField(default=dict, blank=True)
    schema_version = models.PositiveIntegerField(default=1)
    is_complete = models.BooleanField(default=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        base = f"{self.form.name} → {self.client}"
        if self.appointment_id:
            return f"{base} ({self.appointment_id})"
        return base

    def clean(self):
        super().clean()
        if self.assignment_id:
            if self.assignment.client_id != self.client_id:
                raise ValidationError({"assignment": "Assignment does not belong to this client."})
            if self.assignment.form_id != self.form_id:
                raise ValidationError({"assignment": "Assignment is for a different intake form."})

    def save(self, *args, **kwargs):
        # Normalize submitted_at on update to reflect most recent answers.
        if not self._state.adding:
            now = timezone.now()
            update_fields = kwargs.get("update_fields")
            if update_fields:
                if "submitted_at" not in update_fields:
                    if isinstance(update_fields, (list, tuple, set)):
                        update_fields = list(update_fields)
                    else:
                        update_fields = [update_fields]
                    update_fields.append("submitted_at")
                    kwargs["update_fields"] = update_fields
                self.submitted_at = now
            else:
                self.submitted_at = now
        super().save(*args, **kwargs)
        if self.assignment_id:
            actor = getattr(self, "submitted_by", None)
            self.assignment.mark_completed(timestamp=self.submitted_at, actor=actor)

class MasterRoom(models.Model):
    """
    Rooms where Master will operate
    """
    room = models.CharField(max_length=20)

    def __str__(self):
        return self.room

class EmailVerification(models.Model):
    """
    Tracks email verification codes for a specific user and purpose.
    Only one active (unused) verification should exist per user/purpose pair.
    """
    PURPOSE_REGISTER = "register"
    PURPOSES = [(PURPOSE_REGISTER, "Register")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="email_verifications")
    purpose = models.CharField(max_length=32, choices=PURPOSES, default=PURPOSE_REGISTER, db_index=True)
    code = models.CharField(max_length=6)
    sent_to = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    last_sent_at = models.DateTimeField(auto_now=True)
    is_used = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["user", "purpose", "is_used"]),
            models.Index(fields=["expires_at"]),
        ]

    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at


class MasterProfile(models.Model):
    """
    Дополнительная информация о мастере: профессия, график работы, цвет и т.д.
    """
    user = models.OneToOneField(UserProfile, on_delete=models.CASCADE, related_name="master_profile")
    profession = models.CharField(max_length=100, blank=True)
    bio = models.TextField(blank=True)

    def __str__(self):
        return f"{self.user.get_full_name()}"
    @property
    def initials(self):
        parts = self.user.get_full_name().strip().split()
        if len(parts) >= 2:
            return parts[0][0] + parts[1][0]
        return self.user.get_full_name()[:2]

class MasterMonthlySalesTarget(models.Model):
    """
    Stores a monthly sales target for a master so progress can be surfaced in the admin dashboard.
    """
    master = models.ForeignKey(MasterProfile, on_delete=models.CASCADE, related_name="monthly_sales_targets")
    month = models.DateField(help_text="Use the first day of the month for tracking")
    target_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("master", "month")
        ordering = ["-month", "master__user__user__first_name", "master__user__user__last_name"]
        verbose_name = "Master sales target"
        verbose_name_plural = "Master sales targets"

    def __str__(self):
        return f"{self.master} - {self.month:%B %Y}: {self.target_amount}"

    def clean(self):
        super().clean()
        if self.month:
            self.month = self.month.replace(day=1)

    def save(self, *args, **kwargs):
        if self.month:
            self.month = self.month.replace(day=1)
        super().save(*args, **kwargs)

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


class BookingCart(models.Model):
    """Lightweight cart that accumulates services before a booking is confirmed."""

    owner = models.OneToOneField(
        UserProfile,
        on_delete=models.CASCADE,
        related_name="booking_cart",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def for_user(cls, profile: UserProfile) -> "BookingCart":
        """Ensure there is a cart for the given profile and return it."""
        cart, _ = cls.objects.get_or_create(owner=profile)
        return cart

    def clear(self) -> None:
        self.items.all().delete()

    def __str__(self):
        return f"Cart for {self.owner}"


class BookingCartItem(models.Model):
    """Single service selection stored inside a booking cart."""

    cart = models.ForeignKey(
        BookingCart,
        related_name="items",
        on_delete=models.CASCADE,
    )
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    master = models.ForeignKey(MasterProfile, on_delete=models.CASCADE)
    start_time = models.DateTimeField(help_text="Chosen start time for this service")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start_time", "id"]

    def clean(self):
        super().clean()
        if self.start_time and not timezone.is_aware(self.start_time):
            self.start_time = timezone.make_aware(self.start_time, timezone.get_current_timezone())

        service_obj = getattr(self, "service", None)
        if service_obj is None and self.service_id:
            service_obj = Service.objects.only("is_active").filter(pk=self.service_id).first()
        validate_service_is_active(service_obj)

        if not ServiceMaster.objects.filter(service=self.service, master=self.master).exists():
            raise ValidationError({"master": "Selected master cannot perform this service."})

    def service_duration(self) -> int:
        base = self.service.duration_min or 0
        extra = self.service.extra_time_min or 0
        return base + extra

    def end_time(self):
        dur = self.service_duration()
        return self.start_time + timedelta(minutes=dur)

    def __str__(self):
        stamp = self.start_time.astimezone(timezone.get_current_timezone()).strftime("%Y-%m-%d %H:%M")
        return f"{self.service.name} on {stamp} by {self.master}"

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


class AppointmentQuerySet(models.QuerySet):
    STATUS_CANCELLED = "CANCELLED"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_CONFIRMED = "CONFIRMED"
    STATUS_NO_SHOW = "NO_SHOW"
    STATUS_BOOKED = "BOOKED"

    STATUS_LABELS = {
        STATUS_CANCELLED: "Cancelled",
        STATUS_COMPLETED: "Completed",
        STATUS_CONFIRMED: "Confirmed",
        STATUS_NO_SHOW: "No show",
        STATUS_BOOKED: "Booked",
    }

    def with_aggregated_status(self) -> "AppointmentQuerySet":
        """
        Annotate appointments with their derived status code and label based on item statuses.
        """
        latest_history = (
            AppointmentItemStatusHistory.objects.filter(item_id=OuterRef("pk"))
            .order_by("-set_at", "-id")
        )

        items_with_status = AppointmentItem.objects.filter(appointment_id=OuterRef("pk")).annotate(
            latest_status_code=Subquery(latest_history.values("status__code")[:1])
        )

        labels = self.STATUS_LABELS

        return (
            self.alias(
                _has_items=Exists(items_with_status),
                _has_cancelled=Exists(
                    items_with_status.filter(latest_status_code=self.STATUS_CANCELLED)
                ),
                _has_non_cancelled=Exists(
                    items_with_status.filter(
                        Q(latest_status_code__isnull=True)
                        | ~Q(latest_status_code=self.STATUS_CANCELLED)
                    )
                ),
                _has_no_show=Exists(
                    items_with_status.filter(latest_status_code=self.STATUS_NO_SHOW)
                ),
                _has_non_no_show=Exists(
                    items_with_status.filter(
                        Q(latest_status_code__isnull=True)
                        | ~Q(latest_status_code=self.STATUS_NO_SHOW)
                    )
                ),
                _has_completed=Exists(
                    items_with_status.filter(latest_status_code=self.STATUS_COMPLETED)
                ),
                _has_non_completed=Exists(
                    items_with_status.filter(
                        Q(latest_status_code__isnull=True)
                        | ~Q(latest_status_code=self.STATUS_COMPLETED)
                    )
                ),
                _has_confirmed=Exists(
                    items_with_status.filter(latest_status_code=self.STATUS_CONFIRMED)
                ),
            )
            .annotate(
                _aggregated_status_code=Case(
                    When(
                        Q(
                            _has_items=True,
                            _has_cancelled=True,
                            _has_non_cancelled=False,
                        ),
                        then=Value(self.STATUS_CANCELLED),
                    ),
                    When(
                        Q(
                            _has_items=True,
                            _has_no_show=True,
                            _has_non_no_show=False,
                        ),
                        then=Value(self.STATUS_NO_SHOW),
                    ),
                    When(
                        Q(
                            _has_items=True,
                            _has_completed=True,
                            _has_non_completed=False,
                        ),
                        then=Value(self.STATUS_COMPLETED),
                    ),
                    When(
                        Q(
                            _has_confirmed=True,
                            _has_cancelled=False,
                        ),
                        then=Value(self.STATUS_CONFIRMED),
                    ),
                    default=Value(self.STATUS_BOOKED),
                    output_field=models.CharField(max_length=32),
                )
            )
            .annotate(
                _aggregated_status_label=Case(
                    When(
                        _aggregated_status_code=self.STATUS_CANCELLED,
                        then=Value(labels[self.STATUS_CANCELLED]),
                    ),
                    When(
                        _aggregated_status_code=self.STATUS_COMPLETED,
                        then=Value(labels[self.STATUS_COMPLETED]),
                    ),
                    When(
                        _aggregated_status_code=self.STATUS_CONFIRMED,
                        then=Value(labels[self.STATUS_CONFIRMED]),
                    ),
                    When(
                        _aggregated_status_code=self.STATUS_NO_SHOW,
                        then=Value(labels[self.STATUS_NO_SHOW]),
                    ),
                    default=Value(labels[self.STATUS_BOOKED]),
                    output_field=models.CharField(max_length=32),
                )
            )
        )


class Appointment(models.Model):
    """
    Represents a scheduled appointment between a client and a master for a service.
    """
    def get_default_payment_status_id():
        PaymentStatus = apps.get_model('core', 'PaymentStatus')
        obj = PaymentStatus.objects.filter(name="Not Paid").only('id').first()
        return obj.id if obj else None  # ок, если записи ещё нет

    payment_status = models.ForeignKey(
        'core.PaymentStatus',
        on_delete=models.CASCADE,
        default=get_default_payment_status_id,  # ленивый default
        null=True, blank=True,                  # временно допускаем пусто
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='appointments_as_client')
    start_time = models.DateTimeField(null=True, blank=True)
    # payment_status = models.ForeignKey(PaymentStatus, on_delete=models.CASCADE, default=PaymentStatus.objects.get(name="Not Paid").id)
    final_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, editable=False)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), editable=False)
    apply_card_processing_fee = models.BooleanField(
        default=False,
        editable=False,
        help_text="If true, card/Stripe processing fee is included in totals.",
    )
    card_processing_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        editable=False,
    )
    discount_source = models.CharField(max_length=30, blank=True, default="", editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(
        blank=True,
        default="",
        help_text="Internal notes, visible to staff only.",
    )

    # Снимок персональной скидки клиента на момент создания
    personal_discount_percent = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        editable=False,
        help_text="Personal discount snapshot at booking time"
    )

    objects = AppointmentQuerySet.as_manager()

    def _cache_aggregated_status(self, code: str, label: str) -> None:
        self.__dict__["_aggregated_status_code"] = code
        self.__dict__["_aggregated_status_label"] = label

    def _derive_aggregated_status(self) -> tuple[str, str]:
        """
        Compute the aggregated status code and display label from current item statuses.
        """
        items = list(self._prefetched_items())
        if not items:
            code = AppointmentQuerySet.STATUS_BOOKED
            label = AppointmentQuerySet.STATUS_LABELS[code]
            return code, label

        missing_status = False
        observed_codes: set[str] = set()

        for item in items:
            code = getattr(item, "current_status_code", None)
            if not code:
                status = getattr(item, "status", None)
                code = getattr(status, "code", None)

            if not code:
                missing_status = True
                continue

            observed_codes.add(str(code).upper())

        if missing_status:
            code = AppointmentQuerySet.STATUS_BOOKED
        elif not observed_codes:
            code = AppointmentQuerySet.STATUS_BOOKED
        elif observed_codes == {AppointmentQuerySet.STATUS_CANCELLED}:
            code = AppointmentQuerySet.STATUS_CANCELLED
        elif observed_codes == {AppointmentQuerySet.STATUS_COMPLETED}:
            code = AppointmentQuerySet.STATUS_COMPLETED
        elif observed_codes == {AppointmentQuerySet.STATUS_NO_SHOW}:
            code = AppointmentQuerySet.STATUS_NO_SHOW
        elif (
            AppointmentQuerySet.STATUS_CONFIRMED in observed_codes
            and AppointmentQuerySet.STATUS_CANCELLED not in observed_codes
        ):
            code = AppointmentQuerySet.STATUS_CONFIRMED
        else:
            code = AppointmentQuerySet.STATUS_BOOKED

        label = AppointmentQuerySet.STATUS_LABELS.get(
            code, code.replace("_", " ").title()
        )
        return code, label

    @property
    def aggregated_status_code(self) -> str:
        """
        Return the computed aggregate status code for this appointment.
        """
        if "_aggregated_status_code" in self.__dict__:
            return self.__dict__["_aggregated_status_code"]

        code, label = self._derive_aggregated_status()
        self._cache_aggregated_status(code, label)
        return code

    @property
    def aggregated_status(self) -> str:
        """
        Human-readable aggregate status label for the appointment.
        """
        if "_aggregated_status_label" in self.__dict__:
            return self.__dict__["_aggregated_status_label"]

        # Ensure code and label are cached together
        self.aggregated_status_code
        return self.__dict__.get(
            "_aggregated_status_label",
            AppointmentQuerySet.STATUS_LABELS[AppointmentQuerySet.STATUS_BOOKED],
        )

    def _prefetched_items(self):
        """Return prefetched items list or fallback queryset."""
        cache = getattr(self, "_prefetched_objects_cache", {})
        if "items" in cache:
            return cache["items"]
        return self.items.all()

    def _first_item(self):
        """Compatibility helper: earliest appointment item."""
        items = self._prefetched_items()
        if hasattr(items, "order_by"):
            return items.order_by("start_time").first()
        earliest = None
        for it in items:
            if earliest is None:
                earliest = it
                continue
            if it.start_time and (earliest.start_time is None or it.start_time < earliest.start_time):
                earliest = it
        return earliest

    @property
    def primary_item(self):
        """Expose main AppointmentItem for legacy consumers."""
        return self._first_item()

    @property
    def service(self):
        item = self._first_item()
        return getattr(item, "service", None)

    @property
    def master(self):
        item = self._first_item()
        return getattr(item, "master", None)

    @property
    def price(self):
        return self.final_price

    def _subtotal_for_tax(self) -> Decimal:
        """
        Return the appointment subtotal after discounts (without tax).
        """
        subtotal = Decimal("0.00")
        for item in self._prefetched_items():
            subtotal += Decimal(getattr(item, "final_price", Decimal("0.00")) or Decimal("0.00"))
        if hasattr(self, "product_sales"):
            for sale in self.product_sales.all():
                subtotal += Decimal(getattr(sale, "total_amount", Decimal("0.00")) or Decimal("0.00"))
        return subtotal.quantize(TWOPLACES)

    @property
    def total_with_tax(self) -> Decimal:
        """
        Appointment grand total including GST and card processing surcharge.
        """
        if self.final_price is not None:
            return Decimal(self.final_price).quantize(TWOPLACES)
        subtotal = self._subtotal_for_tax()
        tax_total = Decimal(getattr(self, "tax_amount", Decimal("0.00")) or Decimal("0.00"))
        base_total = (subtotal + tax_total).quantize(TWOPLACES)
        fee = Decimal("0.00")
        if getattr(self, "apply_card_processing_fee", False):
            stored_fee = Decimal(getattr(self, "card_processing_fee", Decimal("0.00")) or Decimal("0.00"))
            if stored_fee > Decimal("0.00"):
                fee = stored_fee.quantize(TWOPLACES)
            else:
                fee = card_processing_fee(base_total)
        return (base_total + fee).quantize(TWOPLACES)



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
        tax_total = Decimal("0.00")
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
            tax_total += getattr(it, "tax_amount", Decimal("0.00"))
            # собираем ТОЛЬКО позиционные источники
            if it.discount_source:
                item_sources.add(it.discount_source)
        # агрегированный источник

        product_sales_rel = getattr(self, "product_sales", None)
        if product_sales_rel is not None:
            for sale in product_sales_rel.all():
                subtotal += Decimal(getattr(sale, "total_amount", Decimal("0.00")) or Decimal("0.00"))
                tax_total += Decimal(getattr(sale, "tax_amount", Decimal("0.00")) or Decimal("0.00"))

        self.sync_start_time_from_items(save=True)
        self.discount_source = max(item_sources) if item_sources else ""
        with transaction.atomic():
            if persist_items and changed:
                type(self).items.rel.related_model.objects.bulk_update(
                    changed, ["final_price", "tax_amount", "discount_source", "unit_price"]
                )
        self.tax_amount = tax_total.quantize(TWOPLACES)
        base_total = (subtotal + tax_total).quantize(TWOPLACES)
        processing_fee = Decimal("0.00")
        if self.apply_card_processing_fee:
            stored_fee = Decimal(getattr(self, "card_processing_fee", Decimal("0.00")) or Decimal("0.00"))
            if stored_fee > Decimal("0.00"):
                processing_fee = stored_fee.quantize(TWOPLACES)
                self.card_processing_fee = processing_fee
            else:
                processing_fee = card_processing_fee(base_total)
                self.card_processing_fee = processing_fee
        else:
            self.card_processing_fee = Decimal("0.00")
        self.final_price = (base_total + processing_fee).quantize(TWOPLACES)
        if save:
            super().save(
                update_fields=[
                    "final_price",
                    "tax_amount",
                    "card_processing_fee",
                    "discount_source",
                    "start_time",
                    "apply_card_processing_fee",
                ]
            )

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

        # CHANGED: annotate items with current status so cancelled entries can be ignored.
        items = list(
            self._items_qs()
            .with_current_status()
            .select_related("service", "master", "appointment")
        )
        if not items:
            return

        errors = {}

        # Внутренняя функция проверки одного айтема,
        # почти та же логика, что в AppointmentItem.clean
        service_room_usage = {}
        service_allowed_rooms = {}

        def validate_item(it: "AppointmentItem"):
            status_code = (
                getattr(it, "current_status_code", None)
                or getattr(getattr(it, "status", None), "code", "")
            )
            if status_code and str(status_code).upper() == "CANCELLED":
                return  # CHANGED: skip validation for cancelled appointment items

            # старт от Appointment
            start_dt = getattr(it, "start_time", None) or self.start_time
            if not it.master or not it.service or not start_dt:
                return  # пропускаем неполные строки

            total_min = it.duration_min if hasattr(it, "duration_min") else 0
            this_end = start_dt + timedelta(minutes=total_min)

            # Поиск пересечений с чужими AppointmentItem этого же мастера
            active_status_q = Q(current_status_code__isnull=True) | ~Q(current_status_code__iexact="CANCELLED")  # CHANGED: retain items with no status history

            overlapping_qs = (
                AppointmentItem.objects.with_current_status()
                .filter(
                    master=it.master,
                    start_time__lt=this_end,
                    start_time__gte=start_dt - timedelta(hours=3),
                )
                .filter(active_status_q)
            )  # CHANGED: rely on item-level status when checking overlaps

            # исключаем все айтемы текущего Appointment
            if self.pk:
                overlapping_qs = overlapping_qs.exclude(appointment=self)
            if getattr(it, "pk", None):
                overlapping_qs = overlapping_qs.exclude(pk=it.pk)

            for other in overlapping_qs.select_related("service", "appointment"):
                other_start = other.appointment.start_time if other.appointment else None
                if not other_start:
                    continue
                other_total = other.duration_min if hasattr(other, "duration_min") else 0
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

            # Резервируем комнаты на уровне текущего Appointment, чтобы не превышать вместимость
            service_obj = getattr(it, "service", None)
            service_pk = getattr(service_obj, "pk", None) or getattr(it, "service_id", None)
            if not service_pk:
                return

            if service_pk not in service_allowed_rooms:
                service_allowed_rooms[service_pk] = list(service_obj.allowed_rooms.values_list("pk", flat=True))
            allowed_room_ids = service_allowed_rooms[service_pk]
            if not allowed_room_ids:
                errors.setdefault("service", []).append("Service must be assigned to at least one room.")
                return

            allocations = service_room_usage.setdefault(service_pk, [])
            overlaps = sum(1 for exist_start, exist_end in allocations if start_dt < exist_end and this_end > exist_start)
            if overlaps >= len(allowed_room_ids):
                errors.setdefault("start_time", []).append("All rooms for this service are busy at this time.")
                return
            allocations.append((start_dt, this_end))

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

class AppointmentItemQuerySet(models.QuerySet):
    def with_current_status(self) -> "AppointmentItemQuerySet":
        """
        Annotate appointment items with their latest status metadata.
        """
        latest_history = (
            AppointmentItemStatusHistory.objects.filter(item_id=OuterRef("pk"))
            .order_by("-set_at", "-id")
        )

        return self.annotate(
            current_status_id=Subquery(latest_history.values("status_id")[:1]),
            current_status_code=Subquery(latest_history.values("status__code")[:1]),
            current_status_label=Subquery(latest_history.values("status__name")[:1]),
            current_status_set_at=Subquery(latest_history.values("set_at")[:1]),
        )


class AppointmentItemManager(models.Manager.from_queryset(AppointmentItemQuerySet)):
    pass


class AppointmentItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="items")
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    master = models.ForeignKey(MasterProfile, on_delete=models.CASCADE, related_name="appointment_items")
    status = models.ForeignKey(
        "core.AppointmentItemStatus",
        on_delete=models.PROTECT,
        related_name="items",
        null=True,
        blank=True,
        help_text="Legacy pointer to the latest status; prefer status history helpers.",
    )

    validation_enabled = models.BooleanField(
        default=True,
        db_index=True,
        help_text="When off, time/room validation for this item is skipped; overlaps are allowed.",
    )

    # Время начала именно этой услуги
    start_time = models.DateTimeField()

    # Базовая цена позиции на момент записи (может быть вручную переопределена в админке)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0'))], null=True, blank=True)
    unit_price_overridden = models.BooleanField(default=False, help_text="Manually set in admin")
    duration_override_min = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="Custom duration in minutes for this appointment only"
    )
    room = models.ForeignKey(
        "core.MasterRoom",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        editable=False,
        related_name="appointment_items",
    )
    end_time = models.DateTimeField(null=True, blank=True)
    manual_discount_percent = models.PositiveSmallIntegerField(
        default=0,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Additional per-appointment discount in percent"
    )
    # Итог позиции после позиционных скидок (service/promocode). Персональная НЕ учитывается!
    final_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, editable=False)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), editable=False)
    discount_source = models.CharField(max_length=30, blank=True, default="", editable=False)  # '', 'service', 'promocode'

    objects = AppointmentItemManager()

    @staticmethod
    @lru_cache(maxsize=1)
    def _validation_column_available() -> bool:
        table = AppointmentItem._meta.db_table
        try:
            with connection.cursor() as cursor:
                description = connection.introspection.get_table_description(cursor, table)
        except Exception:
            return False
        return any(getattr(col, "name", "") == "validation_enabled" for col in description)

    class Meta:
        indexes = [
            models.Index(fields=["master", "start_time"], name="appt_master_start_idx"),
            models.Index(fields=["service", "start_time"], name="appt_service_start_idx"),
            models.Index(fields=["room", "start_time"], name="appt_room_start_idx"),
        ]
    def __str__(self):
        return f"{self.appointment.client} for {self.service} at {self.start_time}"
    @property
    def duration_min(self) -> int:
        if self.duration_override_min:
            return int(self.duration_override_min)
        service = getattr(self, "service", None)
        if not service:
            return 0
        extra = service.extra_time_min or 0
        return int((service.duration_min or 0) + extra)

    def compute_end_time(self) -> datetime | None:
        if not self.start_time or not getattr(self, "service", None):
            return None
        base = getattr(self.service, "duration_min", 0) or 0
        extra = getattr(self.service, "extra_time_min", 0) or 0
        dur_min = int(self.duration_override_min or (base + extra))
        return self.start_time + timedelta(minutes=dur_min)

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
        manual_disc = int(getattr(self, "manual_discount_percent", 0) or 0)
        if manual_disc:
            price = price * (Decimal(100) - Decimal(manual_disc)) / Decimal(100)
        # Apply personal discount snapshot at booking time
        personal_pct = 0
        if self.appointment and self.appointment.client:
            personal_pct = int(self.appointment.client.personal_discount_percent or 0)

        if personal_pct:
            price = price * (Decimal(100) - Decimal(personal_pct)) / Decimal(100)
        # Finalize computed price
        self.final_price = price.quantize(Decimal("0.01"))
        # Track discount source flags
        if service_disc == 0 and personal_pct == 0 and promo_disc == 0:
            discount_source = ""
        elif promo_disc > 0 and personal_pct > 0 and service_disc:
            discount_source = "promocode+personal+service"
        elif service_disc > 0 and personal_pct > 0:
            discount_source = "service+personal"
        elif promo_disc > 0 and personal_pct > 0:
            discount_source = "promocode+personal"
        elif service_disc > 0:
            discount_source = "service"
        elif promo_disc > 0:
            discount_source = "promocode"
        else:
            discount_source = "personal"

        if manual_disc > 0:
            discount_source = f"{discount_source}+manual" if discount_source else "manual"
        self.discount_source = discount_source

        taxable_service = getattr(self.service, "is_taxable", False)
        if taxable_service:
            self.tax_amount = compute_tax(self.final_price)
        else:
            self.tax_amount = Decimal("0.00")

    def _final_price_for_tax(self) -> Decimal:
        """
        Determine the effective final price (post-discount) for tax calculations.
        """
        price = getattr(self, "final_price", None)
        if price is not None:
            return Decimal(price).quantize(TWOPLACES)

        original_final = getattr(self, "final_price", None)
        original_source = getattr(self, "discount_source", "")
        self._compute_item_pricing()
        computed = getattr(self, "final_price", None)
        if computed is None:
            computed = self._effective_unit_price()
        computed_decimal = Decimal(computed).quantize(TWOPLACES)
        # Restore initial state to avoid mutating unsaved instances.
        self.final_price = original_final
        self.discount_source = original_source
        return computed_decimal

    # Удобный хелпер: берём реальный старт из self.start_time (или из appointment.start_time, если нет)
    def _resolve_start_dt(self):
        if getattr(self, "start_time", None):
            return self.start_time
        appt = getattr(self, "appointment", None)
        return getattr(appt, "start_time", None)

    def clean(self):
        super().clean()
        start_dt = self._resolve_start_dt()

        service_obj = getattr(self, "service", None)
        if service_obj is None and self.service_id:
            service_obj = (
                Service.objects.filter(pk=self.service_id).select_related("category").first()
            )
            if service_obj is not None:
                self.service = service_obj
        validate_service_is_active(service_obj)

        # Хард-стоп по времени суток
        if start_dt and start_dt.time() > time(23, 59):
            raise ValidationError({"start_time": "Время начала не может быть позже 23:59."})

        if start_dt and self.service_id:
            self.end_time = self.compute_end_time()
        else:
            self.end_time = None

        # До ключевых атрибутов — выходим тихо
        if not self.master or not self.service or not start_dt:
            return

        total_min = self.duration_min
        this_end = self.end_time or (start_dt + timedelta(minutes=total_min))

        status_code = None
        if hasattr(self, "current_status_code") and self.current_status_code:
            status_code = self.current_status_code
        elif getattr(getattr(self, "status", None), "code", None):
            status_code = self.status.code
        elif getattr(self, "_initial_status_code", None):
            status_code = self._initial_status_code

        if status_code and str(status_code).upper() == "CANCELLED":
            return

        if not self._validation_column_available():
            return

        latest_appt_status_sq = None
        try:
            appt_status_history_model = apps.get_model(self._meta.app_label, "AppointmentStatusHistory")
        except LookupError:
            appt_status_history_model = None
        else:
            latest_appt_status_sq = (
                appt_status_history_model.objects.filter(appointment_id=OuterRef("appointment_id"))
                .order_by("-set_at", "-id")
                .values("status__name")[:1]
            )

        # === 1) Пересечения для этого мастера по предметному времени (AppointmentItem.start_time) ===
        if not getattr(self, "validation_enabled", True):
            return

        active_status_q = Q(current_status_code__isnull=True) | ~Q(current_status_code__iexact="CANCELLED")  # CHANGED: treat NULL current status as active

        overlap_filter = Q(start_time__lt=this_end) & (Q(end_time__gt=start_dt) | Q(end_time__isnull=True))

        validation_active_q = Q(validation_enabled__isnull=True) | Q(validation_enabled=True)

        try:
            master_conflicts_qs = (
                type(self)
                .objects.with_current_status()
                .filter(master=self.master)
                .filter(overlap_filter)
                .filter(active_status_q)
                .filter(validation_active_q)
            )
            if latest_appt_status_sq is not None:
                master_conflicts_qs = master_conflicts_qs.annotate(
                    _latest_appt_status=Subquery(latest_appt_status_sq)
                ).exclude(_latest_appt_status__iexact="Cancelled")
            if self.pk:
                master_conflicts_qs = master_conflicts_qs.exclude(pk=self.pk)

            if master_conflicts_qs.exists():
                raise ValidationError({
                    "start_time": "Этот слот пересекается с другим приёмом у того же мастера."
                })
        except (ProgrammingError, OperationalError):
            pass

        # === 2) Проверка рабочего окна мастера (MasterProfile.workdays[weekday]: start_time..end_time) ===
        # master может быть либо MasterProfile, либо User с related master_profile
        master_profile = getattr(self.master, "master_profile", None) or self.master
        workdays_qs = getattr(master_profile, "workdays", None)
        has_workdays = bool(workdays_qs and workdays_qs.exists())

        if has_workdays:
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

        # === 3) Комнатная вместимость ===
        allowed_room_ids = set(self.service.allowed_rooms.values_list("pk", flat=True))
        if not allowed_room_ids:
            raise ValidationError({"service": "Service must be assigned to at least one room."})

        # CHANGED: normalize room selection to ensure overlap checks have consistent room id.
        room_candidate_id = self.room_id
        auto_assigned_room = False
        if room_candidate_id:
            if room_candidate_id not in allowed_room_ids:
                raise ValidationError({"room": "Service can't be performed in the selected room."})
        else:
            from .utils import pick_free_room

            room_candidate = pick_free_room(self.service, start_dt, this_end)
            if room_candidate is None:
                raise ValidationError("All rooms for this service are busy at this time.")
            self.room = room_candidate
            self.room_id = getattr(room_candidate, "pk", getattr(self, "room_id", None))
            room_candidate_id = self.room_id
            auto_assigned_room = True

        if not room_candidate_id:
            raise ValidationError({"room": "Unable to determine a room for this service."})

        allowed_rooms = {
            room.pk: room
            for room in self.service.allowed_rooms.order_by("pk")
        }

        def _fetch_room_conflicts(room_id: int) -> list["AppointmentItem"]:
            qs = (
                type(self)
                .objects.with_current_status()
                .filter(
                    room_id=room_id,
                    start_time__lt=this_end,
                    start_time__gt=start_dt - timedelta(hours=24),
                )
                .filter(overlap_filter)
                .filter(active_status_q)
                .filter(validation_active_q)
            )
            if latest_appt_status_sq is not None:
                qs = qs.annotate(
                    _latest_appt_status=Subquery(latest_appt_status_sq)
                ).exclude(_latest_appt_status__iexact="Cancelled")
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            return list(qs.select_related("service", "appointment", "master"))

        def _has_overlap(items: list["AppointmentItem"]) -> bool:
            return any(True for _ in items)

        room_conflicts = _fetch_room_conflicts(room_candidate_id)

        if auto_assigned_room and _has_overlap(room_conflicts):
            for alt_room_id in allowed_room_ids:
                if alt_room_id == room_candidate_id:
                    continue
                alt_conflicts = _fetch_room_conflicts(alt_room_id)
                if not _has_overlap(alt_conflicts):
                    alt_room = allowed_rooms.get(alt_room_id)
                    if alt_room is None:
                        alt_room = self.service.allowed_rooms.filter(pk=alt_room_id).first()
                    self.room_id = alt_room_id
                    if alt_room is not None:
                        self.room = alt_room
                    room_candidate_id = alt_room_id
                    room_conflicts = alt_conflicts
                    break

        if _has_overlap(room_conflicts):
            raise ValidationError({
                "start_time": "This room is currently used by another service for the selected time."
            })

# === 4) Недоступность мастера (time off / vacation / blocked) ===
        # Allow visual side-by-side rendering with lunch/time-off when validation is off.
        if hasattr(self, "validation_enabled") and not getattr(self, "validation_enabled", True):
            return
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

        if self.service_id and self.start_time:
            self.end_time = self.compute_end_time()

        self.full_clean()

        with transaction.atomic():
            super().save(*args, **kwargs)



class AppointmentItemStatus(models.Model):
    name = models.CharField(max_length=40)
    code = models.CharField(max_length=32, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "id"]
        verbose_name = "Appointment item status"
        verbose_name_plural = "Appointment item statuses"
        indexes = [
            models.Index(fields=["code"], name="appt_item_status_code_idx"),
        ]

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.upper()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class AppointmentItemStatusHistory(models.Model):
    item = models.ForeignKey(
        AppointmentItem,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    status = models.ForeignKey(
        AppointmentItemStatus,
        on_delete=models.PROTECT,
        related_name="history",
    )
    set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="appointment_item_status_actions",
        null=True,
        blank=True,
    )
    set_at = models.DateTimeField(default=timezone.now, db_index=True)
    note = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["-set_at", "-id"]
        verbose_name = "Appointment item status history"
        verbose_name_plural = "Appointment item status history"
        indexes = [
            models.Index(fields=["item", "-set_at"], name="appt_item_status_hist_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.item_id} → {self.status.code} @ {self.set_at:%Y-%m-%d %H:%M:%S}"


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

# --- 4. RETAIL PRODUCTS ---


class ProductCategory(models.Model):
    """
    Top-level grouping for retail products (e.g. Hair Care, Skin Care).
    """
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Product category"
        verbose_name_plural = "Product categories"

    def __str__(self):
        return self.name


class Product(models.Model):
    """
    Retail product that can be sold to clients.
    """
    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.SET_NULL,
        related_name="products",
        blank=True,
        null=True,
    )
    name = models.CharField(max_length=200, unique=True)
    sku = models.CharField(max_length=64, blank=True, null=True, unique=True)
    description = models.TextField(blank=True)
    measure_type = models.CharField(
        max_length=64,
        blank=True,
        help_text="Unit type used by the supplier (e.g. ml, g, pack).",
    )
    measure_value = models.CharField(
        max_length=64,
        blank=True,
        help_text="Package size or quantity as provided by the supplier.",
    )
    brand = models.CharField(max_length=120, blank=True)
    supplier = models.CharField(max_length=120, blank=True)
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Internal cost per unit.",
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Default retail price (CAD).",
    )
    quantity_in_stock = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(
        default=0,
        help_text="Set >0 to flag products that need restock.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_active", "name"], name="product_active_name_idx"),
        ]

    def clean(self):
        super().clean()
        if self.low_stock_threshold and self.low_stock_threshold < 0:
            raise ValidationError({"low_stock_threshold": "Low stock threshold cannot be negative."})

    @property
    def is_low_on_stock(self) -> bool:
        if not self.low_stock_threshold:
            return False
        return self.quantity_in_stock <= self.low_stock_threshold

    def __str__(self):
        return self.name


class ProductSale(models.Model):
    """
    Immutable record describing the sale of a product to a client.
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="sales",
    )
    sold_by = models.ForeignKey(
        UserProfile,
        on_delete=models.PROTECT,
        related_name="product_sales",
        help_text="Employee who processed the sale.",
    )
    client = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        related_name="retail_purchases",
        blank=True,
        null=True,
        help_text="Client receiving the product (optional).",
    )
    appointment = models.ForeignKey(
        "core.Appointment",
        on_delete=models.SET_NULL,
        related_name="product_sales",
        blank=True,
        null=True,
        help_text="Appointment associated with this sale (optional).",
    )
    sold_at = models.DateTimeField(default=timezone.now, db_index=True)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Price per unit at the time of sale.",
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        editable=False,
        help_text="Computed total for reporting.",
    )
    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        editable=False,
        help_text="Tax collected for this sale.",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-sold_at", "-id"]
        indexes = [
            models.Index(fields=["sold_at"], name="product_sale_sold_at_idx"),
            models.Index(fields=["product", "sold_at"], name="product_sale_product_idx"),
            models.Index(fields=["sold_by", "sold_at"], name="product_sale_employee_idx"),
            models.Index(fields=["appointment"], name="product_sale_appt_idx"),
        ]
        constraints = [
            models.CheckConstraint(check=Q(quantity__gt=0), name="product_sale_quantity_positive"),
            models.CheckConstraint(check=Q(unit_price__gte=Decimal("0.00")), name="product_sale_unit_price_positive"),
        ]

    def clean(self):
        super().clean()
        if not self.product_id:
            raise ValidationError({"product": "Product is required."})
        if not self.sold_by_id:
            raise ValidationError({"sold_by": "Sold by user is required."})
        if self.product_id and not self.product.is_active:
            raise ValidationError({"product": "Cannot sell an inactive product."})

    def _compute_total_amount(self) -> Decimal:
        try:
            return (self.unit_price * Decimal(self.quantity)).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError) as exc:
            raise ValidationError({"unit_price": "Invalid price precision."}) from exc

    def save(self, *args, **kwargs):
        if self.sold_at and timezone.is_naive(self.sold_at):
            self.sold_at = timezone.make_aware(self.sold_at, timezone.get_current_timezone())

        if self.product_id and self.unit_price is None:
            self.unit_price = self.product.price

        self.total_amount = self._compute_total_amount()
        self.tax_amount = compute_tax(self.total_amount)

        update_fields = kwargs.get("update_fields")
        restrict_update = update_fields is not None

        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=self.product_id)

            if self._state.adding:
                if self.quantity > product.quantity_in_stock:
                    raise ValidationError({"quantity": "Insufficient stock for this product."})
                product.quantity_in_stock -= self.quantity
                product.save(update_fields=["quantity_in_stock", "updated_at"])
            else:
                prev = type(self).objects.select_for_update().get(pk=self.pk)
                if prev.product_id != self.product_id:
                    raise ValidationError({"product": "Changing product on an existing sale is not supported."})
                delta = self.quantity - prev.quantity
                if delta:
                    if delta > 0 and delta > product.quantity_in_stock:
                        raise ValidationError({"quantity": "Insufficient stock for this product."})
                    product.quantity_in_stock -= delta
                    product.save(update_fields=["quantity_in_stock", "updated_at"])

                if restrict_update:
                    # ensure total_amount stays in sync even with update_fields
                    kwargs["update_fields"] = list(set(update_fields) | {"total_amount", "tax_amount", "updated_at"})

            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=self.product_id)
            product.quantity_in_stock += self.quantity
            product.save(update_fields=["quantity_in_stock", "updated_at"])
            super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.product} × {self.quantity} on {timezone.localtime(self.sold_at).strftime('%Y-%m-%d')}"


# --- 5. PAYMENTS ---

class ClientCard(models.Model):
    """Snapshot of a client card saved in Stripe (non-sensitive)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='cards')
    stripe_customer_id = models.CharField(max_length=255, db_index=True)
    stripe_payment_method_id = models.CharField(max_length=255, unique=True)
    brand = models.CharField(max_length=32)
    last4 = models.CharField(max_length=4)
    exp_month = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    exp_year = models.PositiveSmallIntegerField(validators=[MinValueValidator(2000), MaxValueValidator(2100)])
    funding = models.CharField(max_length=16)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['client', 'stripe_payment_method_id'],
                name='uniq_client_card_by_method',
            )
        ]
        indexes = [
            models.Index(fields=['client', 'is_default'], name='clientcard_default_idx'),
        ]

    def __str__(self) -> str:
        return self.label()

    def label(self) -> str:
        dots = '\u2022' * 4
        return f"{self.brand} {dots} {self.last4} ({self.exp_month}/{self.exp_year})"


class PaymentMethod(models.Model):
    """
    Represents a method of payment (e.g., Credit Card, Cash).
    """
    name = models.CharField(max_length=20)

    def __str__(self):
        return self.name


class Payment(models.Model):
    """Stores payment records for appointments (Stripe + offline)."""

    STRIPE_STATUS_CHOICES = [
        ("requires_payment_method", "Requires payment method"),
        ("requires_confirmation", "Requires confirmation"),
        ("requires_action", "Requires action"),
        ("processing", "Processing"),
        ("succeeded", "Succeeded"),
        ("canceled", "Canceled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name="payments",
        null=True,
        blank=True,
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default="cad")
    method = models.ForeignKey(PaymentMethod, on_delete=models.CASCADE)
    status = models.CharField(
        max_length=32,
        choices=STRIPE_STATUS_CHOICES,
        default="requires_payment_method",
    )
    stripe_payment_intent_id = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
    )
    stripe_payment_method_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    stripe_charge_id = models.CharField(max_length=255, null=True, blank=True)
    receipt_url = models.URLField(blank=True)
    receipt_pdf = models.FileField(
        upload_to="receipts/%Y/%m/",
        blank=True,
        null=True,
        storage=S3Boto3Storage()
    )
    receipt_sent_at = models.DateTimeField(blank=True, null=True)
    livemode = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)
    amount_received = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    amount_refunded = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    captured_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["stripe_payment_intent_id"], name="payment_intent_idx"),
            models.Index(fields=["status"], name="payment_status_idx"),
            models.Index(fields=["stripe_payment_method_id"], name="payment_method_idx"),
        ]

    def __str__(self):
        target = self.appointment_id or "unlinked"
        return f"Payment {self.amount} {self.currency} for {target}"


class PaymentRefund(models.Model):
    """Audit record for manual or Stripe-initiated refunds tied to an appointment."""

    METHOD_STRIPE = "stripe"
    METHOD_CASH = "cash"
    METHOD_ETRANSFER = "etransfer"

    METHOD_CHOICES = [
        (METHOD_STRIPE, "Stripe"),
        (METHOD_CASH, "Cash"),
        (METHOD_ETRANSFER, "E-Transfer"),
    ]

    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name="refunds",
    )
    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name="refunds",
        null=True,
        blank=True,
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Refund amount in major currency units.",
    )
    amount_minor = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="Refund amount in minor currency units (e.g., cents).",
    )
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    stripe_refund_id = models.CharField(max_length=64, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="payment_refunds",
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Payment Refund"
        verbose_name_plural = "Payment Refunds"

    def __str__(self) -> str:
        amount_display = f"{self.amount:.2f}"
        method_label = dict(self.METHOD_CHOICES).get(self.method, self.method)
        return f"{amount_display} via {method_label} for {self.appointment_id}"

# --- 6. PREPAYMENTS ---


class AppointmentPrepayment(models.Model):
    """
    Links a prepayment option to a specific appointment.
    """
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE)
    option = models.ForeignKey(PrepaymentOption, on_delete=models.CASCADE)

# --- 7. FILES ---

class ClientFile(models.Model):
    """
    Represents a file uploaded for a user, such as a document or image.
    """
    USER = 'user'
    ADMIN = 'admin'
    KIND_BEFORE = "before"
    KIND_AFTER = "after"
    KIND_OTHER = "other"

    OWNER_CHOICES = [
        (USER, 'User'),
        (ADMIN, 'Admin'),
    ]
    KIND_CHOICES = [
        (KIND_BEFORE, "Before"),
        (KIND_AFTER, "After"),
        (KIND_OTHER, "Other"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name="client_files",
        null=True,
        blank=True,
        help_text="Appointment this file belongs to.",
    )
    file = models.FileField(upload_to='client_files/', storage=S3Boto3Storage()) # stored in S3!
    file_type = models.CharField(max_length=50, editable=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.CharField(
        max_length=10,
        choices=OWNER_CHOICES,
        default=USER,
        help_text="Who uploaded the file: admin or user"
    )
    uploaded_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_client_files",
        help_text="Staff member who uploaded the file.",
    )
    kind = models.CharField(
        max_length=16,
        choices=KIND_CHOICES,
        default=KIND_OTHER,
        help_text="Categorise the file for before/after tracking.",
    )

    description = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional description (e.g., 'Form before procedure')"
    )

    class Meta:
        ordering = ("-uploaded_at", "-id")

    def _sync_user_with_appointment(self):
        if not self.appointment_id:
            return
        appointment_client_id = getattr(self.appointment, "client_id", None)
        if appointment_client_id is None:
            appointment_client_id = (
                Appointment.objects.filter(pk=self.appointment_id)
                .values_list("client_id", flat=True)
                .first()
            )
        if appointment_client_id is None:
            raise ValidationError({
                "appointment": "Selected appointment has no client linked.",
            })
        client_obj = getattr(self.appointment, "client", None)
        if client_obj is None:
            client_obj = UserProfile.objects.filter(pk=appointment_client_id).first()
        if client_obj is None:
            raise ValidationError({
                "appointment": "Unable to resolve the client profile for this appointment.",
            })
        self.user = client_obj
        self.user_id = appointment_client_id

    def clean(self):
        super().clean()
        self._sync_user_with_appointment()

    def save(self, *args, **kwargs):
        if self.file and not self.file_type:
            name, extension = os.path.splitext(self.file.name)
            self.file_type = extension.lower().lstrip('.')  # без точки
        # Ensure relational integrity before persisting.
        self._sync_user_with_appointment()
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def is_image(self) -> bool:
        image_types = {
            "jpg",
            "jpeg",
            "png",
            "gif",
            "bmp",
            "webp",
            "tiff",
            "heic",
            "heif",
            "svg",
        }
        return (self.file_type or "").lower() in image_types

    def __str__(self) -> str:
        kind_label = self.get_kind_display()
        if self.appointment_id:
            return f"{kind_label} for appointment {self.appointment_id}"
        return f"{kind_label} for {self.user}"

    @property
    def uploader_display(self) -> str:
        if self.uploaded_by_user_id:
            user_obj = self.uploaded_by_user
            if user_obj:
                full_name = user_obj.get_full_name()
                if full_name:
                    return full_name
                username = getattr(user_obj, "get_username", None)
                if callable(username):
                    return username()
                return getattr(user_obj, "username", str(user_obj))
        if self.uploaded_by == self.ADMIN:
            return "Admin"
        if self.uploaded_by == self.USER:
            return "Client"
        return (self.uploaded_by or "Unknown").title()

    @property
    def filename(self) -> str:
        if not self.file:
            return ""
        raw_name = os.path.basename(self.file.name or "")
        # CHANGED: strip storage suffixes like "_ABC123" so UI shows the original upload name.
        root, ext = os.path.splitext(raw_name)
        parts = root.rsplit("_", 1)
        if len(parts) == 2:
            suffix = parts[1]
            if suffix and suffix.isalnum() and len(suffix) >= 6:
                return f"{parts[0]}{ext}"
        return raw_name

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
                start_time__lt=self.end_time,
                start_time__gte=self.start_time - timedelta(hours=3),
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
