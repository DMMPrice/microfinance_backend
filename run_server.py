# run_server.py
import os, sys, traceback, faulthandler
from pathlib import Path

# write crash logs next to the exe
BASE_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / "backend_crash.log"

# dump fatal crashes too
faulthandler.enable(open(LOG_FILE, "a", encoding="utf-8"))

def log(msg: str):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

try:
    log(f"\n--- START ---")
    log(f"exe={sys.executable}")
    log(f"cwd={os.getcwd()}")
    log(f"base_dir={BASE_DIR}")

    import uvicorn

    # IMPORTANT: import app after logging is ready
    from main import app

    uvicorn.run(app, host="0.0.0.0", port=5001, reload=False, log_level="info")

except Exception:
    err = traceback.format_exc()
    log(err)
    print(err)  # if console is visible
    input("\nPress Enter to exit...")
