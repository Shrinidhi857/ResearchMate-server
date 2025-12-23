import os
from dotenv import load_dotenv

print(f"Loading .env from CWD: {os.getcwd()}")
load_dotenv()
print(f"DATABASE_URL: {os.getenv('DATABASE_URL')}")
