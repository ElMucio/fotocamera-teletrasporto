@echo off
rem Prepara l'ambiente isolato nella cartella del progetto (usato da avvia.bat e crea_exe.bat).
rem Pacchetti, cache e .venv restano qui dentro: niente viene installato nel Python di sistema.
rem Si usa il Python 3.12 ufficiale di python.org (gia' installato) perche' e' firmato:
rem Smart App Control di Windows blocca le versioni di Python non firmate.
set "UV_PYTHON=3.12"
set "UV_PYTHON_PREFERENCE=only-system"
set "UV_CACHE_DIR=%~dp0.uv-cache"
set "UV_PROJECT_ENVIRONMENT=%~dp0.venv"
set "UV_LINK_MODE=copy"
if exist "%~dp0strumenti\uv.exe" set "PATH=%~dp0strumenti;%PATH%"

where uv >nul 2>nul
if errorlevel 1 (
  echo uv non trovato. Scaricalo da https://docs.astral.sh/uv/ e metti uv.exe in "%~dp0strumenti".
  exit /b 1
)

if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Prima installazione: scarico i pacchetti dentro la cartella del progetto...
)
uv sync || (
  echo Serve Python 3.12 da https://www.python.org/downloads/ ^(installatore ufficiale^).
  exit /b 1
)
uv run --frozen python -m teletrasporto.modelli || exit /b 1
exit /b 0
