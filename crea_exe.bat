@echo off
rem Crea la versione eseguibile in dist\FotocameraTeletrasporto\FotocameraTeletrasporto.exe
rem Da usare DOPO aver verificato che tutto funziona con avvia.bat.
setlocal
cd /d "%~dp0"
call "%~dp0ambiente.bat" || goto :errore

uv run --frozen pyinstaller --noconfirm --clean ^
  --name FotocameraTeletrasporto ^
  --windowed --onedir ^
  --paths src ^
  --collect-all mediapipe ^
  --hidden-import comtypes.stream ^
  --add-data "models;models" ^
  src\teletrasporto\__main__.py
if errorlevel 1 goto :errore

echo.
echo Fatto: dist\FotocameraTeletrasporto\FotocameraTeletrasporto.exe
echo Le cartelle config e clips verranno create accanto all'eseguibile.
pause
exit /b 0

:errore
echo.
echo Creazione dell'eseguibile non riuscita. Leggi i messaggi qui sopra.
pause
exit /b 1
