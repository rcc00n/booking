# accounts/views.py
from __future__ import annotations

from decimal import Decimal
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import TemplateView, ListView
from django.views.generic.edit import CreateView
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from django.utils import timezone
from django.db.models import OuterRef, Subquery, Count, Prefetch, Sum, F
from django.db.models.functions import TruncMonth
import hashlib

from core.models import (
    Service,
    Appointment,
    AppointmentStatusHistory,
    UserProfile,
    AppointmentItem,
    Product,
    ProductSale,
    EmailVerification,
)

from .forms import (
    ClientRegistrationForm,
    ClientProfileForm, HealthConditionsForm, ProductSaleForm,
)

from .emails import start_or_resend_verification, MAX_ATTEMPTS, ResendNotAllowed, RESEND_COOLDOWN_SEC

User = get_user_model()

RATE_LIMITS = {
    "begin": {"email": (5, 600), "ip": (20, 600)},
    "resend": {"email": (5, 600), "ip": (20, 600)},
    "confirm": {"email": (10, 600), "ip": (30, 600)},
}
RATE_LIMIT_PREFIX = "accounts:verify"
logger = logging.getLogger(__name__)


def _client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
        if ip:
            return ip
    return request.META.get("REMOTE_ADDR", "") or "unknown"


def _rate_limit_key(action: str, identifier: str) -> str:
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
    return f"{RATE_LIMIT_PREFIX}:{action}:{digest}"


def _limit_hit(action: str, identifier: str, limit: int, window: int) -> bool:
    if limit <= 0 or window <= 0:
        return False
    key = _rate_limit_key(action, identifier)
    try:
        added = cache.add(key, 1, window)
        if added:
            return False
        value = cache.incr(key)
    except Exception:
        cache.set(key, 1, window)
        return False
    return value > limit


def _is_rate_limited(action: str, email: str, ip: str) -> bool:
    cfg = RATE_LIMITS.get(action, {})
    normalized_email = (email or "").strip().lower()
    limited = False
    email_limit = cfg.get("email")
    if normalized_email and email_limit:
        limited = limited or _limit_hit(action, f"email:{normalized_email}", *email_limit)
    ip_limit = cfg.get("ip")
    if ip and ip_limit:
        limited = limited or _limit_hit(action, f"ip:{ip}", *ip_limit)
    return limited

# =========================
# Аутентификация и доступ
# =========================
class RoleBasedLoginView(LoginView):
    """
    Логин с редиректами по ролям:
      • staff/superuser → /admin
      • Master → master_dashboard
      • Client → mainmenu
    """
    template_name = "registration/login.html"

    def get_success_url(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return reverse("admin:index")

        try:
            up = user.userprofile
        except UserProfile.DoesNotExist:
            return super().get_success_url()
        role_names = set(
            up.userrole_set.select_related("role").values_list("role__name", flat=True)
        )
        if "Master" in role_names:
            return reverse("master_dashboard")
        if "Client" in role_names:
            return reverse("mainmenu")

        return super().get_success_url()


class RoleRequiredMixin(LoginRequiredMixin):
    """
    Ограничение доступа по конкретной роли.
    """
    required_role: str | None = None

    def dispatch(self, request, *args, **kwargs):
        if self.required_role and not request.user.userrole_set.filter(role__name=self.required_role).exists():
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


# =========================
# Главная клиента (каталог)
# =========================
class MainMenuView(LoginRequiredMixin, TemplateView):
    template_name = "client/mainmenu.html"
    login_url = reverse_lazy("login")
    redirect_field_name = "next"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.userrole_set.filter(role__name="Client").exists():
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["stripe_public_key"] = settings.STRIPE_PUBLIC_KEY
        return ctx


# =========================
# Личный кабинет клиента
# =========================
class ClientDashboardView(LoginRequiredMixin, TemplateView):
    """
    GET  → страница и данные
    POST → сохранение профиля (User + UserProfile)
    """
    template_name = "client/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        now = timezone.now()

        # профиль может отсутствовать → None
        ctx["profile"] = getattr(user, "userprofile", None)
        ctx["now"] = now

        # быстрые действия — список услуг
        ctx["services"] = Service.objects.filter(is_active=True).order_by("name")

        # подзапрос на последний статус записи
        latest_status = (
            AppointmentStatusHistory.objects.filter(appointment_id=OuterRef("pk"))
            .order_by("-set_at")
            .values("status__name")[:1]
        )

        # все записи клиента (для статистики/истории)
        items_prefetch = Prefetch(
            "items",
            queryset=AppointmentItem.objects.select_related("service", "master__user").order_by("start_time"),
        )

        qs = (
            Appointment.objects
            .filter(client=getattr(user, "userprofile", None))
            .select_related("payment_status")
            .prefetch_related(items_prefetch)
            .annotate(current_status=Subquery(latest_status))
            .order_by("-start_time")
        )
        ctx["appointments"] = qs

        # прошлые и будущие
        ctx["recent_appointments"] = qs.filter(start_time__lt=now)[:5]

        # 🔹 все будущие (по возрастанию), исключая отменённые
        upcoming_qs = (
            qs.filter(start_time__gte=now)
              .exclude(current_status="Cancelled")
              .order_by("start_time")
        )
        ctx["upcoming_appointments"] = upcoming_qs
        ctx["next_appointment"] = upcoming_qs.first()  # для обратной совместимости

        # статистика по месяцам (для графика)
        month_counts = (
            qs.filter(start_time__year=now.year)
              .annotate(month=TruncMonth("start_time"))
              .values("month")
              .annotate(cnt=Count("id"))
              .order_by("month")
        )
        ctx["chart_labels"] = [m["month"].strftime("%b") for m in month_counts]
        ctx["chart_data"] = [m["cnt"] for m in month_counts]

        ctx["stripe_public_key"] = settings.STRIPE_PUBLIC_KEY

        return ctx

    def post(self, request, *args, **kwargs):
        """
        Форма профиля (вкладка Profile).
        Поля: first_name, last_name, email, phone, birth_date (YYYY-MM-DD).
        """
        form = ClientProfileForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Профиль обновлён.")
            return redirect(reverse("dashboard") + "#profile")

        ctx = self.get_context_data()
        ctx["profile_form_errors"] = form.errors
        return self.render_to_response(ctx, status=400)


# =========================
# Кабинет мастера
# =========================
class MasterDashboardView(RoleRequiredMixin, TemplateView):
    required_role = "Master"
    template_name = "master/dashboard.html"


class ProductSalesView(RoleRequiredMixin, TemplateView):
    """
    Dashboard for employees to register retail product sales and review inventory.
    """
    required_role = "Master"
    template_name = "master/product_sales.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_staff or request.user.is_superuser:
            return TemplateView.dispatch(self, request, *args, **kwargs)
        return super().dispatch(request, *args, **kwargs)

    def _employee_profile(self) -> UserProfile:
        profile = getattr(self.request.user, "userprofile", None)
        if profile is None:
            raise PermissionDenied("User profile is required to record product sales.")
        return profile

    def _build_form(self, data=None) -> ProductSaleForm:
        profile = getattr(self.request.user, "userprofile", None)
        return ProductSaleForm(data=data, employee_profile=profile)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        form = kwargs.get("form") or self._build_form()
        ctx["form"] = form

        inventory_qs = Product.objects.select_related("category").order_by("name")
        ctx["inventory"] = inventory_qs
        ctx["low_stock_products"] = inventory_qs.filter(
            low_stock_threshold__gt=0,
            quantity_in_stock__lte=F("low_stock_threshold"),
        )
        ctx["product_price_map"] = {
            str(product.pk): f"{product.price:.2f}"
            for product in inventory_qs
        }

        sales_qs = ProductSale.objects.select_related(
            "product__category",
            "sold_by__user",
            "client__user",
        ).order_by("-sold_at", "-id")
        ctx["recent_sales"] = sales_qs[:25]

        today = timezone.localdate(timezone.now())
        month_start = today.replace(day=1)

        totals_qs = ProductSale.objects.all()
        ctx["today_total"] = totals_qs.filter(sold_at__date=today).aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")
        ctx["month_total"] = totals_qs.filter(sold_at__date__gte=month_start).aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")

        inventory_value = Decimal("0.00")
        for product in inventory_qs:
            inventory_value += (product.price or Decimal("0.00")) * Decimal(product.quantity_in_stock or 0)
        ctx["inventory_value"] = inventory_value

        return ctx

    def post(self, request, *args, **kwargs):
        try:
            profile = self._employee_profile()
        except PermissionDenied as exc:
            messages.error(request, str(exc))
            return redirect("product-sales")

        form = self._build_form(data=request.POST)
        if form.is_valid():
            try:
                sale = form.save(employee_profile=profile)
            except ValidationError as exc:
                if hasattr(exc, "message_dict"):
                    for field, messages_list in exc.message_dict.items():
                        for msg in messages_list:
                            if field in form.fields:
                                form.add_error(field, msg)
                            else:
                                form.add_error(None, msg)
                else:
                    for msg in getattr(exc, "messages", [str(exc)]):
                        form.add_error(None, msg)
            else:
                messages.success(
                    request,
                    f"Recorded sale: {sale.product.name} × {sale.quantity} for ${sale.total_amount}.",
                )
                return redirect("product-sales")

        return self.render_to_response(self.get_context_data(form=form), status=400)


# =========================
# Список записей клиента
# =========================
class ClientAppointmentsListView(RoleRequiredMixin, ListView):
    required_role = "Client"
    model = Appointment
    template_name = "client/appointments_list.html"
    paginate_by = 10

    def get_queryset(self):
        return (
            Appointment.objects
            .filter(client=self.request.user.userprofile)
            .prefetch_related(
                Prefetch(
                    "items",
                    queryset=AppointmentItem.objects.select_related("service", "master__user").order_by("start_time"),
                )
            )
            .order_by("-start_time")
        )


# =========================
# Регистрация клиента (AJAX-friendly)
# =========================
class ClientRegisterView(CreateView):
    form_class = ClientRegistrationForm
    template_name = "registration/register_popup.html"
    success_url = None  # вычисляем в get_success_url()

    def form_valid(self, form):
        user = None
        verification_required = False
        try:
            with transaction.atomic():
                user = form.save()

                profile = getattr(user, "userprofile", None)
                if profile and profile.source != "online":
                    profile.source = "online"
                    profile.save(update_fields=["source"])

                try:
                    start_or_resend_verification(user, purpose=EmailVerification.PURPOSE_REGISTER)
                except ResendNotAllowed:
                    verification_required = True
                else:
                    verification_required = True
        except Exception as exc:
            logger.exception("Failed to start email verification during registration", exc_info=exc)
            if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse(
                    {
                        "ok": False,
                        "error": "Unable to complete registration right now. Please try again later.",
                    },
                    status=500,
                )
            raise

        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            payload = {
                "ok": True,
                "status": "ok",
                "username": user.username if user else "",
                "redirect": self.get_success_url(),
            }
            if verification_required and user:
                payload["verification"] = "required"
                payload["email"] = user.email
            return JsonResponse(payload, status=201)

        self.object = user
        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form):
        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse(form.errors, status=400)
        return super().form_invalid(form)

    def get_success_url(self):
        return f"{reverse('login')}?registered=1"


@require_POST
@csrf_protect
def api_verification_begin(request):
    email = (request.POST.get("email") or "").strip().lower()
    if not email:
        return HttpResponseBadRequest("email required")

    ip = _client_ip(request)
    if _is_rate_limited("begin", email, ip):
        return JsonResponse({"ok": False, "error": "Too many requests. Try again shortly."}, status=429)

    user = User.objects.filter(email__iexact=email).first()
    if not user:
        return JsonResponse({"ok": True})

    profile = getattr(user, "userprofile", None)
    if profile and profile.email_verified_at:
        return JsonResponse({"ok": True, "verified": True})

    try:
        start_or_resend_verification(user, purpose=EmailVerification.PURPOSE_REGISTER)
    except ResendNotAllowed as exc:
        retry_after = getattr(exc, "retry_after", RESEND_COOLDOWN_SEC)
        return JsonResponse(
            {
                "ok": False,
                "error": "Please wait before requesting another code.",
                "retry_after": retry_after if retry_after is not None else RESEND_COOLDOWN_SEC,
            },
            status=429,
        )
    except Exception as exc:
        logger.exception("Failed to begin email verification for %s", email, exc_info=exc)
        return JsonResponse({"ok": False, "error": "Unable to send verification code."}, status=500)

    return JsonResponse({"ok": True})


@require_POST
@csrf_protect
def api_verification_confirm(request):
    email = (request.POST.get("email") or "").strip().lower()
    code = (request.POST.get("code") or "").strip()
    if not email or not code or len(code) != 6 or not code.isdigit():
        return HttpResponseBadRequest("invalid payload")

    ip = _client_ip(request)
    if _is_rate_limited("confirm", email, ip):
        return JsonResponse({"ok": False, "error": "Too many attempts. Try again later."}, status=429)

    user = (
        User.objects.select_related("userprofile")
        .filter(email__iexact=email)
        .first()
    )
    if not user:
        return JsonResponse({"ok": False, "error": "invalid code"}, status=400)

    with transaction.atomic():
        verification = (
            EmailVerification.objects.select_for_update()
            .filter(user=user, purpose=EmailVerification.PURPOSE_REGISTER, is_used=False)
            .order_by("-created_at")
            .first()
        )
        if not verification or verification.is_expired():
            return JsonResponse({"ok": False, "error": "code expired"}, status=400)

        if verification.attempts >= MAX_ATTEMPTS:
            return JsonResponse({"ok": False, "error": "too many attempts"}, status=429)

        if verification.code != code:
            verification.attempts += 1
            verification.save(update_fields=["attempts"])
            return JsonResponse({"ok": False, "error": "invalid code"}, status=400)

        verification.is_used = True
        verification.attempts = min(verification.attempts + 1, MAX_ATTEMPTS)
        verification.save(update_fields=["is_used", "attempts"])

        profile = getattr(user, "userprofile", None)
        if profile and not profile.email_verified_at:
            profile.email_verified_at = timezone.now()
            profile.save(update_fields=["email_verified_at"])

    backend = getattr(user, "backend", None)
    if not backend:
        backends = getattr(settings, "AUTHENTICATION_BACKENDS", None) or ["django.contrib.auth.backends.ModelBackend"]
        backend = backends[0]
    login(request, user, backend=backend)

    return JsonResponse({"ok": True})


@require_POST
@csrf_protect
def api_verification_resend(request):
    email = (request.POST.get("email") or "").strip().lower()
    if not email:
        return HttpResponseBadRequest("email required")

    ip = _client_ip(request)
    if _is_rate_limited("resend", email, ip):
        return JsonResponse({"ok": False, "error": "Too many requests. Try again shortly."}, status=429)

    user = User.objects.filter(email__iexact=email).first()
    if not user:
        return JsonResponse({"ok": True})

    profile = getattr(user, "userprofile", None)
    if profile and profile.email_verified_at:
        return JsonResponse({"ok": True, "verified": True})

    try:
        start_or_resend_verification(user, purpose=EmailVerification.PURPOSE_REGISTER)
    except ResendNotAllowed as exc:
        retry_after = getattr(exc, "retry_after", RESEND_COOLDOWN_SEC)
        return JsonResponse(
            {
                "ok": False,
                "error": "Please wait before requesting another code.",
                "retry_after": retry_after if retry_after is not None else RESEND_COOLDOWN_SEC,
            },
            status=429,
        )
    except Exception as exc:
        logger.exception("Failed to resend email verification for %s", email, exc_info=exc)
        return JsonResponse({"ok": False, "error": "Unable to send verification code."}, status=500)

    return JsonResponse({"ok": True})

@login_required
def health_edit(request):
    profile = getattr(request.user, "userprofile", None)
    if not profile:
        # На всякий – создадим профиль
        from core.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = HealthConditionsForm(request.POST)
        if form.is_valid():
            data = form.to_json()
            data["consent_at"] = timezone.now().isoformat()
            profile.health_conditions = data
            profile.save()
            return redirect("health-view")
    else:
        form = HealthConditionsForm()
        form.load_initial_from_json(profile.health_conditions or {})
    return render(request, "client/health_edit.html", {"form": form})

@login_required
def health_view(request):
    profile = getattr(request.user, "userprofile", None)
    if not profile:
        from core.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
    return render(request, "client/health_view.html", {"profile": profile})
