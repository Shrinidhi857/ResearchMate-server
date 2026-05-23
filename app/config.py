import os
from datetime import timedelta
from dotenv import load_dotenv
from pathlib import Path

# Load .env file from the project root (assuming app/config.py is in the app directory)
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-change-this')
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        'postgresql://postgres:password@db:5432/researchmate'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'jwt-secret-change-this')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    
    # Google OAuth config
    GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
    
    # Frontend URL
    FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173')