FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app
COPY src ./src

EXPOSE 8080
USER nobody
ENTRYPOINT ["python", "-m", "demo_reminder.main"]
