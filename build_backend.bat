@echo off
setlocal

REM ================================
REM Go to the folder of this script
REM ================================
cd /d "%~dp0"

echo ----------------------------------------
echo [1/4] Checking virtual environment...
echo ----------------------------------------

REM If venv does not exist, create it
if not exist venv\Scripts\python.exe (
    echo Creating virtual environment: venv
    python -m venv venv
)

echo.
echo ----------------------------------------
echo [2/4] Activating virtual environment...
echo ----------------------------------------
call venv\Scripts\activate.bat

echo.
echo ----------------------------------------
echo [3/4] Installing requirements...
echo ----------------------------------------
pip install --upgrade pip
pip install -r requirements.txt

echo.
echo ----------------------------------------
echo [4/4] Building EXE with Nuitka...
echo ----------------------------------------

python -m nuitka ^
  --onefile ^
  --standalone ^
  --enable-plugin=multiprocessing ^
  --output-dir=dist ^
  run_server.py

echo.
echo ========================================
echo Build complete.
echo Check the "dist" folder for run_server.exe
echo ========================================
echo.
pause
endlocal
