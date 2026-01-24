import os
import subprocess
import tempfile
import shutil
from datetime import datetime

from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from app.utils.database import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS

router = APIRouter(prefix="/db", tags=["DB Maintenance"])


# ------------------------------
# SECURITY (dummy for now)
# ------------------------------
def require_super_admin():
    return True


SECURITY = [Depends(require_super_admin)]

# ------------------------------
# PostgreSQL tools
# ------------------------------
DEFAULT_PG_BIN = r"C:\Program Files\PostgreSQL\18\bin"

PG_DUMP = shutil.which("pg_dump") or os.path.join(DEFAULT_PG_BIN, "pg_dump.exe")
PSQL = shutil.which("psql") or os.path.join(DEFAULT_PG_BIN, "psql.exe")


def _assert_tools():
    if not os.path.exists(PG_DUMP):
        raise HTTPException(500, "pg_dump not found")
    if not os.path.exists(PSQL):
        raise HTTPException(500, "psql not found")


def run_cmd(cmd, env):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    if p.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail={
                "cmd": " ".join(cmd),
                "stderr": p.stderr,
            },
        )
    return p


# ------------------------------
# BACKUP
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
    env["PGPASSWORD"] = DB_PASS  # ✅ RAW PASSWORD

    cmd = [
        PG_DUMP,
        "-h", DB_HOST,
        "-p", DB_PORT,
        "-U", DB_USER,
        "-d", DB_NAME,
        "--format=p",
        "--no-owner",
        "--no-privileges",
        "-f", tmp_path,
    ]

    run_cmd(cmd, env)

    def stream_file():
        try:
            with open(tmp_path, "rb") as f:
                while chunk := f.read(1024 * 1024):
                    yield chunk
        finally:
            os.remove(tmp_path)

    return StreamingResponse(
        stream_file(),
        media_type="application/sql",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ------------------------------
# RESTORE
# ------------------------------
@router.post("/restore", dependencies=SECURITY)
async def restore_database(sql_file: UploadFile = File(...)):
    _assert_tools()

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".sql")
    tmp_path = tmp.name
    tmp.close()

    try:
        with open(tmp_path, "wb") as f:
            f.write(await sql_file.read())

        env = os.environ.copy()
        env["PGPASSWORD"] = DB_PASS

        cmd = [
            PSQL,
            "-h", DB_HOST,
            "-p", DB_PORT,
            "-U", DB_USER,
            "-d", DB_NAME,
            "-v", "ON_ERROR_STOP=1",
            "-f", tmp_path,
        ]

        run_cmd(cmd, env)
        return JSONResponse({"message": "restore completed"})
    finally:
        os.remove(tmp_path)


# ------------------------------
# CLONE
# ------------------------------
class DestinationDB(BaseModel):
    dest_host: str
    dest_port: int = 5432
    dest_dbname: str
    dest_user: str
    dest_pass: str
    clean: bool = False


@router.post("/clone-to", dependencies=SECURITY)
def clone_database(payload: DestinationDB):
    _assert_tools()

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".sql")
    tmp_path = tmp.name
    tmp.close()

    try:
        # dump source
        env_src = os.environ.copy()
        env_src["PGPASSWORD"] = DB_PASS

        dump_cmd = [
            PG_DUMP,
            "-h", DB_HOST,
            "-p", DB_PORT,
            "-U", DB_USER,
            "-d", DB_NAME,
            "--format=p",
            "--no-owner",
            "--no-privileges",
            "-f", tmp_path,
        ]
        if payload.clean:
            dump_cmd += ["--clean", "--if-exists"]

        run_cmd(dump_cmd, env_src)

        # restore destination
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

        return {"message": "clone completed"}
    finally:
        os.remove(tmp_path)
