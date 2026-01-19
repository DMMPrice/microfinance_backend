import os
import subprocess
import tempfile
from datetime import datetime
import shutil

from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

# ✅ Uses your .env loading logic (works in Nuitka EXE too)
from app.utils.database import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS

router = APIRouter(prefix="/db", tags=["DB Maintenance"])


# ------------------------------
# ✅ SECURITY (hook your auth here)
# ------------------------------
def require_super_admin():
    """
    Replace this with your real auth:
    - Decode JWT
    - Check role == 'super_admin' (or your privileged roles)
    - Raise HTTPException(403) if not allowed
    """
    # Example:
    # if user.role != "super_admin": raise HTTPException(403, "Forbidden")
    return True


# Apply to all routes in this router
SECURITY = [Depends(require_super_admin)]

# ------------------------------
# ✅ Robust tool detection (EXE-safe)
# ------------------------------
DEFAULT_PG_BIN = r"C:\Program Files\PostgreSQL\18\bin"

PG_DUMP = shutil.which("pg_dump") or os.path.join(DEFAULT_PG_BIN, "pg_dump.exe")
PSQL = shutil.which("psql") or os.path.join(DEFAULT_PG_BIN, "psql.exe")


def _assert_tools():
    if not os.path.exists(PG_DUMP):
        raise HTTPException(
            status_code=500,
            detail=f"pg_dump not found. Checked PATH and fallback: {PG_DUMP}. Install PostgreSQL client tools or fix PATH.",
        )
    if not os.path.exists(PSQL):
        raise HTTPException(
            status_code=500,
            detail=f"psql not found. Checked PATH and fallback: {PSQL}. Install PostgreSQL client tools or fix PATH.",
        )


def run_cmd(cmd: list[str], env: dict):
    p = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    if p.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Command failed",
                "cmd": " ".join(cmd),
                "stderr": (p.stderr or "")[-4000:],
            },
        )
    return p


def ensure_dest_db_exists(dest_host: str, dest_port: int, dest_user: str, dest_pass: str, dest_dbname: str):
    """
    Connect to 'postgres' and create dest_dbname if missing.
    Destination user must have CREATEDB privilege.
    """
    env = os.environ.copy()
    env["PGPASSWORD"] = dest_pass

    # check
    check_cmd = [
        PSQL,
        "-h", dest_host,
        "-p", str(dest_port),
        "-U", dest_user,
        "-d", "postgres",
        "-tAc",
        f"SELECT 1 FROM pg_database WHERE datname='{dest_dbname}';",
    ]
    p = run_cmd(check_cmd, env)
    exists = (p.stdout or "").strip() == "1"
    if exists:
        return

    # create
    create_cmd = [
        PSQL,
        "-h", dest_host,
        "-p", str(dest_port),
        "-U", dest_user,
        "-d", "postgres",
        "-v", "ON_ERROR_STOP=1",
        "-c", f'CREATE DATABASE "{dest_dbname}";',
    ]
    run_cmd(create_cmd, env)


# ------------------------------
# ✅ (1) Backup: SOURCE (.env) -> download .sql
# ------------------------------
@router.post("/backup", dependencies=SECURITY)
def backup_database():
    _assert_tools()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{DB_NAME}_backup_{ts}.sql"

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".sql")
    tmp_path = tmp.name
    tmp.close()

    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASS

    cmd = [
        PG_DUMP,
        "-h", str(DB_HOST),
        "-p", str(DB_PORT),
        "-U", str(DB_USER),
        "-d", str(DB_NAME),
        "--format=p",  # plain SQL
        "--no-owner",
        "--no-privileges",
        "-f", tmp_path,
    ]

    run_cmd(cmd, env)

    def stream_file(path: str, chunk_size: int = 1024 * 1024):
        try:
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    return StreamingResponse(
        stream_file(tmp_path),
        media_type="application/sql",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ------------------------------
# ✅ (2) Restore Upload: upload .sql -> restore into SOURCE (.env)
# ------------------------------
@router.post("/restore", dependencies=SECURITY)
async def restore_database(sql_file: UploadFile = File(...)):
    _assert_tools()

    if not sql_file.filename or not sql_file.filename.lower().endswith(".sql"):
        raise HTTPException(status_code=400, detail="Upload a .sql file")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".sql")
    tmp_path = tmp.name
    tmp.close()

    try:
        content = await sql_file.read()
        with open(tmp_path, "wb") as f:
            f.write(content)

        env = os.environ.copy()
        env["PGPASSWORD"] = DB_PASS

        cmd = [
            PSQL,
            "-h", str(DB_HOST),
            "-p", str(DB_PORT),
            "-U", str(DB_USER),
            "-d", str(DB_NAME),
            "-v", "ON_ERROR_STOP=1",
            "-f", tmp_path,
        ]

        run_cmd(cmd, env)

        return JSONResponse({"message": "restore completed", "database": DB_NAME})
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


# ------------------------------
# ✅ (3) Clone-to: SOURCE (.env) -> DEST (request creds), no upload
# ------------------------------
class DestinationDB(BaseModel):
    dest_host: str = Field(..., examples=["127.0.0.1"])
    dest_port: int = Field(5432, examples=[5432])
    dest_dbname: str = Field(..., examples=["microfinance_clone"])
    dest_user: str = Field(..., examples=["postgres"])
    dest_pass: str = Field(..., examples=["secret"])
    clean: bool = False  # if True, dump includes --clean --if-exists (overwrite destination objects)


@router.post("/clone-to", dependencies=SECURITY)
def clone_source_to_destination(payload: DestinationDB):
    _assert_tools()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".sql")
    tmp_path = tmp.name
    tmp.close()

    try:
        # 1) Dump SOURCE
        env_src = os.environ.copy()
        env_src["PGPASSWORD"] = DB_PASS

        dump_cmd = [
            PG_DUMP,
            "-h", str(DB_HOST),
            "-p", str(DB_PORT),
            "-U", str(DB_USER),
            "-d", str(DB_NAME),
            "--format=p",
            "--no-owner",
            "--no-privileges",
        ]
        if payload.clean:
            dump_cmd += ["--clean", "--if-exists"]
        dump_cmd += ["-f", tmp_path]

        run_cmd(dump_cmd, env_src)

        # 2) Ensure DEST DB exists
        ensure_dest_db_exists(
            dest_host=payload.dest_host,
            dest_port=payload.dest_port,
            dest_user=payload.dest_user,
            dest_pass=payload.dest_pass,
            dest_dbname=payload.dest_dbname,
        )

        # 3) Restore into DEST
        env_dest = os.environ.copy()
        env_dest["PGPASSWORD"] = payload.dest_pass

        restore_cmd = [
            PSQL,
            "-h", payload.dest_host,
            "-p", str(payload.dest_port),
            "-U", payload.dest_user,
            "-d", payload.dest_dbname,
            "-v", "ON_ERROR_STOP=1",
            "-f", tmp_path,
        ]

        run_cmd(restore_cmd, env_dest)

        return JSONResponse(
            {
                "message": "clone completed",
                "timestamp": ts,
                "source": {"host": str(DB_HOST), "port": str(DB_PORT), "db": str(DB_NAME)},
                "destination": {"host": payload.dest_host, "port": payload.dest_port, "db": payload.dest_dbname},
            }
        )

    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
