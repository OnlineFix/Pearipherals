@echo off
rem Build Pearipherals.exe into dist\ — run from the repo root.
rem Set PEARIPHERALS_VERSION for a release build; local builds default to 1.2.0.
if not defined PEARIPHERALS_VERSION set PEARIPHERALS_VERSION=1.2.0
if not exist .venv (
    python -m venv .venv || goto :err
    .venv\Scripts\pip install -r requirements.txt || goto :err
)
.venv\Scripts\python.exe scripts\write_version_info.py %PEARIPHERALS_VERSION% build\pearipherals-version-info.txt || goto :err
.venv\Scripts\pyinstaller --noconfirm --onefile --windowed --name Pearipherals --icon pearipherals.ico --version-file build\pearipherals-version-info.txt --hidden-import pystray._win32 pearipherals.py || goto :err
echo.
echo Build OK: dist\Pearipherals.exe
exit /b 0
:err
echo Build FAILED
exit /b 1
