FROM python:3.12-slim AS tailwind

WORKDIR /tailwind
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*
RUN curl -sL -o /usr/local/bin/tailwindcss \
      https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64 && \
    chmod +x /usr/local/bin/tailwindcss
COPY static_src/css/input.css static_src/css/input.css
COPY templates templates
COPY apps apps
RUN tailwindcss -i static_src/css/input.css -o static/css/output.css --minify


FROM python:3.12-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && \
    rm -rf /var/lib/apt/lists/*

COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/prod.txt

COPY . .
COPY --from=tailwind /tailwind/static/css/output.css static/css/output.css

RUN useradd --create-home --uid 1000 kiwi && \
    mkdir -p /app/media /app/staticfiles && \
    chown -R kiwi:kiwi /app
USER kiwi

RUN SECRET_KEY_PLACEHOLDER=1 DJANGO_SECRET_KEY=build-time-placeholder \
    python manage.py collectstatic --noinput

EXPOSE 8000

COPY --chown=kiwi:kiwi docker/entrypoint.sh /app/docker/entrypoint.sh
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
