@echo off
rem Avvia Fotocamera Teletrasporto. Tutto (Python, pacchetti, cache, modelli)
rem resta dentro questa cartella: per disinstallare basta cancellarla.
setlocal
cd /d "%~dp0"
call "%~dp0ambiente.bat" || goto :errore
uv run --frozen python -m teletrasporto %*
if errorlevel 1 goto :errore
exit /b 0

:errore
echo.
echo Si e' verificato un errore. Leggi i messaggi qui sopra.
pause
exit /b 1
