from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # ensure models are registered
from app.utils.database import engine, Base
from app.initial_data import init_seed

import sys
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

from app.routers import (
    auth_router,
    groups_router,
    members_router,
    branches_router,
    regions_router,
    loan_officers_router,
    loans_router,
    settings_router,
    reports_router
)

app = FastAPI(title="Microfinance Backend API", version="1.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://localhost:8081",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:8081",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router.router)
app.include_router(regions_router.router)
app.include_router(branches_router.router)
app.include_router(groups_router.router)
app.include_router(members_router.router)
app.include_router(loan_officers_router.router)
app.include_router(loans_router.router)
app.include_router(settings_router.router)
app.include_router(reports_router.router)


@app.on_event("startup")
def on_startup():
    # DEV ONLY – OK for now
    Base.metadata.create_all(bind=engine)

    print("🔄 Running initial database seeding…")
    init_seed()
    print("✅ Seeding complete.\n")


@app.get("/")
def root():
    return {"message": "Microfinance Backend is running!!"}
