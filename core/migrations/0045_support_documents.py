from django.db import migrations, models
from django.db.models import Q


PRIVACY_BODY = """
<section>
  <h2>Personal data we collect</h2>
  <p>We ask for just the information we need to manage your bookings and keep you informed.</p>
  <ul>
    <li>Profile details such as your full name, pronouns, and preferred contact information.</li>
    <li>Contact details including email, phone number, and billing address for confirmations and receipts.</li>
    <li>Booking history, appointment notes, receipts, and optional intake forms that you complete.</li>
  </ul>
</section>
<section>
  <h2>How we use this information</h2>
  <p>We rely on your explicit consent and the performance of our service agreement to process data.</p>
  <ul>
    <li>To schedule, reschedule, and personalise appointments and aftercare.</li>
    <li>To process payments, issue invoices, and meet accounting/audit requirements.</li>
    <li>To deliver essential service updates (appointment confirmations, reminder emails, and transactional SMS).</li>
  </ul>
</section>
<section>
  <h2>How we keep it safe</h2>
  <p>Security is layered: we encrypt data in transit, store it with vetted providers, and only grant access to trained team members.</p>
  <ul>
    <li>All logins require least-privilege staff accounts with MFA where supported.</li>
    <li>Sensitive records are retained only for the period required by Canadian legislation and payment partners.</li>
    <li>We log access to personal data to quickly investigate any suspicious activity.</li>
  </ul>
</section>
<section>
  <h2>Your privacy controls</h2>
  <p>You decide how your information is stored and when it should be removed.</p>
  <ul>
    <li>Request a copy of your data or corrections at any time by emailing privacy@malva.example.</li>
    <li>Withdraw consent for optional fields (marketing preferences, intake details) without impacting service delivery.</li>
    <li>Ask us to deactivate your account; we will retain only the invoices and records we must keep by law.</li>
  </ul>
</section>
""".strip()


EMAIL_UPDATES_BODY = """
<section>
  <h2>What you receive</h2>
  <ul>
    <li>Booking-related nudges when you have an upcoming visit or a saved form to complete.</li>
    <li>Occasional wellness tips and curated product spotlights tailored to your service history.</li>
    <li>Exclusive offers for loyal guests, limited to two marketing campaigns per month.</li>
  </ul>
</section>
<section>
  <h2>Respecting your inbox</h2>
  <p>We keep every message purposeful. Marketing emails include a one-click unsubscribe link that takes effect immediately.</p>
  <ul>
    <li>Unsubscribing stops promotional content but keeps essential booking confirmations and receipts flowing.</li>
    <li>We do not sell, rent, or share your email with outside marketers. Delivery is handled by vetted providers only.</li>
    <li>Preferences are mirrored inside your profile so our team honours your choice during manual outreach.</li>
  </ul>
</section>
<section>
  <h2>Changing your mind</h2>
  <p>Opting back in is as easy as checking the consent box in your profile or emailing hello@malva.example. We will reply within two business days.</p>
  <p>If you prefer that we purge all marketing interaction history, let us know—this does not impact your booking account.</p>
</section>
""".strip()


def seed_support_documents(apps, schema_editor):
    SupportDocument = apps.get_model("core", "SupportDocument")
    documents = [
        {
            "document_type": "privacy_notice",
            "slug": "privacy-notice",
            "title": "Privacy Notice",
            "subtitle": "How we process, protect, and respect your personal information.",
            "intro": "This page explains the safeguards we apply whenever you share data with Malva Booking.",
            "body": PRIVACY_BODY,
            "card_title": "Privacy notice",
            "card_excerpt": "Understand what we collect, why we store it, and how to exercise your rights.",
            "card_cta_label": "Review privacy",
            "display_order": 10,
        },
        {
            "document_type": "email_updates",
            "slug": "email-updates",
            "title": "Email Updates & Marketing Preferences",
            "subtitle": "Transparency around optional newsletters and promotional updates.",
            "intro": "We believe curated updates should feel helpful. Here is exactly what opting in means.",
            "body": EMAIL_UPDATES_BODY,
            "card_title": "Marketing emails",
            "card_excerpt": "See how often we write, what we include, and how to change your preference instantly.",
            "card_cta_label": "See policy",
            "display_order": 20,
        },
    ]
    for doc in documents:
        SupportDocument.objects.update_or_create(
            document_type=doc["document_type"],
            defaults=doc,
        )


def unseed_support_documents(apps, schema_editor):
    SupportDocument = apps.get_model("core", "SupportDocument")
    SupportDocument.objects.filter(
        document_type__in=["privacy_notice", "email_updates"]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0044_clientfile_before_after"),
    ]

    operations = [
        migrations.CreateModel(
            name="SupportDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("document_type", models.CharField(choices=[("privacy_notice", "Privacy notice"), ("email_updates", "Email updates policy"), ("other", "General support document")], help_text="Used to reference the document from code and routes.", max_length=32)),
                ("slug", models.SlugField(help_text="Public slug used in support URLs, e.g. 'privacy-notice'.", max_length=80, unique=True)),
                ("title", models.CharField(max_length=160)),
                ("subtitle", models.CharField(blank=True, help_text="Short supporting line shown under the hero title.", max_length=255)),
                ("intro", models.TextField(blank=True, help_text="Optional intro paragraph rendered above the sections.")),
                ("body", models.TextField(help_text="Rich HTML content rendered on the legal/support page.")),
                ("card_title", models.CharField(blank=True, help_text="Override title for the Support tab card if needed.", max_length=120)),
                ("card_excerpt", models.CharField(blank=True, help_text="Short summary displayed on the Support tab card.", max_length=240)),
                ("card_cta_label", models.CharField(default="Read policy", help_text="Button label for the Support tab card CTA.", max_length=80)),
                ("display_order", models.PositiveSmallIntegerField(default=100, help_text="Lower values surface earlier inside the Support tab.")),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Support document",
                "verbose_name_plural": "Support documents",
                "ordering": ("display_order", "title"),
            },
        ),
        migrations.AddConstraint(
            model_name="supportdocument",
            constraint=models.UniqueConstraint(
                fields=("document_type",),
                condition=~Q(document_type="other"),
                name="unique_support_doc_per_type",
            ),
        ),
        migrations.RunPython(seed_support_documents, unseed_support_documents),
    ]
