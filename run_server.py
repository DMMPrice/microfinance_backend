# run_server.py
import os, sys, traceback, faulthandler, ctypes
from pathlib import Path
import multiprocessing


def show_error_popup(msg: str):
    try:
        ctypes.windll.user32.MessageBoxW(0, msg, "Backend Crash", 0x10)  # MB_ICONERROR
    except Exception:
        pass


# Ensure child-process safety (important when multiprocessing plugin is enabled)
if __name__ == "__main__":
    multiprocessing.freeze_support()

BASE_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / "backend_crash.log"

# Ensure logs go next to the exe and relative paths work
os.chdir(BASE_DIR)

# Dump fatal crashes too
_fh = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
faulthandler.enable(_fh)


def log(msg: str):
    try:
        _fh.write(msg + "\n")
        _fh.flush()
    except Exception:
        pass


def main():
    log("\n--- START ---")
    log(f"exe={sys.executable}")
    log(f"cwd={os.getcwd()}")
    log(f"base_dir={BASE_DIR}")
    log(f"argv={sys.argv}")

    try:
        import uvicorn
        from main import app  # import after logging is ready

        uvicorn.run(app, host="0.0.0.0", port=5001, reload=False, log_level="info")

    except Exception:
        err = traceback.format_exc()
        log(err)
        print(err)  # visible if console exists
        show_error_popup(err)  # visible even if console disappears


if __name__ == "__main__":
    try:
        main()
    finally:
        # Always pause so double-click doesn't vanish instantly
        try:
            input("\nProcess ended. Press Enter to exit...")
        except Exception:
            pass
