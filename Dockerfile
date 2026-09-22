# ──────────────────────────────────────────────────────────────────────────────
# ResearchMate – Production Dockerfile
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

# System deps: pdflatex, psycopg2, AWS CLI for secret fetching
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        texlive-latex-base \
        texlive-latex-extra \
        texlive-fonts-recommended \
        curl \
        unzip \
    && pip install --no-cache-dir awscli \
    && rm -rf /var/lib/apt/lists/*

# ─── Python dependencies ──────────────────────────────────────────────────────
FROM base AS deps
WORKDIR /install
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ─── Final runtime image ──────────────────────────────────────────────────────
FROM base AS runtime
WORKDIR /app

COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

COPY . .

# Make entrypoint executable
RUN chmod +x scripts/entrypoint.sh

# Non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
RUN chown -R appuser:appgroup /app
USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Runs migrations then starts Uvicorn
CMD ["scripts/entrypoint.sh"]
