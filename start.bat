@echo off
rem Acoustic Masking Lab - one-time setup and run (Windows).
rem The Python environment lives outside OneDrive: %LOCALAPPDATA%\AcousticMaskingLab\venv
setlocal
set "BASE=%LOCALAPPDATA%\AcousticMaskingLab"
set "VENV=%BASE%\venv"
set "AML_AMT_ROOT=%BASE%\amt\amtoolbox-1.6.0"
if not exist "%VENV%\Scripts\python.exe" (
  echo Creating Python environment in %VENV% ...
  python -m venv "%VENV%" || goto :err
  "%VENV%\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt" || goto :err
)
if not exist "%~dp0frontend\dist\index.html" (
  echo Building the frontend ...
  pushd "%~dp0frontend"
  call npm install && call npm run build || goto :err
  popd
)
if not exist "%AML_AMT_ROOT%\models\paulick2024.m" (
  echo Installing AMT 1.6.0 for the CASP page ...
  "%VENV%\Scripts\python.exe" "%~dp0scripts\install_amt.py" "%BASE%\amt" || echo AMT install failed: the CASP page will be disabled.
)
echo Starting on http://127.0.0.1:8770
start "" http://127.0.0.1:8770
"%VENV%\Scripts\python.exe" -m uvicorn app:app --app-dir "%~dp0backend" --host 127.0.0.1 --port 8770
goto :eof
:err
echo Setup failed.
pause
