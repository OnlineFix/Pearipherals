@echo off
rem Build Pearipherals.exe into dist\ — run from the repo root.
if not exist .venv (
    python -m venv .venv || goto :err
    .venv\Scripts\pip install -r requirements.txt || goto :err
)
.venv\Scripts\pyinstaller --noconfirm --onefile --windowed --name Pearipherals --icon pearipherals.ico --hidden-import pystray._win32 pearipherals.py || goto :err
echo.
echo Build OK: dist\Pearipherals.exe
exit /b 0
:err
echo Build FAILED
exit /b 1
