from app.config import Config
import os

print(f"DATABASE_URL from env: {os.getenv('DATABASE_URL')}")
print(f"SQLALCHEMY_DATABASE_URI from Config: {Config.SQLALCHEMY_DATABASE_URI}")
