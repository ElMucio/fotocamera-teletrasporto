"""Avvio del programma."""
import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from . import modelli
from .clip import ArchivioClip
from .impostazioni import Impostazioni
from .percorsi import CLIP
from .pipeline import Pipeline
from .ui.finestra import Finestra
from .uscita.fotocamera_virtuale import obs_installata


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    app.setApplicationName("Fotocamera Teletrasporto")
    try:
        modelli.scarica_mancanti()
    except OSError as e:
        QMessageBox.critical(None, "Modelli mancanti", f"Download dei modelli non riuscito:\n{e}")
        return 1

    imp = Impostazioni.carica()
    if imp.fotocamera_virtuale and not obs_installata():
        QMessageBox.warning(None, "Fotocamera virtuale",
                            "OBS Virtual Camera non trovata: installa OBS Studio per usare la "
                            "fotocamera virtuale. Intanto funziona solo l'anteprima.")
    archivio = ArchivioClip(CLIP, imp.clip_da_conservare)
    archivio.carica_in_background()
    pipeline = Pipeline(imp, archivio)
    finestra = Finestra(imp, pipeline)
    finestra.show()
    return app.exec()
