#!/usr/bin/env bash
# scripts/entrypoint.sh
# Container startup: run DB migrations then launch the API server.
# Used as CMD in Dockerfile for both production and staging.

set -euo pipefail

echo "═══════════════════════════════════════════"
echo "  ResearchMate API – Container Startup"
echo "═══════════════════════════════════════════"

# ── Optional: fetch secrets from AWS Secrets Manager ─────────────────────────
# If running on EC2/ECS with an IAM role, pull the secret and export as env vars.
if [ -n "${AWS_SECRET_NAME:-}" ]; then
    echo "→ Fetching secrets from AWS Secrets Manager: $AWS_SECRET_NAME"
    SECRET_JSON=$(aws secretsmanager get-secret-value \
        --secret-id "$AWS_SECRET_NAME" \
        --query SecretString \
        --output text \
        --region "${AWS_REGION:-ap-south-1}")
    # Export each key=value pair from JSON into the environment
    eval "$(echo "$SECRET_JSON" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for k, v in d.items():
    v = v.replace(\"'\", \"'\\\"'\\\"'\")
    print(f\"export {k}='{v}'\")
")"
    echo "→ Secrets loaded ✓"
fi

# ── Wait for database to be ready ────────────────────────────────────────────
echo "→ Waiting for database..."
python3 - <<'PYEOF'
import os, time, sys
from sqlalchemy import create_engine, text

db_url = os.getenv("DATABASE_URL", "")
if not db_url:
    print("WARNING: DATABASE_URL not set")
    sys.exit(0)

for attempt in range(30):
    try:
        engine = create_engine(db_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"  Database ready after {attempt + 1} attempt(s) ✓")
        sys.exit(0)
    except Exception as e:
        print(f"  Attempt {attempt + 1}/30: {e}")
        time.sleep(2)

print("ERROR: Database did not become ready in time")
sys.exit(1)
PYEOF

# ── Run Alembic migrations ────────────────────────────────────────────────────
echo "→ Running database migrations..."
alembic upgrade head
echo "→ Migrations complete ✓"

# ── Start the API server ──────────────────────────────────────────────────────
WORKERS="${UVICORN_WORKERS:-2}"
echo "→ Starting Uvicorn (workers=$WORKERS)..."
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 5000 \
    --workers "$WORKERS" \
    --proxy-headers \
    --forwarded-allow-ips="*"
