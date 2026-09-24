# One image, deployed twice: SERVICE_ROLE=api (public) and SERVICE_ROLE=worker (internal only).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /srv

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir ".[cloud]" \
    && useradd --create-home --uid 10001 paperaid
USER paperaid

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
