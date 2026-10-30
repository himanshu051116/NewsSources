FROM mcr.microsoft.com/playwright/python:v1.54.0-noble
WORKDIR /app
COPY pyproject.toml README.md /app/
COPY backend /app/backend
RUN pip install --no-cache-dir -e . && pip install --no-cache-dir "playwright>=1.54,<2"
ENV PYTHONPATH=/app/backend/src
USER pwuser
CMD ["python", "-m", "newsintel.browser_renderer.main"]
