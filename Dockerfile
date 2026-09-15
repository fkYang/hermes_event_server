FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
RUN pip install --no-cache-dir .

USER nobody
EXPOSE 8080
CMD ["uvicorn", "eventserver.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
