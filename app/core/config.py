import os
from dotenv import load_dotenv

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "xxx")
JWT_ALGO = os.getenv("JWT_ALGO", "HS256")
