import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Appointment, ClientFile, PaymentStatus, UserProfile


class AdminClientFilesViewTests(TestCase):
    """
    Ensures the admin user profile view surfaces all client files with appointment metadata.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_dir = tempfile.mkdtemp(prefix="client-files-")
        cls._original_storage = ClientFile._meta.get_field("file").storage
        ClientFile._meta.get_field("file").storage = FileSystemStorage(location=cls._media_dir)

    @classmethod
    def tearDownClass(cls):
        ClientFile._meta.get_field("file").storage = cls._original_storage
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

        cls.payment_status = PaymentStatus.objects.create(name="Files Pending")

        cls.appointment = Appointment.objects.create(
            client=cls.client_profile,
            payment_status=cls.payment_status,
            start_time=timezone.now(),
        )

        ClientFile.objects.create(
            user=cls.client_profile,
            appointment=cls.appointment,
            file=SimpleUploadedFile("before-session.jpg", b"\x47\x49\x46", content_type="image/jpeg"),
            kind=ClientFile.KIND_BEFORE,
            description="Before session reference",
            uploaded_by=ClientFile.ADMIN,
            uploaded_by_user=cls.admin_user,
        )

        ClientFile.objects.create(
            user=cls.client_profile,
            file=SimpleUploadedFile("consent-form.pdf", b"%PDF", content_type="application/pdf"),
            kind=ClientFile.KIND_OTHER,
            description="Signed consent form",
            uploaded_by=ClientFile.USER,
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
