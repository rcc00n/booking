web: gunicorn booking.wsgi:application --bind 0.0.0.0:$PORT
worker: celery -A booking worker --loglevel=info
beat: celery -A booking beat --loglevel=info
