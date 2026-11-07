@echo off
rem One-folder Windows build of EV-Traction Lab, from a clean virtual environment.
rem Run from the repository root, with Python 3.12 (64-bit) on the PATH as "py -3.12".
py -3.12 -m venv .venv-build || exit /b 1
call .venv-build\Scripts\activate.bat || exit /b 1
python -m pip install --upgrade pip || exit /b 1
python -m pip install -r requirements.txt -r packaging\requirements-build.txt || exit /b 1
pyinstaller --noconfirm --clean packaging\EVLab.spec || exit /b 1
rem Start-up self-test of the build (exit code 0 = all checks passed; log in build\smoke\smoke.log)
start /wait "" dist\EVLab\EVLab.exe --smoke build\smoke
if errorlevel 1 (type build\smoke\smoke.log & exit /b 1)
type build\smoke\smoke.log
echo Build OK: dist\EVLab\EVLab.exe
