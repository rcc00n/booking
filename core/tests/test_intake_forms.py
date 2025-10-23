from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Appointment,
    AppointmentItem,
    ClientIntakeAssignment,
    ClientIntakeForm,
    ClientIntakeFormSubmission,
    MasterProfile,
    Service,
    ServiceMaster,
    UserProfile,
)
from core.admin import CustomUserAdmin
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory


class IntakeFormBuilderTests(TestCase):
    def setUp(self):
        self.form = ClientIntakeForm.objects.create(
            name="Health Questionnaire",
            slug="health-questionnaire",
            schema={
                "sections": [
                    {
                        "id": "sec-1",
                        "title": "General",
                        "fields": [
                            {
                                "id": "fld-1",
                                "key": "full_name",
                                "label": "Full name",
                                "type": "text",
                                "required": True,
                                "placeholder": "Client full name",
                            },
                            {
                                "id": "fld-2",
                                "key": "consent",
                                "label": "Consent",
                                "type": "radio",
                                "required": True,
                                "choices": [
                                    {"value": "yes", "label": "Yes"},
                                    {"value": "no", "label": "No"},
                                ],
                            },
                        ],
                    },
                ],
                "meta": {"version": 1},
            },
        )

    def test_build_form_generates_expected_fields(self):
        django_form = self.form.build_bound_form()
        self.assertIn("full_name", django_form.fields)
        self.assertIn("consent", django_form.fields)
        self.assertTrue(django_form.fields["full_name"].required)
        self.assertEqual(django_form.fields["consent"].choices, [("yes", "Yes"), ("no", "No")])

    def test_validation_passes_with_correct_payload(self):
        payload = {"full_name": "Alice Example", "consent": "yes"}
        django_form = self.form.build_bound_form(data=payload)
        self.assertTrue(django_form.is_valid(), django_form.errors)
        self.assertEqual(django_form.cleaned_data["consent"], "yes")

    def test_validation_fails_when_required_missing(self):
        payload = {"full_name": "", "consent": ""}
        django_form = self.form.build_bound_form(data=payload)
        self.assertFalse(django_form.is_valid())
        self.assertIn("full_name", django_form.errors)
        self.assertIn("consent", django_form.errors)

    def test_service_active_forms_uses_prefetched_cache(self):
        service = Service.objects.create(
            name="Facial",
            base_price="120.00",
            duration_min=60,
        )
        service.pre_appointment_forms.add(self.form)

        prefetched_service = Service.objects.prefetch_related("pre_appointment_forms").get(pk=service.pk)
        active = prefetched_service.active_forms()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].pk, self.form.pk)


class IntakeFormManageViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin_user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password123",
        )

        client_auth = User.objects.create_user(username="client", password="pass123")
        self.client_profile, _ = UserProfile.objects.get_or_create(user=client_auth)

        master_auth = User.objects.create_user(username="master", password="pass123")
        master_profile_user, _ = UserProfile.objects.get_or_create(user=master_auth)
        self.master_profile = MasterProfile.objects.create(user=master_profile_user)

        self.service = Service.objects.create(
            name="Sample service",
            base_price="100.00",
            duration_min=60,
        )

        ServiceMaster.objects.create(service=self.service, master=self.master_profile)

        self.intake_form = ClientIntakeForm.objects.create(
            name="Pre-care form",
            slug="pre-care",
            schema={
                "meta": {"version": 1},
                "sections": [
                    {
                        "id": "sec",
                        "title": "Basics",
                        "fields": [
                            {"id": "f1", "key": "full_name", "label": "Full name", "type": "text", "required": True},
                            {"id": "f2", "key": "consent", "label": "Consent", "type": "checkbox", "required": False},
                        ],
                    }
                ],
            },
        )
        self.service.pre_appointment_forms.add(self.intake_form)

        self.appointment = Appointment.objects.create(
            client=self.client_profile,
            start_time=timezone.now(),
        )

        AppointmentItem.objects.create(
            appointment=self.appointment,
            service=self.service,
            master=self.master_profile,
            start_time=timezone.now(),
        )

    def test_manage_view_creates_submission(self):
        self.client.force_login(self.admin_user)

        url = reverse(
            "admin:core_appointment_manage_form",
            args=[self.appointment.pk, self.intake_form.pk],
        )

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pre-care form")

        post_data = {
            "full_name": "Jane Example",
            "consent": "on",
        }
        response = self.client.post(url, post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        submission = ClientIntakeFormSubmission.objects.get(
            appointment=self.appointment,
            form=self.intake_form,
        )
        self.assertEqual(submission.data["full_name"], "Jane Example")
        self.assertTrue(submission.data["consent"])


class IntakeAssignmentSignalTests(TestCase):
    def setUp(self):
        self.form = ClientIntakeForm.objects.create(
            name="Universal Form",
            slug="universal-form",
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
            username="client",
            email="client@example.com",
            password="pass123",
        )
        self.profile, _ = UserProfile.objects.get_or_create(user=self.user)

    def test_universal_assignment_created_for_profile(self):
        self.assertTrue(
            ClientIntakeAssignment.objects.filter(client=self.profile, form=self.form).exists()
        )

    def test_submission_marks_assignment_completed(self):
        assignment = ClientIntakeAssignment.objects.get(client=self.profile, form=self.form)
        form = assignment.form
        ClientIntakeFormSubmission.objects.create(
            assignment=assignment,
            form=form,
            client=self.profile,
            submitted_by=self.user,
            data={"full_name": "Alice Example"},
            raw_payload={"full_name": "Alice Example"},
            form_schema_snapshot=form.normalized_schema(),
            schema_version=form.schema_version,
            is_complete=True,
        )
        assignment.refresh_from_db()
        self.assertTrue(assignment.is_completed)


class IntakeAdminAnnotationTests(TestCase):
    def setUp(self):
        self.admin_site = AdminSite()
        self.admin_instance = CustomUserAdmin(get_user_model(), self.admin_site)
        self.request_factory = RequestFactory()

        self.form = ClientIntakeForm.objects.create(
            name="General Intake",
            slug="general-intake",
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
            username="client-admin",
            email="client-admin@example.com",
            password="pass123",
        )
        self.profile, _ = UserProfile.objects.get_or_create(user=self.user)
        self.assignment = ClientIntakeAssignment.objects.get(client=self.profile, form=self.form)
        self.staff = get_user_model().objects.create_superuser(
            username="staff",
            email="staff@example.com",
            password="pass123",
        )

    def _get_queryset_row(self):
        request = self.request_factory.get("/admin/core/user/")
        request.user = self.staff
        return self.admin_instance.get_queryset(request).get(pk=self.user.pk)

    def test_queryset_exposes_pending_flag(self):
        row = self._get_queryset_row()
        self.assertTrue(row.universal_intake_pending)

    def test_queryset_flag_clears_after_submission(self):
        form = self.assignment.form
        ClientIntakeFormSubmission.objects.create(
            assignment=self.assignment,
            form=form,
            client=self.profile,
            submitted_by=self.user,
            data={"full_name": "Done"},
            raw_payload={"full_name": "Done"},
            form_schema_snapshot=form.normalized_schema(),
            schema_version=form.schema_version,
            is_complete=True,
        )
        row = self._get_queryset_row()
        self.assertFalse(row.universal_intake_pending)
