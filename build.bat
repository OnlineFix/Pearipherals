@echo off
rem Build Pearipherals.exe into dist\ — run from the repo root.
rem Set PEARIPHERALS_VERSION for a release build; local builds default to 1.2.0.
if not defined PEARIPHERALS_VERSION set "PEARIPHERALS_VERSION=1.2.0"
if not exist .venv (
    python -m venv .venv || goto :err
    .venv\Scripts\pip install -r requirements.txt || goto :err
)
rem validate_build_version before any %PEARIPHERALS_VERSION% command-line expansion.
.venv\Scripts\python.exe -c "import os,re,sys; v=os.environ.get('PEARIPHERALS_VERSION',''); sys.exit(0 if re.fullmatch(r'v?[0-9]+[.][0-9]+[.][0-9]+(?:[.][0-9]+)?', v) else 2)" || goto :err
.venv\Scripts\python.exe scripts\write_version_info.py "%PEARIPHERALS_VERSION%" build\pearipherals-version-info.txt || goto :err
rem A local build may claim git:HEAD only when the complete worktree is clean.
rem Clear inherited state first; Git/resolver failure and dirty files stay unknown.
set PEARIPHERALS_REVISION=
for /f %%i in ('.venv\Scripts\python.exe scripts\write_build_manifest.py --resolve-local-revision .') do set PEARIPHERALS_REVISION=%%i
if not defined PEARIPHERALS_REVISION set PEARIPHERALS_REVISION=0000000000000000000000000000000000000000
.venv\Scripts\python.exe scripts\write_build_manifest.py "%PEARIPHERALS_VERSION%" "%PEARIPHERALS_REVISION%" build\pearipherals-build.json || goto :err
.venv\Scripts\pyinstaller --noconfirm --onefile --windowed --name Pearipherals --icon pearipherals.ico --version-file build\pearipherals-version-info.txt --add-data "build\pearipherals-build.json;." --hidden-import pystray._win32 pearipherals.py || goto :err
echo.
echo Build OK: dist\Pearipherals.exe
exit /b 0
:err
echo Build FAILED
exit /b 1
