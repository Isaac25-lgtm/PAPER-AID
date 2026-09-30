# One image, deployed twice: SERVICE_ROLE=api (public) and SERVICE_ROLE=worker (internal only).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /srv

# A small offline TeX Live for the LaTeX conversion's PDF (no shell escape, no network at run time).
# With WITH_LIBREOFFICE=true (owner's decision, Workstream H) the image also gets LibreOffice Writer
# and metric-compatible fonts, so page limits are counted on the rendered document (RENDER_PAGES).
ARG WITH_LIBREOFFICE=false
RUN apt-get update \
    && apt-get install -y --no-install-recommends texlive-latex-base texlive-latex-recommended texlive-fonts-recommended lmodern \
    && if [ "$WITH_LIBREOFFICE" = "true" ]; then apt-get install -y --no-install-recommends libreoffice-writer-nogui fonts-liberation2 fonts-crosextra-carlito fonts-crosextra-caladea; fi \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir ".[cloud]" \
    && python -m app.latex.package \
    && useradd --create-home --uid 10001 paperaid
USER paperaid

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
