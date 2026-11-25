# Booking integrations

Providers are configured separately from running the Django development server.
Use development accounts and test keys, and keep all credentials out of Git.

## Stripe

Relevant environment variables include:

- `STRIPE_PUBLIC_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`.
- `STRIPE_CURRENCY` and `STRIPE_API_VERSION`.
- `STRIPE_PAYMENT_METHOD_TYPES` for supported checkout methods.

Review [`core/payments/stripe_api.py`](../core/payments/stripe_api.py) and
[`booking/settings.py`](../booking/settings.py) for the actual behavior and defaults.
The application supports payment intents, saved-card operations, refunds, staff
payment records and no-show handling. Provider completion and webhook processing
are separate steps; a local page alone does not establish a successful charge.

For an intentionally configured test account, Stripe CLI can forward webhooks:

```bash
stripe login
stripe listen --forward-to localhost:8000/stripe/webhook/
```

Existing documentation provides these **synthetic Stripe test-mode fixtures**:

| Scenario | Test card |
| --- | --- |
| Successful test payment | `4242 4242 4242 4242` |
| Additional authentication | `4000 0027 6000 3184` |
| Insufficient funds | `4000 0000 0000 9995` |

Use them only with test credentials. They do not represent real customer cards or
successful application/provider verification during this documentation refresh.

The customer cart obtains a PaymentIntent through the application's checkout flow.
Staff no-show charging is a separate authenticated operation at
`/accounts/api/payments/no-show/charge/`; do not use it as a smoke test against a
real customer or live provider account.

## Staff payment entry

The appointment admin exposes a payment menu. Cash and e-transfer options open
the appropriate payment entry; terminal/card flows have their own processing and
fee behavior. Confirm settings and webhook results before interpreting a payment
record as a settled provider transaction. Receipts and refund behavior live in
the corresponding core models, views and payment tests.

## Telegram

The [`telegrambot/`](../telegrambot/) app owns subscriptions, bot settings and
operational commands. Configuration uses `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_NOTIFICATIONS_ENABLED`, `TELEGRAM_ADMIN_PASSPHRASE` and optional admin-chat
settings. Use the admin interface and your own secret values; this document does
not publish recovery credentials or shared test accounts.

The separate worker is declared in [`Procfile`](../Procfile) and can be started
locally only for an intentionally configured test bot:

```bash
python manage.py run_telegram_bot
```

Existing commands include subscription management and daily operational information.
Inspect [`telegrambot/handlers.py`](../telegrambot/handlers.py) and
[`telegrambot/services.py`](../telegrambot/services.py) when adding a command or
changing recipient behavior.

## Optional staff assistant

The code includes an OpenAI-backed staff assistant. Provider keys and access rules
must be configured intentionally; availability depends on the external provider.
Review [`telegrambot/assistant.py`](../telegrambot/assistant.py) and the bot settings
before enabling it. No AI call, billing authorization, real message or payment is
performed as part of this documentation refresh.

## Email, SMS and uploads

Email, Twilio and S3 are optional configured integrations. Use isolated development
destinations and private storage. Keep client intake documents, payment information,
message histories and uploaded files outside version control.
