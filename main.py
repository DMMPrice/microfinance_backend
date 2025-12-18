from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models
from app.utils.database import engine, Base
from app.routers import (
    auth_router,
    groups_router,
    members_router,
    branches_router,
    regions_router,
    loan_officers_router,
    loans_router,
    settings_router
)
from app.initial_data import init_seed  # 👉 USE THIS instead of seed_roles()

# --------------------------------------
# Create tables (DEV ONLY – OK for now)
# --------------------------------------
Base.metadata.create_all(bind=engine)

# --------------------------------------
# Seed master data ONCE
# --------------------------------------
# This safely seeds:
# - roles
# - regions
# - branches
# - users + employees
# - loan_officers
#
# And will automatically SKIP if already seeded.
# --------------------------------------
print("🔄 Running initial database seeding…")
init_seed()
print("✅ Seeding complete.\n")

# --------------------------------------
# FastAPI APP
# --------------------------------------
app = FastAPI(title="Microfinance Backend API", version="1.0")

# --------------------------------------
# CORS CONFIG (Relaxed for now)
# --------------------------------------
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

# --------------------------------------
# ROUTERS
# --------------------------------------
app.include_router(auth_router.router)
app.include_router(regions_router.router)
app.include_router(branches_router.router)
app.include_router(groups_router.router)
app.include_router(members_router.router)
app.include_router(loan_officers_router.router)
app.include_router(loans_router.router)
app.include_router(settings_router.router)


@app.get("/")
def root():
    return {"message": "Microfinance Backend is running"}
