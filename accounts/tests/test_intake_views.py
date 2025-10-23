from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import (
    ClientIntakeAssignment,
    ClientIntakeForm,
    ClientIntakeFormSubmission,
    Role,
    UserProfile,
    UserRole,
)


class ClientIntakeViewsTests(TestCase):
    def setUp(self):
        self.form = ClientIntakeForm.objects.create(
            name="Client Intake",
            slug="client-intake",
            is_universal=True,
            schema={
                "meta": {},
                "sections": [
                    {
                        "id": "sec",
                        "title": "Basics",
                        "fields": [
                            {
                                "id": "f1",
                                "key": "full_name",
                                "label": "Full name",
                                "type": "text",
                                "required": True,
                            },
                        ],
                    }
                ],
            },
        )
        self.user = get_user_model().objects.create_user(
            username="client-view",
            email="client-view@example.com",
            password="pass123",
        )
        self.profile, _ = UserProfile.objects.get_or_create(user=self.user)
        self.role, _ = Role.objects.get_or_create(name="Client")
        UserRole.objects.create(user=self.profile, role=self.role)
        self.assignment = ClientIntakeAssignment.objects.get(client=self.profile, form=self.form)

    def test_assignments_view_lists_universal_form(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("client-intake-forms"))
        self.assertEqual(response.status_code, 200)
        assignments = response.context["assignments"]
        self.assertEqual(len(assignments), 1)
        self.assertEqual(assignments[0]["assignment"].pk, self.assignment.pk)

    def test_detail_view_persists_submission(self):
        self.client.force_login(self.user)
        url = reverse("client-intake-form-detail", args=[self.assignment.pk])
        get_response = self.client.get(url)
        self.assertEqual(get_response.status_code, 200)

        payload = {
            "intake-full_name": "Alice Example",
        }
        post_response = self.client.post(url, payload)
        self.assertEqual(post_response.status_code, 302)

        submission = ClientIntakeFormSubmission.objects.get(assignment=self.assignment)
        self.assignment.refresh_from_db()
        self.assertTrue(self.assignment.is_completed)
        self.assertEqual(submission.data["full_name"], "Alice Example")
