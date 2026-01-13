# app/initial_data.py

from datetime import date
from sqlalchemy.orm import Session

from app.utils.database import SessionLocal
from app.models.roles_model import Role
from app.models.regions_model import Region
from app.models.branches_model import Branch
from app.models.user_model import User
from app.models.employee_model import Employee
from app.models.loan_officer_model import LoanOfficer
from app.models.expense_categories_model import ExpenseCategory
from app.models.expense_subcategories_model import ExpenseSubCategory

# -----------------------------------------
# 1) Default roles (by NAME, not by ID)
# -----------------------------------------
DEFAULT_ROLES = [
    "admin",
    "regional_manager",
    "branch_manager",
    "loan_officer",
    "super_admin",
]

# -----------------------------------------
# 2) Default Regions & Branches
# -----------------------------------------
DEFAULT_REGIONS = [
    {"name": "Region 1"},
]

DEFAULT_BRANCHES = [
    {
        "name": "Branch 1 - Main",
        "region_name": "Region 1",
    }
]

# -----------------------------------------
# 3) Default Users + Employees (seed data)
# -----------------------------------------
USERS_TO_SEED = [
    {
        "username": "superadmin",
        "email": "superadmin@example.com",
        "password": "super123",
        "full_name": "Super Administrator",
        "phone": "9876543210",
        "role_name": "super_admin",
        "region_name": None,
        "branch_name": None,
        "employee_code": "EMP-SA-001",
        "date_joined": date(2025, 1, 1),
        "notes": "Top-level system admin",
        "is_active": True,
    },
    {
        "username": "admin1",
        "email": "admin1@example.com",
        "password": "adminpass",
        "full_name": "Primary Admin",
        "phone": "9876500000",
        "role_name": "admin",
        "region_name": None,
        "branch_name": None,
        "employee_code": "EMP-AD-001",
        "date_joined": date(2025, 1, 2),
        "notes": "Admin level access",
        "is_active": True,
    },
    {
        "username": "region_mgr1",
        "email": "regionmgr1@example.com",
        "password": "region123",
        "full_name": "Regional Manager One",
        "phone": "9000000001",
        "role_name": "regional_manager",
        "region_name": "Region 1",
        "branch_name": None,
        "employee_code": "EMP-RM-001",
        "date_joined": date(2025, 1, 5),
        "notes": "Oversees region operations",
        "is_active": True,
    },
    {
        "username": "branch_mgr1",
        "email": "branchmgr1@example.com",
        "password": "branch123",
        "full_name": "Branch Manager One",
        "phone": "9000000002",
        "role_name": "branch_manager",
        "region_name": "Region 1",
        "branch_name": "Branch 1 - Main",
        "employee_code": "EMP-BM-001",
        "date_joined": date(2025, 1, 6),
        "notes": "Manages branch operations",
        "is_active": True,
    },
    {
        "username": "loan_officer1",
        "email": "lo1@example.com",
        "password": "loan123",
        "full_name": "Loan Officer One",
        "phone": "9000000003",
        "role_name": "loan_officer",
        "region_name": "Region 1",
        "branch_name": "Branch 1 - Main",
        "employee_code": "EMP-LO-001",
        "date_joined": date(2025, 1, 10),
        "notes": "Field loan officer",
        "is_active": True,
    },
]

# -----------------------------------------
# 4) Default Expense Category + Subcategory
# -----------------------------------------
DEFAULT_EXPENSE_MASTER = [
    {
        "category": "Office & Admin",
        "subcategories": ["Stationery", "Printing", "Internet", "Mobile Recharge", "Courier"],
    },
    {
        "category": "Rent & Utilities",
        "subcategories": ["Office Rent", "Electricity", "Water", "Maintenance"],
    },
    {
        "category": "Staff & Welfare",
        "subcategories": ["Tea/Snacks", "Welfare", "Training", "Uniform"],
    },
    {
        "category": "Travel & Transport",
        "subcategories": ["Local Travel", "Fuel", "Vehicle Maintenance", "Auto/Taxi"],
    },
    {
        "category": "Banking & Charges",
        "subcategories": ["Bank Charges", "Loan Processing Fees", "SMS Charges"],
    },
]


# =========================================
# Seeding helpers
# =========================================

def seed_roles(db: Session) -> None:
    existing = {r.name for r in db.query(Role).all()}
    created_any = False

    for role_name in DEFAULT_ROLES:
        if role_name not in existing:
            db.add(Role(name=role_name))
            created_any = True

    if created_any:
        db.commit()
        print("[INIT] Seeded default roles:", DEFAULT_ROLES)
    else:
        print("[INIT] Roles already seeded, skipping.")


def seed_regions(db: Session) -> None:
    existing = {r.region_name for r in db.query(Region).all()}
    created_any = False

    for reg in DEFAULT_REGIONS:
        name = reg["name"]
        if name not in existing:
            db.add(Region(region_name=name))
            created_any = True

    if created_any:
        db.commit()
        print("[INIT] Seeded default regions:", [r["name"] for r in DEFAULT_REGIONS])
    else:
        print("[INIT] Regions already seeded, skipping.")


def seed_branches(db: Session) -> None:
    existing = {b.branch_name for b in db.query(Branch).all()}
    created_any = False

    for br in DEFAULT_BRANCHES:
        name = br["name"]
        region_name = br["region_name"]

        if name in existing:
            continue

        region_obj = db.query(Region).filter(Region.region_name == region_name).first()
        if not region_obj:
            print(f"[INIT] Skipping branch '{name}' because region '{region_name}' not found.")
            continue

        db.add(Branch(branch_name=name, region_id=region_obj.region_id))
        created_any = True

    if created_any:
        db.commit()
        print("[INIT] Seeded default branches:", [b["name"] for b in DEFAULT_BRANCHES])
    else:
        print("[INIT] Branches already seeded, skipping.")


def seed_users_and_employees(db: Session) -> None:
    """
    Creates:
      - users  (auth)
      - employees (profile + hierarchy)
      - loan_officers row for role 'loan_officer'
    """
    created_any = False

    # Preload maps for quick lookup
    roles_by_name = {r.name: r for r in db.query(Role).all()}
    regions_by_name = {r.region_name: r for r in db.query(Region).all()}
    branches_by_name = {b.branch_name: b for b in db.query(Branch).all()}

    for u in USERS_TO_SEED:
        username = u["username"]

        existing_user = db.query(User).filter(User.username == username).first()
        if existing_user:
            print(f"[INIT] User '{username}' already exists, skipping.")
            continue

        role_name = u["role_name"]
        role_obj = roles_by_name.get(role_name)
        if not role_obj:
            print(f"[INIT] Role '{role_name}' not found for user '{username}', skipping.")
            continue

        region_id = None
        branch_id = None

        if u["region_name"]:
            reg_obj = regions_by_name.get(u["region_name"])
            if not reg_obj:
                print(f"[INIT] Region '{u['region_name']}' not found for user '{username}', skipping.")
                continue
            region_id = reg_obj.region_id

        if u["branch_name"]:
            br_obj = branches_by_name.get(u["branch_name"])
            if not br_obj:
                print(f"[INIT] Branch '{u['branch_name']}' not found for user '{username}', skipping.")
                continue
            branch_id = br_obj.branch_id

        auth_user = User(
            username=u["username"],
            email=u["email"],
            password=u["password"],  # plain text (dev only)
            is_active=u["is_active"],
        )
        db.add(auth_user)
        db.flush()

        employee = Employee(
            user_id=auth_user.user_id,
            full_name=u["full_name"],
            phone=u["phone"],
            role_id=role_obj.id,
            region_id=region_id,
            branch_id=branch_id,
            employee_code=u["employee_code"],
            date_joined=u["date_joined"],
            notes=u["notes"],
            is_active=u["is_active"],
        )
        db.add(employee)
        db.flush()

        if role_name == "loan_officer":
            lo_exists = (
                db.query(LoanOfficer)
                .filter(LoanOfficer.employee_id == employee.employee_id)
                .first()
            )
            if not lo_exists:
                db.add(LoanOfficer(employee_id=employee.employee_id))

        created_any = True
        print(f"[INIT] Seeded user + employee: {username} ({role_name})")

    if created_any:
        db.commit()
        print("[INIT] Users & employees seeding completed.")
    else:
        print("[INIT] Users & employees already present, skipping.")


# ✅ NEW: Seed expense categories + subcategories
def seed_expense_categories_and_subcategories(db: Session) -> None:
    created_any = False

    # Preload existing categories
    existing_cats = {c.category_name: c for c in db.query(ExpenseCategory).all()}

    for row in DEFAULT_EXPENSE_MASTER:
        cat_name = row["category"].strip()

        # 1) Category
        cat_obj = existing_cats.get(cat_name)
        if not cat_obj:
            cat_obj = ExpenseCategory(category_name=cat_name, is_active=True)
            db.add(cat_obj)
            db.flush()  # get category_id
            existing_cats[cat_name] = cat_obj
            created_any = True
            print(f"[INIT] Created expense category: {cat_name}")

        # 2) Subcategories for this category
        existing_subs = {
            s.subcategory_name
            for s in (
                db.query(ExpenseSubCategory)
                .filter(ExpenseSubCategory.category_id == cat_obj.category_id)
                .all()
            )
        }

        for sub_name in row.get("subcategories", []):
            sub_name = sub_name.strip()
            if sub_name in existing_subs:
                continue

            db.add(
                ExpenseSubCategory(
                    category_id=cat_obj.category_id,
                    subcategory_name=sub_name,
                    is_active=True,
                )
            )
            created_any = True
            print(f"[INIT]   - Created expense subcategory: {cat_name} -> {sub_name}")

    if created_any:
        db.commit()
        print("[INIT] Expense category/subcategory seeding completed.")
    else:
        print("[INIT] Expense categories/subcategories already seeded, skipping.")


# =========================================
# Entry point
# =========================================

def init_seed() -> None:
    db: Session = SessionLocal()
    try:
        seed_roles(db)
        seed_regions(db)
        seed_branches(db)
        seed_users_and_employees(db)

        # ✅ NEW: Expense master seed
        seed_expense_categories_and_subcategories(db)

    finally:
        db.close()


if __name__ == "__main__":
    # Run with:
    #   python -m app.initial_data
    init_seed()
