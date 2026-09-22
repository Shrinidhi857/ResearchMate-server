"""
migrations/versions/001_enable_pgvector.py
Enable the pgvector extension on PostgreSQL.
Must run before any table with VECTOR columns is created.
"""
from alembic import op

revision = "001_enable_pgvector"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector — safe to run multiple times (IF NOT EXISTS)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")


def downgrade() -> None:
    # Only drop if nothing depends on it
    op.execute("DROP EXTENSION IF EXISTS vector;")
