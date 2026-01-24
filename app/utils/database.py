from urllib.parse import quote_plus
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# ---------------------
# DB CONFIG (ONLY HERE)
# ---------------------
DB_HOST = "127.0.0.1"
DB_PORT = "5432"
DB_NAME = "microfinance"
DB_USER = "akota"
DB_PASS = "Akota@123"

# ---------------------
# SQLAlchemy URL
# ---------------------
DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER}:{quote_plus(DB_PASS)}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
