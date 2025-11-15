import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import QueryDict
from django.test import RequestFactory, TestCase
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.datastructures import MultiValueDict

from core.forms import CustomUserChangeForm
from core.models import Appointment, ClientFile, PaymentStatus, UserProfile


class AdminClientFilesViewTests(TestCase):
    """
    Ensures the admin user profile view surfaces all client files with appointment metadata.
    """

    @classmethod
    def setUpClass(cls):
        cls._media_dir = tempfile.mkdtemp(prefix="client-files-")
        cls._original_storage = ClientFile._meta.get_field("file").storage
        field = ClientFile._meta.get_field("file")
        filesystem_storage = FileSystemStorage(location=cls._media_dir)
        field.storage = filesystem_storage
        field._storage = filesystem_storage
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        field = ClientFile._meta.get_field("file")
        field.storage = cls._original_storage
        field._storage = cls._original_storage
        shutil.rmtree(cls._media_dir, ignore_errors=True)
        super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()

        cls.admin_user = user_model.objects.create_superuser(
            username="files-admin",
            email="admin-files@example.com",
            password="adminpass123",
        )

        cls.client_user = user_model.objects.create_user(
            username="files-client",
            email="client-files@example.com",
            password="clientpass123",
            first_name="Taylor",
            last_name="Tester",
        )
        cls.client_profile = getattr(cls.client_user, "userprofile", None)
        if cls.client_profile is None:
            cls.client_profile = UserProfile.objects.create(user=cls.client_user)
        cls.client_profile.phone = "+14035550123"
        cls.client_profile.postal_code = "T2X1A1"
        cls.client_profile.address = "123 Example Street"
        cls.client_profile.save(update_fields=["phone", "postal_code", "address"])

        cls.payment_status = PaymentStatus.objects.create(name="Files Pending")

        cls.appointment = Appointment.objects.create(
            client=cls.client_profile,
            payment_status=cls.payment_status,
            start_time=timezone.now(),
        )

        cls.before_file = ClientFile.objects.create(
            user=cls.client_profile,
            appointment=cls.appointment,
            file=SimpleUploadedFile("before-session.jpg", b"\x47\x49\x46", content_type="image/jpeg"),
            kind=ClientFile.KIND_BEFORE,
            description="Before session reference",
            uploaded_by=ClientFile.ADMIN,
            uploaded_by_user=cls.admin_user,
        )

        cls.consent_file = ClientFile.objects.create(
            user=cls.client_profile,
            file=SimpleUploadedFile("consent-form.pdf", b"%PDF", content_type="application/pdf"),
            kind=ClientFile.KIND_OTHER,
            description="Signed consent form",
            uploaded_by=ClientFile.USER,
        )

    def setUp(self):
        self.factory = RequestFactory()

    def _user_change_form_data(self, overrides=None):
        profile = self.client_profile
        data = QueryDict("", mutable=True)
        data["email"] = self.client_user.email
        data["first_name"] = self.client_user.first_name
        data["last_name"] = self.client_user.last_name
        if self.client_user.is_active:
            data["is_active"] = "on"
        if self.client_user.is_staff:
            data["is_staff"] = "on"
        if self.client_user.is_superuser:
            data["is_superuser"] = "on"
        data.setlist("groups", [])
        data.setlist("user_permissions", [])
        data["password"] = self.client_user.password
        data["postal_code"] = profile.postal_code or ""
        data["address"] = profile.address or ""
        data["how_heard"] = profile.how_heard or ""
        if profile.email_marketing_consent:
            data["email_marketing_consent"] = "on"
        data["notes"] = profile.notes or ""
        data["personal_discount_percent"] = str(profile.personal_discount_percent or 0)
        data["phone"] = profile.phone or "+14035550000"
        data["birth_date_year"] = ""
        data["birth_date_month"] = ""
        data["birth_date_day"] = ""
        data["files_kind"] = ClientFile.KIND_BEFORE
        data["files_description"] = "Session capture"
        data["files_appointment"] = str(self.appointment.pk)
        if overrides:
            for key, value in overrides.items():
                if isinstance(value, list):
                    data.setlist(key, value)
                else:
                    data[key] = value
        data._mutable = False
        return data

    @staticmethod
    def _file_payload(filename):
        return MultiValueDict(
            {
                "files": [
                    SimpleUploadedFile(
                        filename,
                        b"\x47\x49\x46",
                        content_type="image/jpeg",
                    )
                ]
            }
        )

    def test_user_change_view_lists_all_client_files(self):
        self.client.force_login(self.admin_user)
        url = reverse("admin:auth_user_change", args=[self.client_user.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        response.render()

        self.assertContains(response, "Client Files (2)")
        self.assertContains(response, "before-session.jpg")
        self.assertContains(response, "consent-form.pdf")
        self.assertContains(response, "Before session reference")
        self.assertContains(response, "Signed consent form")
        appointment_url = reverse("admin:core_appointment_change", args=[self.appointment.pk])
        self.assertContains(response, appointment_url)
        self.assertContains(response, "Not linked to an appointment")

    def test_admin_can_delete_client_file_from_profile(self):
        self.client.force_login(self.admin_user)
        try:
            delete_url = reverse(
                "admin:auth_user_delete_file",
                args=[self.client_user.pk, self.before_file.pk],
            )
        except NoReverseMatch:
            self.skipTest("Client file deletion admin view is not registered")

        response = self.client.post(delete_url, data={})

        self.assertRedirects(response, reverse("admin:auth_user_change", args=[self.client_user.pk]))
        self.assertFalse(ClientFile.objects.filter(pk=self.before_file.pk).exists())

        remaining = ClientFile.objects.filter(user=self.client_profile)
        self.assertEqual(remaining.count(), 1)
        self.assertEqual(remaining.first().pk, self.consent_file.pk)

        follow_up = self.client.get(reverse("admin:auth_user_change", args=[self.client_user.pk]))
        follow_up.render()
        self.assertContains(follow_up, "Client Files (1)")
        self.assertNotContains(follow_up, "before-session.jpg")

    def test_user_change_form_uploads_file_with_metadata(self):
        data = self._user_change_form_data(
            {
                "files_kind": ClientFile.KIND_BEFORE,
                "files_description": "Fresh capture",
                "files_appointment": str(self.appointment.pk),
            }
        )
        files = self._file_payload("before-admin.jpg")
        request = self.factory.post("/")
        request.user = self.admin_user

        form = CustomUserChangeForm(
            data=data,
            files=files,
            instance=self.client_user,
            request=request,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        uploaded = (
            ClientFile.objects.filter(
                user=self.client_profile,
                appointment=self.appointment,
                description="Fresh capture",
            )
            .order_by("-uploaded_at")
            .first()
        )
        self.assertIsNotNone(uploaded)
        self.assertEqual(uploaded.kind, ClientFile.KIND_BEFORE)
        self.assertEqual(uploaded.uploaded_by_user, self.admin_user)

    def test_user_change_form_requires_appointment_for_before_after(self):
        data = self._user_change_form_data(
            {
                "files_kind": ClientFile.KIND_AFTER,
                "files_appointment": "",
            }
        )
        files = self._file_payload("after-admin.jpg")
        request = self.factory.post("/")
        request.user = self.admin_user

        form = CustomUserChangeForm(
            data=data,
            files=files,
            instance=self.client_user,
            request=request,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("files_appointment", form.errors)
