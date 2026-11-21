#!/usr/bin/env bash
# scripts/backup.sh
# Automated PostgreSQL backup script for ResearchMate
# Runs via cron on the EC2 host and uploads compressed dumps to AWS S3.
# Usage: ./scripts/backup.sh

set -euo pipefail

# Configuration
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="/opt/researchmate/backups"
LOCAL_FILE="${BACKUP_DIR}/researchmate_${TIMESTAMP}.sql.gz"
S3_BUCKET="${AWS_S3_BUCKET:-}"
S3_PREFIX="backups"
DB_CONTAINER="researchmate_db"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-researchmate}"

mkdir -p "$BACKUP_DIR"

echo "=========================================="
echo " Starting Database Backup: ${TIMESTAMP}"
echo "=========================================="

# 1. Verify DB container is running
if ! docker ps --filter "name=${DB_CONTAINER}" --filter "status=running" | grep -q "${DB_CONTAINER}"; then
    echo "ERROR: Container ${DB_CONTAINER} is not running!" >&2
    exit 1
fi

# 2. Dump PostgreSQL database and compress
echo "→ Creating compressed database dump..."
docker exec "${DB_CONTAINER}" pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --no-owner --clean | gzip > "${LOCAL_FILE}"

FILE_SIZE=$(du -h "${LOCAL_FILE}" | cut -f1)
echo "→ Local backup created: ${LOCAL_FILE} (${FILE_SIZE}) ✓"

# 3. Upload to AWS S3 using EC2 IAM Role
if [ -n "${S3_BUCKET}" ]; then
    echo "→ Uploading to s3://${S3_BUCKET}/${S3_PREFIX}/..."
    aws s3 cp "${LOCAL_FILE}" "s3://${S3_BUCKET}/${S3_PREFIX}/researchmate_${TIMESTAMP}.sql.gz" \
        --sse AES256
    echo "→ S3 upload complete ✓"
else
    echo "WARNING: AWS_S3_BUCKET not set. Backup kept locally only."
fi

# 4. Cleanup local backups older than 7 days
echo "→ Cleaning up local backups older than 7 days..."
find "${BACKUP_DIR}" -type f -name "researchmate_*.sql.gz" -mtime +7 -delete
echo "→ Local retention cleanup complete ✓"

echo "=========================================="
echo " Backup finished successfully!"
echo "=========================================="
