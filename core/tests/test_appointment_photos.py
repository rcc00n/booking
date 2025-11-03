import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models import Appointment, ClientFile, PaymentStatus, UserProfile


class AppointmentPhotoAdminTests(TestCase):
    """
    Covers the admin-facing workflow for Before/After photos.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_dir = tempfile.mkdtemp(prefix="appt-photos-")
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
            username="photo-admin",
            email="photo-admin@example.com",
            password="testpass123",
        )

        cls.client_user = user_model.objects.create_user(
            username="photo-client",
            email="client@example.com",
            password="clientpass123",
            first_name="Casey",
            last_name="Client",
        )
        cls.client_profile = getattr(cls.client_user, "userprofile", None)
        if cls.client_profile is None:
            cls.client_profile = UserProfile.objects.create(user=cls.client_user)

        cls.other_user = user_model.objects.create_user(
            username="photo-other",
            email="other@example.com",
            password="otherpass123",
        )
        cls.other_profile = getattr(cls.other_user, "userprofile", None)
        if cls.other_profile is None:
            cls.other_profile = UserProfile.objects.create(user=cls.other_user)

        cls.payment_status = PaymentStatus.objects.create(name="Test Not Paid")

    def _make_appointment(self):
        return Appointment.objects.create(
            client=self.client_profile,
            payment_status=self.payment_status,
        )

    @staticmethod
    def _fake_image(name="sample.jpg"):
        return SimpleUploadedFile(name, b"\x47\x49\x46\x38\x39\x61", content_type="image/jpeg")

    def test_client_file_aligns_with_appointment_client(self):
        appointment = self._make_appointment()
        file_obj = self._fake_image()

        attachment = ClientFile(
            user=self.other_profile,
            appointment=appointment,
            file=file_obj,
            kind=ClientFile.KIND_BEFORE,
        )

        self.assertNotEqual(appointment.client_id, self.other_profile.id)
        self.assertEqual(attachment.appointment_id, appointment.pk)
        self.assertEqual(attachment.user_id, self.other_profile.id)

        attachment.save()
        attachment.refresh_from_db()

        self.assertEqual(attachment.user_id, appointment.client_id)
        self.assertEqual(attachment.user, appointment.client)
        self.assertEqual(attachment.kind, ClientFile.KIND_BEFORE)

    def test_upload_view_creates_files(self):
        appointment = self._make_appointment()
        url = reverse("admin:core_appointment_upload_photos", args=[appointment.pk])

        self.client.force_login(self.admin_user)
        from django.test.client import BOUNDARY, MULTIPART_CONTENT, encode_multipart

        payload = {
            "kind": ClientFile.KIND_BEFORE,
            "description": "Session start",
            "files": [self._fake_image("before-1.jpg"), self._fake_image("before-2.jpg")],
        }
        multipart_data = encode_multipart(BOUNDARY, payload)

        response = self.client.generic("POST", url, multipart_data, content_type=MULTIPART_CONTENT)

        self.assertEqual(response.status_code, 302)
        expected_redirect = f"{reverse('admin:core_appointment_change', args=[appointment.pk])}#before-after"
        self.assertEqual(response.headers.get("Location"), expected_redirect)

        uploaded_payload = response.wsgi_request.FILES.getlist("files")
        self.assertTrue(uploaded_payload)

        from django.contrib.messages import get_messages

        error_messages = [m.message for m in get_messages(response.wsgi_request) if m.level_tag == "error"]
        self.assertFalse(error_messages, error_messages)

        files = ClientFile.objects.filter(appointment=appointment).order_by("uploaded_at")
        self.assertEqual(files.count(), 2)
        for uploaded in files:
            self.assertEqual(uploaded.user, appointment.client)
            self.assertEqual(uploaded.kind, ClientFile.KIND_BEFORE)
            self.assertEqual(uploaded.description, "Session start")
            self.assertEqual(uploaded.uploaded_by, ClientFile.ADMIN)
            self.assertEqual(uploaded.uploaded_by_user, self.admin_user)

    def test_delete_view_removes_file(self):
        appointment = self._make_appointment()
        file_record = ClientFile.objects.create(
            user=appointment.client,
            appointment=appointment,
            file=self._fake_image("after.jpg"),
            kind=ClientFile.KIND_AFTER,
            uploaded_by=ClientFile.ADMIN,
            uploaded_by_user=self.admin_user,
            description="Post session",
        )

        url = reverse("admin:core_appointment_delete_photo", args=[appointment.pk, file_record.pk])
        self.client.force_login(self.admin_user)
        response = self.client.post(url, data={"return_to_date": ""})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ClientFile.objects.filter(pk=file_record.pk).exists())
