@echo off
cd /d %~dp0
if not exist kiza.db (
  echo First run: creating a CLEAN database with REAL mode ^(no demo data^).
  python db.py --real
  echo.
  echo SAVE THE PASSWORDS ABOVE NOW - they are shown only once.
  pause
)
echo Starting KIZA-AGRI ...
start "KIZA Python ML service" cmd /c python ml_service\api.py
start "KIZA App" cmd /c python app.py
timeout /t 3 >nul
start http://127.0.0.1:5000
