#!/bin/sh
set -e

if [ -n "$DATABASE_HOST" ]; then
  echo "Waiting for database at $DATABASE_HOST:${DATABASE_PORT:-5432}..."
  until python -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1)
try:
    s.connect(('$DATABASE_HOST', int('${DATABASE_PORT:-5432}')))
except OSError:
    sys.exit(1)
"; do
    sleep 1
  done
  echo "Database is up."
fi

if [ "$1" = "gunicorn" ]; then
  python manage.py migrate --noinput
fi

exec "$@"
