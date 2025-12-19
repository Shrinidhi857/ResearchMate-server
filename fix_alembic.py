from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    try:
        # Check if table exists first? Or just try dropping.
        # Postgres might throw error if not exists, but we want it gone.
        db.session.execute(text("DROP TABLE IF EXISTS alembic_version"))
        db.session.commit()
        print("Dropped alembic_version table.")
    except Exception as e:
        print(f"Error: {e}")
