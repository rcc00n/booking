from django.db.utils import OperationalError, ProgrammingError
from django.templatetags.static import static

from core.models import SiteBranding


DEFAULT_LOGO_PATH = "img/malva-dashboard-logo.png"
DEFAULT_DESKTOP_SIZE = 44
DEFAULT_MOBILE_SIZE = 42


def _load_branding():
    """
    Safely pull the latest active branding record.
    Shields template rendering from missing tables during migrations.
    """
    try:
        branding = (
            SiteBranding.objects.filter(is_active=True)
            .order_by("-updated_at", "-id")
            .first()
        )
        if branding:
            return branding
        return SiteBranding.objects.order_by("-updated_at", "-id").first()
    except (ProgrammingError, OperationalError):
        return None


def site_branding(request):
    branding = _load_branding()

    logo_url = static(DEFAULT_LOGO_PATH)
    logo_alt = "Malva Booking"
    desktop_size = DEFAULT_DESKTOP_SIZE
    mobile_size = DEFAULT_MOBILE_SIZE

    if branding:
        logo_alt = branding.logo_alt_text or logo_alt
        desktop_size = branding.logo_width or desktop_size
        mobile_size = branding.logo_width_mobile or branding.logo_width or mobile_size
        try:
            if branding.logo and getattr(branding.logo, "url", ""):
                logo_url = branding.logo.url
        except Exception:
            # Fall back silently if storage cannot resolve the URL yet.
            pass

    return {
        "site_branding": {
            "logo_url": logo_url,
            "logo_alt": logo_alt,
            "logo_size": desktop_size,
            "logo_size_mobile": mobile_size,
        }
    }
