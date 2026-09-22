FROM ghcr.io/astral-sh/uv:0.8.22 AS uv
FROM python:3.11-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN apt-get update && apt-get install -y --no-install-recommends libportaudio2 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY apps/__init__.py apps/__init__.py
COPY apps/api apps/api
COPY apps/voice_agent apps/voice_agent
COPY packages packages
COPY tests/fixtures/reports/sample_report.json tests/fixtures/reports/sample_report.json
COPY deploy deploy
RUN mkdir -p /app/data && chown -R app:app /app
ENV PATH="/app/.venv/bin:$PATH" HOME=/home/app
USER app
RUN python -m apps.voice_agent download-files
CMD ["python", "-m", "deploy.railway"]
