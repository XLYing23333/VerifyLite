FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=1921 \
    GUNICORN_WORKERS=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/data

EXPOSE 1921

CMD ["sh", "-c", "gunicorn --workers ${GUNICORN_WORKERS:-1} --bind 0.0.0.0:${PORT:-1921} --timeout ${GUNICORN_TIMEOUT:-600} wsgi:app"]
