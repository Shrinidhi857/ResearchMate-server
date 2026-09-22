from app.database import SessionLocal

# For backward compatibility if any module imports db
db = SessionLocal()
