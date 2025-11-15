web: gunicorn booking.wsgi:application
worker: celery -A booking worker --loglevel=info
beat: celery -A booking beat --loglevel=info
telegrambot: python manage.py run_telegram_bot
