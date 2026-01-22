from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
from pathlib import Path
import os
import sys

# ======================================================
# Load .env correctly in BOTH:
# - normal dev run (uvicorn main:app)
# - Nuitka onefile EXE (run_server.exe)
# ======================================================

if getattr(sys, "frozen", False):
    # Running as compiled EXE (Nuitka onefile)
    # -> sys.executable is the path to run_server.exe
    BASE_DIR = Path(sys.executable).parent
else:
    # Running as normal Python script
    # This file is: <project_root>/app/utils/database.py
    # So parents[2] = project_root (microfinance-backend)
    BASE_DIR = Path(__file__).resolve().parents[2]

# .env in the same folder as:
# - project root (for dev: uvicorn)
# - dist folder (for EXE: run_server.exe + .env)
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path)

# ---------------------
# Read environment vars
# ---------------------
DB_HOST = "127.0.0.1"
DB_PORT = "5432"
DB_NAME = "microfinance"
DB_USER = "akota"
DB_PASS = "Akota%40123"

# DB_HOST = "72.61.174.109"
# DB_PORT = "5432"
# DB_NAME = "microfinance"
# DB_USER = "admin"
# DB_PASS = "Powercasting2025"

# 🛡️ Fix the None / empty / "None" port issue permanently
if not DB_PORT or str(DB_PORT).lower() == "none":
    DB_PORT = "5432"

# ---------------------
# SQLAlchemy URL
# ---------------------
DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# ---------------------
# SQLAlchemy engine / session / Base
# ---------------------
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,  # drops dead connections automatically
    pool_size=5,
    max_overflow=10,
    future=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
