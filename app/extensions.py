from app.database import engine, SessionLocal, Base, get_db

# For backward compatibility if any module imports db
db = SessionLocal()