# Booking development guide

## Fresh local setup

The repository pins Python 3.12 in [`.python-version`](../.python-version).
Prepare an empty local PostgreSQL database and a dedicated local role. Set
`DATABASE_URL` explicitly; the settings read it from the environment. Django uses
the `SECRET_KEY` variable. Configure your own values in an untracked `.env`:

```dotenv
SECRET_KEY=<generate-a-new-local-secret>
DATABASE_URL=postgresql://LOCAL_USER:LOCAL_PASSWORD@127.0.0.1:5432/booking_local
```

Replace every placeholder and generate a new random key, for example with
`python -c 'import secrets; print(secrets.token_urlsafe(50))'`. Do not reuse passwords,
bot recovery phrases or provider keys from an existing deployment or old examples.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000
```

The project includes PDF rendering dependencies; install their required native
libraries for your platform. Development commands were checked against source
configuration, not run against a new database during the documentation refresh.

`makemigrations` is for intentional model development, not a prerequisite to running
the existing schema. Review generated migrations and add coverage for the changed
business rule before submitting a pull request.

## Optional background processes

Configure a separate local Redis broker/result backend before starting Celery:

```bash
celery -A booking worker --loglevel=info
celery -A booking beat --loglevel=info
```

The Telegram process is independent:

```bash
python manage.py run_telegram_bot
```

Only start these workers with intentionally configured local providers and recipients.
Scheduled tasks, messaging and payment-related jobs can have external effects. Do
not point development processes at a deployed database, broker or active bot.

## Persistent uploads

The application supports `STORAGE_ROOT`, `MEDIA_ROOT` and `STATIC_ROOT`. For a
deployment, mount persistent storage outside the replaceable application filesystem.
An example for an explicitly selected Dokku app is:

```bash
dokku storage:ensure-directory <app>-storage
dokku storage:mount <app> /var/lib/dokku/data/storage/<app>-storage:/app/storage
```

Replace placeholders and review the intended host before operating it. Storage
changes and rebuilds are deployment operations, not local setup steps. Keep private
uploads out of Git and arrange backups independently.

## Source and verification boundaries

- [`booking/settings.py`](../booking/settings.py) defines environment and provider
  settings. The current development defaults require a separate security review
  before exposing a deployment.
- [`Procfile`](../Procfile) declares web, Celery worker, scheduler and Telegram worker.
- [`core/tests/`](../core/tests/) and [`telegrambot/tests.py`](../telegrambot/tests.py)
  contain existing tests. This documentation refresh does not claim they were run.
- The existing GitHub deployment workflow responds to the `deploy` branch. Publishing
  documentation does not require pushing that branch or starting a deployment.

See [integrations](INTEGRATIONS.md) for payment, webhook and messaging configuration.
