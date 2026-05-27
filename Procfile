web: gunicorn config.wsgi:application --workers 2 --bind 0.0.0.0:$PORT --timeout 120
release: python manage.py migrate --no-input && python manage.py collectstatic --no-input
