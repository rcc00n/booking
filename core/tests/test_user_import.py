from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from core.models import Role, UserProfile, UserRole
from core.services.user_import import (
    UserImportSchemaError,
    import_users_from_file,
)


class UserImportServiceTests(TestCase):
    def setUp(self):
        self.User = get_user_model()

    def test_successful_csv_import_creates_user_profile_and_role(self):
        data = (
            "Username,Email,Password,First name,Last name,Phone\n"
            "newuser,new.user@example.com,SecurePa55!,New,User,+1 (555) 000-1111\n"
        )
        uploaded = SimpleUploadedFile("users.csv", data.encode("utf-8"), content_type="text/csv")

        result = import_users_from_file(uploaded)

        self.assertEqual(result.created, 1)
        self.assertEqual(result.errors, [])

        user = self.User.objects.get(username="newuser")
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.source, "offline")
        self.assertEqual(profile.phone, "+15550001111")
        role = Role.objects.get(name="Client")
        self.assertTrue(UserRole.objects.filter(user=profile, role=role).exists())

    def test_duplicate_username_is_reported_as_error(self):
        self.User.objects.create_user(
            username="existing",
            email="existing@example.com",
            password="StrongPass#1",
            first_name="Old",
            last_name="User",
        )
        data = (
            "Username,Email,Password,First name,Last name,Phone\n"
            "existing,new@example.com,SecurePa55!,New,User,+1 (555) 222-3333\n"
        )
        uploaded = SimpleUploadedFile("users.csv", data.encode("utf-8"), content_type="text/csv")

        result = import_users_from_file(uploaded)

        self.assertEqual(result.created, 0)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("already exists", result.errors[0].message)

    def test_missing_required_column_raises_schema_error(self):
        data = "Username,Email,Password,First name\nuser1,user1@example.com,SecurePa55!,User\n"
        uploaded = SimpleUploadedFile("users.csv", data.encode("utf-8"), content_type="text/csv")

        with self.assertRaises(UserImportSchemaError):
            import_users_from_file(uploaded)

    def test_xlsx_import(self):
        try:
            import openpyxl
        except ImportError:  # pragma: no cover
            self.skipTest("openpyxl not installed")

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.append(["Username", "Email", "Password", "First name", "Last name", "Phone"])
        sheet.append(["exceluser", "excel.user@example.com", "SecurePa55!", "Excel", "User", "+1 555 444 5555"])
        buffer = BytesIO()
        workbook.save(buffer)
        workbook.close()
        uploaded = SimpleUploadedFile(
            "users.xlsx",
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        result = import_users_from_file(uploaded)

        self.assertEqual(result.created, 1)
        self.assertFalse(result.errors)
        self.assertTrue(self.User.objects.filter(username="exceluser").exists())

        profile = UserProfile.objects.get(user__username="exceluser")
        self.assertEqual(profile.phone, "+15554445555")
