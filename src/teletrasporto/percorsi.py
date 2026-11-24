"""Percorsi delle cartelle del progetto, validi sia da sorgente sia dall'eseguibile."""
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    # Eseguibile PyInstaller: i dati scrivibili stanno accanto all'exe, i modelli nel pacchetto.
    RADICE = Path(sys.executable).resolve().parent
    MODELLI = Path(getattr(sys, "_MEIPASS", RADICE)) / "models"
else:
    RADICE = Path(__file__).resolve().parents[2]
    MODELLI = RADICE / "models"

CONFIG = RADICE / "config"
CLIP = RADICE / "clips"
