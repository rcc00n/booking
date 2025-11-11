from django.db import migrations


TERMS_BODY = """
<section>
  <h2>Your booking agreement with Malva</h2>
  <p>These terms explain how appointments are confirmed, rescheduled, or cancelled. Please review them before completing a booking.</p>
  <ul>
    <li>Appointments may be rescheduled or cancelled up to 24 hours in advance through your portal or by contacting support.</li>
    <li>Late cancellations or no-shows may incur the fee outlined on your confirmation screen.</li>
    <li>Packages, prepaid services, and gift cards are non-transferable unless our support team approves the change in writing.</li>
  </ul>
</section>
<section>
  <h2>Payments & billing</h2>
  <p>We securely process cards through our payment partners and never store full card numbers on Malva servers.</p>
  <ul>
    <li>Deposits or balances are charged according to the schedule shown in checkout.</li>
    <li>Refunds post back to the original payment method as soon as our bank releases the funds (typically 5–10 business days).</li>
    <li>Disputed or reversed payments may result in an account hold until the balance is cleared.</li>
  </ul>
</section>
<section>
  <h2>Your responsibilities</h2>
  <ul>
    <li>Provide accurate profile details and keep intake forms up to date so we can tailor services safely.</li>
    <li>Arrive on time or notify us as soon as possible if you are delayed.</li>
    <li>Respect studio policies around health, safety, and respectful conduct toward staff and other guests.</li>
  </ul>
  <p>If you have any questions, email support@malva.example and we will clarify anything before you agree.</p>
</section>
""".strip()


def create_terms_document(apps, _):
    SupportDocument = apps.get_model("core", "SupportDocument")
    SupportDocument.objects.update_or_create(
        document_type="terms_conditions",
        defaults={
            "slug": "terms-and-conditions",
            "title": "Terms & Conditions",
            "subtitle": "What you agree to when booking with Malva.",
            "intro": "These terms keep bookings fair for clients and practitioners. Contact support if you need clarification.",
            "body": TERMS_BODY,
            "card_title": "Terms & conditions",
            "card_excerpt": "Appointments, billing, and cancellation expectations in one place.",
            "card_cta_label": "Read terms",
            "display_order": 30,
        },
    )


def delete_terms_document(apps, _):
    SupportDocument = apps.get_model("core", "SupportDocument")
    SupportDocument.objects.filter(document_type="terms_conditions").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0045_support_documents"),
    ]

    operations = [
        migrations.RunPython(create_terms_document, delete_terms_document),
    ]
