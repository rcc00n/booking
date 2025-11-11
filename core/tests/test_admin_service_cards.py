import json
import re
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import (
    MasterProfile,
    MasterRoom,
    Service,
    ServiceCategory,
    ServiceMaster,
    UserProfile,
)


class ServiceAdminListTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass123",
        )
        UserProfile.objects.get_or_create(user=self.superuser, defaults={"phone": "+10000000000"})

        self.client.force_login(self.superuser)
        self.url = reverse("admin:core_service_changelist")

        self.category_skin = ServiceCategory.objects.create(name="Skin Care")
        self.category_body = ServiceCategory.objects.create(name="Body Treatments")

        self.active_service = Service.objects.create(
            name="Hydra Facial",
            description="Glow boost facial",
            category=self.category_skin,
            base_price="120.00",
            duration_min=60,
            extra_time_min=15,
        )
        self.inactive_service = Service.objects.create(
            name="Relax Massage",
            description="Soothing massage",
            category=self.category_body,
            base_price="80.00",
            duration_min=90,
            extra_time_min=0,
        )
        self.uncategorised_service = Service.objects.create(
            name="Custom Consultation",
            description="Consult",
            category=None,
            base_price="0.00",
            duration_min=30,
            extra_time_min=0,
        )

        master_user = User.objects.create_user(
            username="master1",
            email="master1@example.com",
            password="password123",
            first_name="Alice",
            last_name="Master",
        )
        master_profile, _ = UserProfile.objects.get_or_create(user=master_user, defaults={"phone": "+15550123456"})
        self.room = MasterRoom.objects.create(room="Room 1")
        self.active_service.allowed_rooms.add(self.room)
        master = MasterProfile.objects.create(user=master_profile)
        ServiceMaster.objects.create(master=master, service=self.active_service)

    def _names(self, response):
        return [obj.name for obj in response.context["cl"].result_list]

    def test_default_ordering(self):
        response = self.client.get(self.url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._names(response), sorted(self._names(response)))

    def test_filter_by_category(self):
        response = self.client.get(self.url, {"svc_category": str(self.category_skin.pk)}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._names(response), [self.active_service.name])

    def test_filter_uncategorised(self):
        response = self.client.get(self.url, {"svc_category": "none"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._names(response), [self.uncategorised_service.name])

    def test_search_service_name(self):
        response = self.client.get(self.url, {"q": "Hydra"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._names(response), [self.active_service.name])

    def test_search_service_description(self):
        response = self.client.get(self.url, {"q": "soothing"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._names(response), [self.inactive_service.name])

    def test_search_category_name(self):
        response = self.client.get(self.url, {"q": "skin"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._names(response), [self.active_service.name])

    def test_category_options_in_context(self):
        response = self.client.get(self.url, follow=True)
        self.assertEqual(response.status_code, 200)
        options = response.context["category_options"]
        values = {opt["value"] for opt in options}
        self.assertIn("", values)
        self.assertIn("none", values)

    def test_currency_symbol_from_settings(self):
        with self.settings(STRIPE_CURRENCY="cad"):
            response = self.client.get(self.url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["currency_symbol"], "CA$")

    def test_pagination_second_page(self):
        for idx in range(12):
            Service.objects.create(
                name=f"Extra Service {idx}",
                description="extra",
                category=self.category_skin,
                base_price="50.00",
                duration_min=30,
                extra_time_min=0,
            )

        response = self.client.get(self.url, {"p": 2}, follow=True)
        self.assertEqual(response.status_code, 200)
        cl = response.context["cl"]
        self.assertEqual(cl.list_per_page, 10)
        expected = Service.objects.count() - cl.list_per_page
        self.assertEqual(len(cl.result_list), expected)

    def test_pagination_links_preserve_filters(self):
        for idx in range(12):
            Service.objects.create(
                name=f"Extra Filter Service {idx}",
                description="extra",
                category=self.category_skin,
                base_price="65.00",
                duration_min=30,
                extra_time_min=0,
            )

        response = self.client.get(self.url, {"svc_category": str(self.category_skin.pk)}, follow=True)
        self.assertEqual(response.status_code, 200)
        pagination_ctx = response.context["svc_pagination"]
        self.assertTrue(pagination_ctx["has_next"])
        self.assertFalse(pagination_ctx["has_previous"])
        self.assertEqual(pagination_ctx["next_page"], 2)
        self.assertEqual(pagination_ctx["current_page"], 1)
        html = response.content.decode()
        next_link = re.search(r'href="([^"]+)"[^>]*>\s*Next\s*<', html)
        self.assertIsNotNone(next_link)
        self.assertIn(f"svc_category={self.category_skin.pk}", next_link.group(1))
        self.assertIn("p=2", next_link.group(1))

        response_page2 = self.client.get(
            self.url, {"svc_category": str(self.category_skin.pk), "p": 2}, follow=True
        )
        self.assertEqual(response_page2.status_code, 200)
        pagination_page2 = response_page2.context["svc_pagination"]
        self.assertTrue(pagination_page2["has_previous"])
        self.assertFalse(pagination_page2["has_next"])
        self.assertEqual(pagination_page2["previous_page"], 1)
        self.assertEqual(pagination_page2["current_page"], 2)
        html_page2 = response_page2.content.decode()
        prev_link = re.search(r'href="([^"]+)"[^>]*>\s*Previous\s*<', html_page2)
        self.assertIsNotNone(prev_link)
        self.assertIn(f"svc_category={self.category_skin.pk}", prev_link.group(1))
        self.assertNotIn("p=1", prev_link.group(1))

    def test_change_links_include_preserved_filters(self):
        response = self.client.get(self.url, {"svc_category": str(self.category_skin.pk)}, follow=True)
        self.assertEqual(response.status_code, 200)
        encoded_filters = quote(f"svc_category={self.category_skin.pk}")
        html = response.content.decode()
        self.assertIn(f"_changelist_filters={encoded_filters}", html)

    def test_save_redirect_preserves_category_filter(self):
        filter_qs = f"svc_category={self.category_skin.pk}"
        encoded_filters = quote(filter_qs)
        change_url = reverse("admin:core_service_change", args=[self.active_service.pk])
        change_url_with_filters = f"{change_url}?_changelist_filters={encoded_filters}"
        get_response = self.client.get(change_url_with_filters)
        self.assertEqual(get_response.status_code, 200)

        post_data = {
            "name": self.active_service.name,
            "description": self.active_service.description,
            "category": str(self.category_skin.pk),
            "base_price": "120.00",
            "duration_min": "60",
            "extra_time_min": "15",
            "allowed_rooms": [str(self.room.pk)],
            "pre_appointment_forms": [],
            "_save": "Save",
            "_changelist_filters": filter_qs,
        }

        response = self.client.post(change_url_with_filters, post_data, follow=False)
        expected_redirect = f"{reverse('admin:core_service_changelist')}?{filter_qs}"
        self.assertRedirects(response, expected_redirect, fetch_redirect_response=False)
        self.active_service.refresh_from_db()
        self.assertFalse(self.active_service.is_active)
    def test_ajax_fragment_search(self):
        response = self.client.get(self.url, {"q": "Hydra"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertIn("Hydra Facial", payload["html"])
        self.assertNotIn("Relax Massage", payload["html"])
        meta = payload["meta"]
        self.assertEqual(meta["current_page"], 1)
        self.assertEqual(meta["result_count"], 1)
        self.assertEqual(meta["start_index"], 1)
        self.assertEqual(meta["end_index"], 1)
        self.assertFalse(meta["has_previous"])
        self.assertFalse(meta["has_next"])
        self.assertEqual(meta["search_term"], "Hydra")
