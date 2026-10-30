FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl libpq5 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend ./backend
COPY config ./config
COPY scripts ./scripts
RUN pip install --upgrade pip && pip install '.[extractors]'
RUN useradd --create-home --uid 10001 newsintel && chown -R newsintel:newsintel /app
USER newsintel
EXPOSE 8010
CMD ["newsintel-api"]
