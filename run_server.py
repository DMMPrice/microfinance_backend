# run_server.py
import uvicorn

# ⬇️ IMPORTANT: this makes Nuitka see and bundle main.py
from main import app

# python -m nuitka --onefile --standalone --follow-imports
# --include-data-file=.env=.env --enable-plugin=multiprocessing
# --enable-plugin=anti-bloat --output-dir=dist run_server.py
def main():
    # Pass the app object directly (no "main:app" string)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("\n[ERROR] Backend crashed:")
        print(e)
        print("\nPress Enter to exit...")
        input()
    else:
        print("\nServer stopped. Press Enter to exit...")
        input()
